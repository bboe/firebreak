from __future__ import annotations

import enum
import hashlib

from firebreak.amonet.payload import (
    ACKNOWLEDGEMENT,
    BLOCK_SIZE,
    Command,
    NotReadyError,
    Payload,
    framed,
)
from firebreak.emmc import RPMB_SIZE
from firebreak.mediatek.usbdl import (
    PAYLOAD_LOAD_ADDRESS,
    Connection,
    ProtocolMismatchError,
)

MAXIMUM_BLOCKS = 64
STAGE1_SHA256 = "dd5dddcde43eb9aec57351e9702226a4a47a560106d6d9fd62aa0cf9233617d6"
STAGE2_READY = b"\xb1\xb2\xb3\xb4"


class Client(Payload):
    SHA256 = "f17b6a7a537f1983d90c162f80d6cc042cc16ba7f22828448b8713b4b97f47fd"
    maximum_blocks = MAXIMUM_BLOCKS

    def kick(self) -> None:
        self._send(command=DonutCommand.KICK_WATCHDOG)

    def read_block(self, *, index: int) -> bytes:
        self._send(arguments=(index,), command=Command.READ_BLOCK)
        return self.read_exactly(label=f"block {index}", length=BLOCK_SIZE)

    def read_blocks(self, *, count: int, index: int) -> bytes:
        check_block_count(count=count)
        self._send(arguments=(index, count), command=DonutCommand.READ_BLOCKS)
        return self.read_exactly(
            label=f"{count} blocks at {index}", length=count * BLOCK_SIZE
        )

    def read_rpmb(self) -> bytes:
        self._send(command=Command.READ_RPMB)
        return self.read_exactly(label="RPMB", length=RPMB_SIZE)

    def write_blocks(self, *, data: bytes, index: int) -> None:
        count, remainder = divmod(len(data), BLOCK_SIZE)
        if remainder:
            message = f"{len(data)} bytes is not a whole number of blocks"
            raise ValueError(message)
        check_block_count(count=count)
        self._send(arguments=(index, count), command=DonutCommand.WRITE_BLOCKS)
        self.port.write(data=data)
        self._acknowledge(label=f"write of {count} blocks at {index}")


class DonutCommand(enum.IntEnum):
    KICK_WATCHDOG = 0x3001
    LOAD_STAGE2 = 0x4000
    READ_BLOCKS = 0x1004
    READ_MEMORY = 0x5000
    START_STAGE2 = 0x4001
    WRITE_BLOCKS = 0x1003


def check_block_count(*, count: int) -> None:
    if not 1 <= count <= MAXIMUM_BLOCKS:
        message = (
            f"a multi-block command takes 1 to {MAXIMUM_BLOCKS} blocks, not {count}"
        )
        raise ValueError(message)


def start_stage2(
    *, client: type[Client] = Client, stage1: Connection, stage2: bytes
) -> Client:
    found = hashlib.sha256(stage2).hexdigest()
    if found != client.SHA256:
        message = (
            f"stage2.bin has SHA-256 {found}, but {client.__module__} speaks"
            f" only {client.SHA256}"
        )
        raise ProtocolMismatchError(message)
    stage1.port.write(
        data=framed(
            arguments=(PAYLOAD_LOAD_ADDRESS, len(stage2)),
            command=DonutCommand.LOAD_STAGE2,
        )
    )
    stage1.port.write(data=stage2)
    acknowledged = stage1.read_exactly(
        label="stage 2 acknowledgement", length=len(ACKNOWLEDGEMENT)
    )
    if acknowledged != ACKNOWLEDGEMENT:
        message = (
            f"stage 1 did not take stage 2: expected {ACKNOWLEDGEMENT!r},"
            f" got {acknowledged!r}"
        )
        raise ProtocolMismatchError(message)
    stage1.port.write(
        data=framed(
            arguments=(PAYLOAD_LOAD_ADDRESS,), command=DonutCommand.START_STAGE2
        )
    )
    ready = stage1.read_exactly(label="stage 2 ready pattern", length=len(STAGE2_READY))
    if ready != STAGE2_READY:
        message = f"stage 2's ready pattern: expected {STAGE2_READY!r}, got {ready!r}"
        raise NotReadyError(message)
    return client(port=stage1.port, timeout=stage1.timeout)
