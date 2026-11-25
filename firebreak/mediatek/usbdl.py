from __future__ import annotations

import contextlib
import enum
import struct
import time
from typing import TYPE_CHECKING, Protocol

from firebreak.sizes import padded

if TYPE_CHECKING:
    from collections.abc import Sequence

BAUD_RATE = 115200
CACHE_DISABLE_SUBCOMMAND = 0xB1
HANDSHAKE = ((0xA0, 0x5F), (0x0A, 0xF5), (0x50, 0xAF), (0x05, 0xFA))
HANDSHAKE_TIMEOUT = 10
HARDWARE_CODE_SIZE = 4
JUMP_REGISTER = 0x1028A8
MEDIATEK_VENDOR_ID = 0x0E8D
MESSAGE_LIMIT = 64
PAYLOAD_LOAD_ADDRESS = 0x201000
PAYLOAD_STATUS = b"\0\0"
PORT_POLL_INTERVAL = 0.25
READ_STATUS = b"\x00\x00"
READ_TIMEOUT = 5
STATUS_LIMIT = 0xFF
WATCHDOG_DISABLE_ADDRESS = 0x10007000
WATCHDOG_DISABLE_VALUE = 0x22000000
WORD_MASK = 0xFFFFFFFF
WORD_SIZE = 4
WRITE_STATUS = b"\x00\x01"


class BootromCommand(enum.IntEnum):
    EXTENDED = 0xC8
    READ_WORDS = 0xD1
    WRITE_WORDS = 0xD4
    ACCESS = 0xDA
    SEND_PAYLOAD = 0xE0
    HARDWARE_CODE = 0xFD


class Connection:
    def __init__(self, *, port: SerialPort, timeout: float = READ_TIMEOUT) -> None:
        self.port = port
        self.timeout = timeout

    def read_exactly(self, *, label: str, length: int) -> bytes:
        data = bytearray()
        deadline = time.monotonic() + self.timeout
        while len(data) < length:
            data += self.port.read(size=length - len(data))
            if len(data) < length and time.monotonic() >= deadline:
                cut = "..." if len(data) > MESSAGE_LIMIT else ""
                message = (
                    f"{label}: read {len(data)} of {length} bytes before the"
                    f" {self.timeout} second timeout; got"
                    f" {bytes(data[:MESSAGE_LIMIT])!r}{cut}"
                )
                raise ShortReadError(message, received=bytes(data))
        return bytes(data)


