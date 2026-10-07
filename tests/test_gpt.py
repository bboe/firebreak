from __future__ import annotations

import struct
import zlib

import pytest

from firebreak.android import gpt

DISK = 10000
LAST_USABLE = DISK - 34
OTHERS = [f"part{index}" for index in range(13)]


def check(*, names: list[str]) -> dict[str, gpt.Partition]:
    table = gpt.stock_gpt(raw=raw(names=names))
    primary, backup, parts = table.primary, table.backup, table.partitions
    assert primary[:512] == b"M" * 512
    assert gpt.gpt_intact(entries=primary[1024:], header=primary[512:1024])
    assert gpt.gpt_intact(entries=backup[:16384], header=backup[16384:])
    assert struct.unpack("<QQ", primary[536:552]) == (1, DISK - 1)
    assert struct.unpack("<QQ", backup[16384 + 24 : 16384 + 40]) == (DISK - 1, 1)
    assert (
        struct.unpack("<Q", backup[16384 + 72 : 16384 + 80])[0] == table.backup_sector
    )
    assert table.backup_sector == DISK - 33
    assert parts["userdata"].first + parts["userdata"].sectors - 1 == LAST_USABLE
    assert [part.number for part in parts.values()] == list(range(1, 17))
    return parts


def entry(*, first: int, last: int, name: str) -> bytes:
    return (
        b"T" * 16
        + b"U" * 16
        + struct.pack("<QQ", first, last)
        + bytes(8)
        + name.encode(encoding="utf-16le").ljust(72, b"\0")
    )


def raw(*, backup: bool = False, names: list[str]) -> bytes:
    header, entries = table(backup=backup, names=names)
    return b"M" * 512 + header + entries


def table(*, backup: bool = False, names: list[str]) -> tuple[bytes, bytes]:
    entries = bytearray(128 * 128)
    first = 34
    for index, name in enumerate(iterable=names):
        size = 1000 if name == "userdata" else 100
        entries[index * 128 : (index + 1) * 128] = entry(
            first=first, last=first + size - 1, name=name
        )
        first += size
    header = bytearray(92)
    header[:8] = b"EFI PART"
    header[8:12] = b"\0\0\1\0"
    header[12:16] = struct.pack("<I", 92)
    own, alternate, entries_address = (
        (DISK - 1, 1, DISK - 33) if backup else (1, DISK - 1, 2)
    )
    header[24:40] = struct.pack("<QQ", own, alternate)
    header[40:56] = struct.pack("<QQ", 34, LAST_USABLE)
    header[72:80] = struct.pack("<Q", entries_address)
    header[80:88] = struct.pack("<II", 128, 128)
    header[88:92] = struct.pack("<I", zlib.crc32(entries) & 0xFFFFFFFF)
    header[16:20] = struct.pack("<I", zlib.crc32(header) & 0xFFFFFFFF)
    return bytes(header).ljust(512, b"\0"), bytes(entries)


def test_gpt_intact() -> None:
    header, entries = table(names=["a"])
    assert gpt.gpt_intact(entries=entries, header=header)
    assert not gpt.gpt_intact(entries=entries[:-1] + b"x", header=header)
    assert not gpt.gpt_intact(entries=entries, header=b"X" + header[1:])
    broken = bytearray(header)
    broken[16] ^= 0xFF
    assert not gpt.gpt_intact(entries=entries, header=bytes(broken))
    count = bytearray(header)
    count[80:84] = struct.pack("<I", 64)
    assert not gpt.gpt_intact(entries=entries, header=bytes(count))


def test_stock_gpt_fails() -> None:
    with pytest.raises(
        expected_exception=SystemExit, match="would have 15 partitions, not 16"
    ):
        gpt.stock_gpt(raw=raw(names=[*OTHERS[:-1], "boot_a", "boot_b", "userdata"]))
    with pytest.raises(expected_exception=SystemExit, match="neither copy"):
        gpt.stock_gpt(raw=b"M" * 512 + b"X" * 512 + bytes(16384))


def test_stock_gpt_keeps_a_stock_table() -> None:
    parts = check(names=[*OTHERS, "boot_a", "boot_b", "userdata"])
    assert list(parts) == [*OTHERS, "boot_a", "boot_b", "userdata"]
    assert parts["boot_a"] == gpt.Partition(first=1334, number=14, sectors=100)
    assert parts["boot_a"].size == 100 * 512


def test_stock_gpt_reads_the_backup_header() -> None:
    names = [*OTHERS, "boot_a", "boot_b", "userdata"]
    assert gpt.stock_gpt(raw=raw(backup=True, names=names)) == gpt.stock_gpt(
        raw=raw(names=names)
    )


def test_stock_gpt_undoes_amonets_table() -> None:
    names = [*OTHERS, "boot_a", "boot_b", "userdata", "boot_a_x", "boot_b_x"]
    parts = check(names=names)
    assert list(parts) == [*OTHERS, "userdata", "boot_a", "boot_b"]
    assert parts["boot_a"].first == 34 + 15 * 100 + 1000
