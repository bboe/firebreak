from __future__ import annotations

import enum
import hashlib
import struct
from typing import TYPE_CHECKING, ClassVar, TypeVar

from firebreak.emmc import RPMB_SIZE
from firebreak.mediatek.usbdl import Connection, ProtocolMismatchError, verify

if TYPE_CHECKING:
    from collections.abc import Sequence

    from firebreak.mediatek.usbdl import Bootrom

ACKNOWLEDGEMENT = b"\xd0\xd0\xd0\xd0"
BLOCK_SIZE = 0x200
PAYLOAD_MAGIC = 0xF00DD00D
PAYLOAD_READY = b"\xb1\xb2\xb3\xb4"


class Command(enum.IntEnum):
    READ_BLOCK = 0x1000
    WRITE_BLOCK = 0x1001
    SWITCH_PARTITION = 0x1002
    READ_RPMB = 0x2000
    WRITE_RPMB = 0x2001
    REBOOT = 0x3000


class NotReadyError(ProtocolMismatchError):
    pass


class Payload(Connection):
    SHA256: ClassVar[str]

    def _acknowledge(self, *, label: str) -> None:
        verify(
            expected=ACKNOWLEDGEMENT,
            label=label,
            received=self.read_exactly(label=label, length=len(ACKNOWLEDGEMENT)),
        )

    def _send(self, *, arguments: Sequence[int] = (), command: int) -> None:
        self.port.write(
            data=struct.pack(
                f">{2 + len(arguments)}I", PAYLOAD_MAGIC, command, *arguments
            )
        )

    def reboot(self) -> None:
        self._send(command=Command.REBOOT)

    def switch_partition(self, *, partition: int) -> None:
        self._send(arguments=(partition,), command=Command.SWITCH_PARTITION)

    def write_block(self, *, data: bytes, index: int) -> None:
        if len(data) != BLOCK_SIZE:
            message = f"a block is {BLOCK_SIZE} bytes, not {len(data)}"
            raise ValueError(message)
        self._send(arguments=(index,), command=Command.WRITE_BLOCK)
        self.port.write(data=data)
        self._acknowledge(label=f"write of block {index}")

    def write_rpmb(self, *, data: bytes) -> None:
        if len(data) != RPMB_SIZE:
            message = f"RPMB takes {RPMB_SIZE} bytes, not {len(data)}"
            raise ValueError(message)
        self._send(command=Command.WRITE_RPMB)
        self.port.write(data=data)


Client = TypeVar("Client", bound=Payload)


def start_payload(*, bootrom: Bootrom, client: type[Client], payload: bytes) -> Client:
    found = hashlib.sha256(payload).hexdigest()
    if found != client.SHA256:
        message = (
            f"payload.bin has SHA-256 {found}, but {client.__module__} speaks"
            f" only {client.SHA256}"
        )
        raise ProtocolMismatchError(message)
    bootrom.run_payload(payload=payload)
    ready = bootrom.read_exactly(label="ready pattern", length=len(PAYLOAD_READY))
    if ready != PAYLOAD_READY:
        message = (
            f"the payload's ready pattern: expected {PAYLOAD_READY!r}, got {ready!r}"
        )
        raise NotReadyError(message)
    return client(port=bootrom.port, timeout=bootrom.timeout)
