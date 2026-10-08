from __future__ import annotations

import enum

from firebreak.amonet.payload import BLOCK_SIZE, Command, Payload
from firebreak.emmc import RPMB_SIZE
from firebreak.mediatek.usbdl import PAYLOAD_LOAD_ADDRESS

FLUSH_LENGTH = 4
MAXIMUM_BLOCKS = 64


class BiscuitCommand(enum.IntEnum):
    WRITE_BLOCKS = 0x1003
    READ_BLOCKS = 0x1004
    READ_MEMORY = 0x5000


class Client(Payload):
    SHA256 = "51401ef600f464ea3c32dada3c131e6b3776be2d6ccdf801ba94f1c3358ccf88"
    maximum_blocks = MAXIMUM_BLOCKS

    def _flushed(self, *, label: str, length: int) -> bytes:
        self._send(
            arguments=(PAYLOAD_LOAD_ADDRESS, FLUSH_LENGTH),
            command=BiscuitCommand.READ_MEMORY,
        )
        return self.read_exactly(label=label, length=length + FLUSH_LENGTH)[:length]

    def read_block(self, *, index: int) -> bytes:
        self._send(arguments=(index,), command=Command.READ_BLOCK)
        return self._flushed(label=f"block {index}", length=BLOCK_SIZE)

    def read_blocks(self, *, count: int, index: int) -> bytes:
        check_block_count(count=count)
        self._send(arguments=(index, count), command=BiscuitCommand.READ_BLOCKS)
        return self._flushed(
            label=f"{count} blocks at {index}", length=count * BLOCK_SIZE
        )

    def read_rpmb(self) -> bytes:
        self._send(command=Command.READ_RPMB)
        return self._flushed(label="RPMB", length=RPMB_SIZE)

    def write_blocks(self, *, data: bytes, index: int) -> None:
        count, remainder = divmod(len(data), BLOCK_SIZE)
        if remainder:
            message = f"{len(data)} bytes is not a whole number of blocks"
            raise ValueError(message)
        check_block_count(count=count)
        self._send(arguments=(index, count), command=BiscuitCommand.WRITE_BLOCKS)
        self.port.write(data=data)
        self._acknowledge(label=f"write of {count} blocks at {index}")


def check_block_count(*, count: int) -> None:
    if not 1 <= count <= MAXIMUM_BLOCKS:
        message = (
            f"a multi-block command takes 1 to {MAXIMUM_BLOCKS} blocks, not {count}"
        )
        raise ValueError(message)
