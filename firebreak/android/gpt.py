from __future__ import annotations

import dataclasses
import struct
import zlib

from firebreak.ui import _die

ENTRY_COUNT = 128
ENTRY_SIZE = 128
ENTRIES_SIZE = ENTRY_COUNT * ENTRY_SIZE
PARTITION_TABLE_HEADER_SIZE = 92
SECTOR_SIZE = 512
STOCK_PARTITIONS = 16


@dataclasses.dataclass(frozen=True)
class Partition:
    first: int
    number: int
    sectors: int

    @property
    def size(self) -> int:
        return self.sectors * SECTOR_SIZE


@dataclasses.dataclass(frozen=True)
class StockTable:
    backup: bytes
    backup_sector: int
    partitions: dict[str, Partition]
    primary: bytes


def entry_name(*, entry: bytes) -> str:
    return entry[56:ENTRY_SIZE].decode(encoding="utf-16le").rstrip("\0")


def gpt_intact(*, entries: bytes, header: bytes) -> bool:
    if (
        header[:8] != b"EFI PART"
        or struct.unpack("<I", header[12:16])[0] != PARTITION_TABLE_HEADER_SIZE
    ):
        return False
    if struct.unpack("<II", header[80:88]) != (ENTRY_COUNT, ENTRY_SIZE):
        return False
    unsigned_header = bytearray(header[:PARTITION_TABLE_HEADER_SIZE])
    unsigned_header[16:20] = bytes(4)
    return (
        zlib.crc32(unsigned_header) == struct.unpack("<I", header[16:20])[0]
        and zlib.crc32(entries[:ENTRIES_SIZE]) == struct.unpack("<I", header[88:92])[0]
    )


def partition_map(*, entries: bytes) -> dict[str, Partition]:
    parts = {}
    for number in range(1, STOCK_PARTITIONS + 1):
        entry = entries[(number - 1) * ENTRY_SIZE : number * ENTRY_SIZE]
        first, last = struct.unpack("<QQ", entry[32:48])
        parts[entry_name(entry=entry)] = Partition(
            first=first, number=number, sectors=last - first + 1
        )
    return parts


def stock_entries(*, entries: bytes, last_usable: int) -> bytes:
    used = [
        entries[offset : offset + ENTRY_SIZE]
        for offset in range(0, ENTRIES_SIZE, ENTRY_SIZE)
        if entries[offset : offset + 16] != bytes(16)
    ]
    amonet = any(entry_name(entry=entry).endswith("_x") for entry in used)
    stock = bytearray()
    for entry in used:
        name = entry_name(entry=entry)
        if amonet and name in {"boot_a", "boot_b"}:
            continue
        restored = bytearray(entry)
        if name.endswith("_x"):
            name = name[:-2]
            restored[56:ENTRY_SIZE] = name.encode(encoding="utf-16le").ljust(72, b"\0")
        if name == "userdata":
            restored[40:48] = struct.pack("<Q", last_usable)
        stock += restored
    count = len(stock) // ENTRY_SIZE
    if count != STOCK_PARTITIONS:
        _die(
            message=f"the stock table would have {count} partitions,"
            f" not {STOCK_PARTITIONS}"
        )
    return bytes(stock.ljust(ENTRIES_SIZE, b"\0"))


def stock_gpt(*, raw: bytes) -> StockTable:
    template = raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    entries = raw[2 * SECTOR_SIZE : 2 * SECTOR_SIZE + ENTRIES_SIZE]
    if not gpt_intact(entries=entries, header=template):
        _die(message="neither copy of the Dot's partition table is intact")
    stock = stock_entries(
        entries=entries, last_usable=struct.unpack("<Q", template[48:56])[0]
    )
    backup_address = max(struct.unpack("<QQ", template[24:40]))
    backup_sector = backup_address - ENTRIES_SIZE // SECTOR_SIZE
    primary_header = table_header(
        alternate_address=backup_address,
        entries=stock,
        entries_address=2,
        own_address=1,
        template=template,
    )
    backup_header = table_header(
        alternate_address=1,
        entries=stock,
        entries_address=backup_sector,
        own_address=backup_address,
        template=template,
    )
    return StockTable(
        backup=stock + backup_header,
        backup_sector=backup_sector,
        partitions=partition_map(entries=stock),
        primary=raw[:SECTOR_SIZE] + primary_header + stock,
    )


def table_header(
    *,
    alternate_address: int,
    entries: bytes,
    entries_address: int,
    own_address: int,
    template: bytes,
) -> bytes:
    header = bytearray(template[:PARTITION_TABLE_HEADER_SIZE])
    header[16:20] = bytes(4)
    header[24:40] = struct.pack("<QQ", own_address, alternate_address)
    header[72:80] = struct.pack("<Q", entries_address)
    header[88:92] = struct.pack("<I", zlib.crc32(entries))
    header[16:20] = struct.pack("<I", zlib.crc32(header))
    return bytes(header.ljust(SECTOR_SIZE, b"\0"))
