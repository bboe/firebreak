from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from firebreak.ui import FatalError, again

if TYPE_CHECKING:
    import pathlib

CHUNK = 1 << 20
DOWNLOAD_SIZE = 0x6D00000
FIRE_OS_5 = (
    0x08, 0xB5, None, None, None, None, 0x01, 0x28, None, 0xD0,
    0x00, 0x20, 0x08, 0xBD, None, None, None, None, 0xD0, 0xF1,
    0x01, 0x00, 0x38, 0xBF, 0x00, 0x20, 0x08, 0xBD,
)  # fmt: skip
FIRE_OS_6 = (
    0x08, 0xB5, None, None, None, None, 0x01, 0x28, None, 0xD1,
    None, None, None, None, 0xB0, 0xFA, 0x80, 0xF0, 0x40, 0x09,
    0x08, 0xBD, 0x00, 0x20, 0x08, 0xBD,
)  # fmt: skip
HEADER = 0x200
LOCK_CHECKS = (FIRE_OS_5, FIRE_OS_6)
MTK_MAGIC = 0x58881688
OVERSHOOT = 0x24
UNLOCKED = bytes.fromhex("00207047")


def head(*, image: pathlib.Path) -> bytes:
    code = little_kernel(image=image)
    offset = located(code=code, name=image.name)
    patched = bytearray(code[: offset + OVERSHOOT])
    patched[offset : offset + len(UNLOCKED)] = UNLOCKED
    return bytes(patched)


def little_kernel(*, image: pathlib.Path) -> bytes:
    raw = image.read_bytes()
    if len(raw) < HEADER:
        raise FatalError(
            message=f"{image.name} is too short to be a bootloader image. " + again()
        )
    magic, size = struct.unpack_from("<II", raw, 0)
    if magic != MTK_MAGIC or size > len(raw) - HEADER:
        raise FatalError(message=f"{image.name} is not a bootloader image. " + again())
    return raw[HEADER : HEADER + size]


def located(*, code: bytes, name: str) -> int:
    found = [
        at
        for shape in LOCK_CHECKS
        for at in range(0, len(code) - len(shape) + 1, 2)
        if all(
            want is None or code[at + index] == want for index, want in enumerate(shape)
        )
    ]
    if len(found) != 1:
        raise FatalError(
            message=f"{name} holds {len(found)} lock checks rather than one, so"
            " this cannot unlock it and the Dot was not modified. " + again()
        )
    return found[0]


def write(*, image: pathlib.Path, path: pathlib.Path) -> pathlib.Path:
    tail = head(image=image)
    zeros = bytes(CHUNK)
    with path.open(mode="wb") as out:
        for _ in range(DOWNLOAD_SIZE // CHUNK):
            out.write(zeros)
        out.write(bytes(DOWNLOAD_SIZE % CHUNK))
        out.write(tail)
    return path
