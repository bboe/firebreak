from __future__ import annotations

import struct
import zlib
from typing import NamedTuple

from firebreak.ui import _die

PARTITION_TABLE_HEADER_SIZE = 92
STOCK_PARTITIONS = 16


class Partition(NamedTuple):
    first: int
    number: int
    sectors: int

    @property
    def size(self) -> int:
        return self.sectors * 512


def gpt_intact(*, entries: bytes, header: bytes) -> bool:
    if (
        header[:8] != b"EFI PART"
        or struct.unpack("<I", header[12:16])[0] != PARTITION_TABLE_HEADER_SIZE
    ):
        return False
    if struct.unpack("<II", header[80:88]) != (128, 128):
        return False
    unsigned_header = bytearray(header[:92])
    unsigned_header[16:20] = bytes(4)
    return (
        zlib.crc32(unsigned_header) & 0xFFFFFFFF
        == struct.unpack("<I", header[16:20])[0]
        and zlib.crc32(entries[: 128 * 128]) & 0xFFFFFFFF
        == struct.unpack("<I", header[88:92])[0]
    )


def stock_gpt(  # ruff: ignore[too-many-locals]
    *, raw: bytes
) -> tuple[bytes, bytes, int, dict[str, Partition]]:
    master_boot_record, table_header, entries = (
        raw[:512],
        bytearray(raw[512:1024]),
        raw[1024 : 1024 + 128 * 128],
    )
    if not gpt_intact(entries=entries, header=table_header):
        _die(message="neither copy of the Dot's partition table is intact")
    last_usable = struct.unpack("<Q", table_header[48:56])[0]
    backup_address = max(struct.unpack("<QQ", table_header[24:40]))
    names = [
        entries[index * 128 + 56 : (index + 1) * 128]
        .decode(encoding="utf-16le")
        .rstrip("\0")
        for index in range(128)
    ]
    amonet = any(name.endswith("_x") for name in names)
    new = bytearray(128 * 128)
    count = 0
    for index in range(128):
        entry = bytearray(entries[index * 128 : (index + 1) * 128])
        if entry[:16] == b"\0" * 16:
            continue
        name = names[index]
        if amonet and name in {"boot_a", "boot_b"}:
            continue
        if name.endswith("_x"):
            name = name[:-2]
            entry[56:128] = name.encode(encoding="utf-16le").ljust(72, b"\0")
        if name == "userdata":
            entry[40:48] = struct.pack("<Q", last_usable)
        new[count * 128 : (count + 1) * 128] = entry
        count += 1
    if count != STOCK_PARTITIONS:
        _die(
            message=f"the stock table would have {count} partitions,"
            f" not {STOCK_PARTITIONS}"
        )
    entries_checksum = zlib.crc32(new) & 0xFFFFFFFF

    def header(
        *, alternate_address: int, entries_address: int, own_address: int
    ) -> bytes:
        header_bytes = bytearray(table_header[:92])
        header_bytes[16:20] = b"\0" * 4
        header_bytes[24:32] = struct.pack("<Q", own_address)
        header_bytes[32:40] = struct.pack("<Q", alternate_address)
        header_bytes[72:80] = struct.pack("<Q", entries_address)
        header_bytes[88:92] = struct.pack("<I", entries_checksum)
        header_bytes[16:20] = struct.pack("<I", zlib.crc32(header_bytes) & 0xFFFFFFFF)
        return bytes(header_bytes).ljust(512, b"\0")

    parts = {}
    for index in range(count):
        entry = new[index * 128 : (index + 1) * 128]
        first, last = struct.unpack("<QQ", entry[32:48])
        parts[entry[56:128].decode(encoding="utf-16le").rstrip("\0")] = Partition(
            first=first, number=index + 1, sectors=last - first + 1
        )
    primary = (
        master_boot_record
        + header(alternate_address=backup_address, entries_address=2, own_address=1)
        + bytes(new)
    )
    backup = bytes(new) + header(
        alternate_address=1,
        entries_address=backup_address - 32,
        own_address=backup_address,
    )
    return primary, backup, backup_address - 32, parts
