from __future__ import annotations

import struct
import zlib
from typing import NamedTuple

from firebreak.ui import _die

GPT_HEADER_SIZE = 92
STOCK_PARTITIONS = 16


class Partition(NamedTuple):
    number: int
    first: int
    sectors: int

    @property
    def size(self) -> int:
        return self.sectors * 512


def gpt_intact(*, entries: bytes, hdr: bytes) -> bool:
    if hdr[:8] != b"EFI PART" or struct.unpack("<I", hdr[12:16])[0] != GPT_HEADER_SIZE:
        return False
    if struct.unpack("<II", hdr[80:88]) != (128, 128):
        return False
    h = bytearray(hdr[:92])
    h[16:20] = bytes(4)
    return (
        zlib.crc32(h) & 0xFFFFFFFF == struct.unpack("<I", hdr[16:20])[0]
        and zlib.crc32(entries[: 128 * 128]) & 0xFFFFFFFF
        == struct.unpack("<I", hdr[88:92])[0]
    )


def stock_gpt(  # ruff: ignore[too-many-locals]
    raw: bytes,
) -> tuple[bytes, bytes, int, dict[str, Partition]]:
    mbr, hdr, entries = (
        raw[:512],
        bytearray(raw[512:1024]),
        raw[1024 : 1024 + 128 * 128],
    )
    if not gpt_intact(entries=entries, hdr=hdr):
        _die(message="neither copy of the Dot's partition table is intact")
    last_usable = struct.unpack("<Q", hdr[48:56])[0]
    backup_lba = max(struct.unpack("<QQ", hdr[24:40]))
    names = [
        entries[i * 128 + 56 : (i + 1) * 128].decode("utf-16le").rstrip("\0")
        for i in range(128)
    ]
    amonet = any(name.endswith("_x") for name in names)
    new = bytearray(128 * 128)
    k = 0
    for i in range(128):
        e = bytearray(entries[i * 128 : (i + 1) * 128])
        if e[:16] == b"\0" * 16:
            continue
        name = names[i]
        if amonet and name in {"boot_a", "boot_b"}:
            continue
        if name.endswith("_x"):
            name = name[:-2]
            e[56:128] = name.encode("utf-16le").ljust(72, b"\0")
        if name == "userdata":
            e[40:48] = struct.pack("<Q", last_usable)
        new[k * 128 : (k + 1) * 128] = e
        k += 1
    if k != STOCK_PARTITIONS:
        _die(
            message=f"the stock table would have {k} partitions, not {STOCK_PARTITIONS}"
        )
    entries_crc = zlib.crc32(new) & 0xFFFFFFFF

    def header(*, alternate: int, at: int, my: int) -> bytes:
        h = bytearray(hdr[:92])
        h[16:20] = b"\0" * 4
        h[24:32] = struct.pack("<Q", my)
        h[32:40] = struct.pack("<Q", alternate)
        h[72:80] = struct.pack("<Q", at)
        h[88:92] = struct.pack("<I", entries_crc)
        h[16:20] = struct.pack("<I", zlib.crc32(h) & 0xFFFFFFFF)
        return bytes(h).ljust(512, b"\0")

    parts = {}
    for i in range(k):
        e = new[i * 128 : (i + 1) * 128]
        first, last = struct.unpack("<QQ", e[32:48])
        parts[e[56:128].decode("utf-16le").rstrip("\0")] = Partition(
            first=first, number=i + 1, sectors=last - first + 1
        )
    primary = mbr + header(alternate=backup_lba, at=2, my=1) + bytes(new)
    backup = bytes(new) + header(alternate=1, at=backup_lba - 32, my=backup_lba)
    return primary, backup, backup_lba - 32, parts