class Bootrom(Connection):
    def _echo(self, *, data: bytes, label: str) -> None:
        self.port.write(data=data)
        verify(
            expected=data,
            label=f"{label}: echo",
            received=self.read_exactly(label=label, length=len(data)),
            sent=data,
        )

    def _header(
        self, *, address: int, command: BootromCommand, count: int, label: str
    ) -> None:
        self._echo(data=bytes([command]), label=label)
        self._echo(data=struct.pack(">I", address), label=f"{label}: address")
        self._echo(data=struct.pack(">I", count), label=f"{label}: count")

    def _read_status(self, *, label: str, strict: bool) -> None:
        data = self.read_exactly(label=label, length=len(READ_STATUS))
        if strict:
            verify(expected=READ_STATUS, label=label, received=data)
            return
        (status,) = struct.unpack(">H", data)
        if status > STATUS_LIMIT:
            message = (
                f"{label}: {status:#06x} is past {STATUS_LIMIT:#04x}, so the"
                " bootrom refused the read rather than objecting to it"
            )
            raise ProtocolMismatchError(message)

    def _status(self, *, expected: bytes, label: str) -> None:
        verify(
            expected=expected,
            label=label,
            received=self.read_exactly(label=label, length=len(expected)),
        )

    def access(
        self,
        *,
        address: int,
        data: bytes = b"",
        end_status: bool = True,
        length: int = 0,
    ) -> bytes:
        length = len(data) if data else length
        label = f"{'write' if data else 'read'} of {length} bytes at {address:#x}"
        self._echo(data=bytes([BootromCommand.ACCESS]), label=label)
        for word in (int(bool(data)), address, length):
            self._echo(data=struct.pack(">I", word), label=label)
        self._status(expected=READ_STATUS, label=f"{label}: argument status")
        held = b""
        if data:
            self.port.write(data=data)
        else:
            held = self.read_exactly(label=label, length=length)
        if end_status:
            self._status(expected=READ_STATUS, label=f"{label}: end status")
        return held

    def disable_caches(self) -> None:
        self.send_extended(subcommand=CACHE_DISABLE_SUBCOMMAND)

    def disable_watchdog(self) -> None:
        self.write_words(
            address=WATCHDOG_DISABLE_ADDRESS, words=(WATCHDOG_DISABLE_VALUE,)
        )

    def handshake(self) -> None:
        first, answer = HANDSHAKE[0]
        deadline = time.monotonic() + HANDSHAKE_TIMEOUT
        while True:
            self.port.write(data=bytes([first]))
            with contextlib.suppress(ProtocolMismatchError):
                if self.read_exactly(label="handshake", length=1) == bytes([answer]):
                    break
            self.port.reset_input_buffer()
            if time.monotonic() >= deadline:
                message = (
                    f"no {answer:#04x} answered {first:#04x} within"
                    f" {HANDSHAKE_TIMEOUT} seconds; the port needs a replug"
                )
                raise HandshakeTimeoutError(message)
        for sent, expected in HANDSHAKE[1:]:
            self.port.write(data=bytes([sent]))
            verify(
                expected=bytes([expected]),
                label=f"handshake step {sent:#04x}",
                received=self.read_exactly(label="handshake", length=1),
                sent=bytes([sent]),
            )

    def hardware_code(self) -> int:
        label = "hardware code"
        self._echo(data=bytes([BootromCommand.HARDWARE_CODE]), label=label)
        held = self.read_exactly(label=label, length=HARDWARE_CODE_SIZE)
        code, _ = struct.unpack(">HH", held)
        verify(
            expected=READ_STATUS,
            label=f"{label} status",
            received=held[-len(READ_STATUS) :],
        )
        return code

    def read_words(
        self, *, address: int, count: int, strict: bool = True
    ) -> tuple[int, ...]:
        label = f"read of {count} words at {address:#x}"
        self._header(
            address=address, command=BootromCommand.READ_WORDS, count=count, label=label
        )
        self._read_status(label=f"{label}: argument status", strict=strict)
        data = self.read_exactly(label=label, length=count * WORD_SIZE)
        self._read_status(label=f"{label}: end status", strict=strict)
        return struct.unpack(f">{count}I", data)

    def run_payload(self, *, payload: bytes) -> None:
        self.write_words(
            address=PAYLOAD_LOAD_ADDRESS, words=payload_words(data=payload)
        )
        self.write_words(
            address=JUMP_REGISTER, read_status=False, words=(PAYLOAD_LOAD_ADDRESS,)
        )

    def send_extended(self, *, subcommand: int) -> None:
        label = f"extended command {subcommand:#04x}"
        self._echo(data=bytes([BootromCommand.EXTENDED]), label=label)
        self._echo(data=bytes([subcommand]), label=label)
        self.read_exactly(label=label, length=1)
        self.read_exactly(label=label, length=2)

    def send_payload(self, *, payload: bytes) -> None:
        label = f"payload of {len(payload)} bytes"
        self._echo(data=bytes([BootromCommand.SEND_PAYLOAD]), label=label)
        self._echo(data=struct.pack(">I", len(payload)), label=f"{label}: length")
        room = self.read_exactly(label=f"{label}: room", length=len(PAYLOAD_STATUS))
        if room != PAYLOAD_STATUS:
            message = (
                f"{label}: the bootrom kept no room for a payload that long,"
                f" answering {room!r}"
            )
            raise PayloadTooLargeError(message)
        self.port.write(data=payload)
        self.read_exactly(label=f"{label}: upload status", length=len(PAYLOAD_STATUS))
        self.read_exactly(label=f"{label}: end status", length=len(PAYLOAD_STATUS))

    def write_words(
        self, *, address: int, read_status: bool = True, words: Sequence[int]
    ) -> None:
        label = f"write of {len(words)} words at {address:#x}"
        self._header(
            address=address,
            command=BootromCommand.WRITE_WORDS,
            count=len(words),
            label=label,
        )
        self._status(expected=WRITE_STATUS, label=f"{label}: argument status")
        for index, word in enumerate(words):
            self._echo(
                data=struct.pack(">I", word),
                label=f"{label}: word {index} at {address + index * WORD_SIZE:#x}",
            )
        if read_status:
            self._status(expected=WRITE_STATUS, label=f"{label}: end status")


class ProductId(enum.IntEnum):
    BOOTROM = 0x0003
    PRELOADER = 0x2000


class SerialPort(Protocol):
    timeout: float | None

    def read(self, *, size: int) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def write(self, *, data: bytes) -> int | None: ...


class UsbdlError(Exception):
    pass


class HandshakeTimeoutError(UsbdlError):
    pass


class PayloadTooLargeError(UsbdlError):
    pass


class ProtocolMismatchError(UsbdlError):
    pass


class ShortReadError(ProtocolMismatchError):
    def __init__(self, message: str, *, received: bytes) -> None:
        super().__init__(message)
        self.received = received


def mediatek_ports() -> dict[str, int | None]:
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    return {
        port.device: port.pid
        for port in list_ports.comports()
        if port.vid == MEDIATEK_VENDOR_ID
    }


def payload_words(*, data: bytes) -> tuple[int, ...]:
    whole = data.ljust(padded(length=len(data), unit=WORD_SIZE), b"\0")
    return struct.unpack(f"<{len(whole) // WORD_SIZE}I", whole)


def verify(
    *, expected: bytes, label: str, received: bytes, sent: bytes | None = None
) -> None:
    if received == expected:
        return
    message = (
        f"{label}: expected {expected!r}, got {received!r}"
        if sent is None
        else f"{label}: sent {sent!r}, expected {expected!r}, got {received!r}"
    )
    raise ProtocolMismatchError(message)
