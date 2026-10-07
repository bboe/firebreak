from __future__ import annotations

import struct
import zlib

import pytest

from firebreak.android import gpt

DISK = 10000
LAST_USABLE = DISK - 34
OTHERS = [f"part{i}" for i in range(13)]


def check(names: list[str]) -> dict[str, gpt.Partition]:
    primary, backup, backup_at, parts = gpt.stock_gpt(raw(names))
    assert primary[:512] == b"M" * 512
    assert gpt.gpt_intact(entries=primary[1024:], hdr=primary[512:1024])
    assert gpt.gpt_intact(entries=backup[:16384], hdr=backup[16384:])
    assert struct.unpack("<QQ", primary[536:552]) == (1, DISK - 1)
    assert struct.unpack("<QQ", backup[16384 + 24 : 16384 + 40]) == (DISK - 1, 1)
    assert struct.unpack("<Q", backup[16384 + 72 : 16384 + 80])[0] == backup_at
    assert backup_at == DISK - 33
    assert parts["userdata"].first + parts["userdata"].sectors - 1 == LAST_USABLE
    assert [part.number for part in parts.values()] == list(range(1, 17))
    return parts


def entry(name: str, first: int, last: int) -> bytes:
    return (
        b"T" * 16
        + b"U" * 16
        + struct.pack("<QQ", first, last)
        + bytes(8)
        + name.encode("utf-16le").ljust(72, b"\0")
    )


def raw(names: list[str]) -> bytes:
    hdr, entries = table(names)
    return b"M" * 512 + hdr + entries


def table(names: list[str]) -> tuple[bytes, bytes]:
    entries = bytearray(128 * 128)
    first = 34
    for i, name in enumerate(names):
        size = 1000 if name == "userdata" else 100
        entries[i * 128 : (i + 1) * 128] = entry(name, first, first + size - 1)
        first += size
    hdr = bytearray(92)
    hdr[:8] = b"EFI PART"
    hdr[8:12] = b"\0\0\1\0"
    hdr[12:16] = struct.pack("<I", 92)
    hdr[24:40] = struct.pack("<QQ", 1, DISK - 1)
    hdr[40:56] = struct.pack("<QQ", 34, LAST_USABLE)
    hdr[72:80] = struct.pack("<Q", 2)
    hdr[80:88] = struct.pack("<II", 128, 128)
    hdr[88:92] = struct.pack("<I", zlib.crc32(entries) & 0xFFFFFFFF)
    hdr[16:20] = struct.pack("<I", zlib.crc32(hdr) & 0xFFFFFFFF)
    return bytes(hdr).ljust(512, b"\0"), bytes(entries)


def test_gpt_intact() -> None:
    hdr, entries = table(["a"])
    assert gpt.gpt_intact(entries=entries, hdr=hdr)
    assert not gpt.gpt_intact(entries=entries[:-1] + b"x", hdr=hdr)
    assert not gpt.gpt_intact(entries=entries, hdr=b"X" + hdr[1:])
    broken = bytearray(hdr)
    broken[16] ^= 0xFF
    assert not gpt.gpt_intact(entries=entries, hdr=bytes(broken))
    count = bytearray(hdr)
    count[80:84] = struct.pack("<I", 64)
    assert not gpt.gpt_intact(entries=entries, hdr=bytes(count))


def test_stock_gpt_fails() -> None:
    with pytest.raises(SystemExit, match="would have 15 partitions, not 16"):
        gpt.stock_gpt(raw([*OTHERS[:-1], "boot_a", "boot_b", "userdata"]))
    with pytest.raises(SystemExit, match="neither copy"):
        gpt.stock_gpt(b"M" * 512 + b"X" * 512 + bytes(16384))


def test_stock_gpt_keeps_a_stock_table() -> None:
    parts = check([*OTHERS, "boot_a", "boot_b", "userdata"])
    assert list(parts) == [*OTHERS, "boot_a", "boot_b", "userdata"]
    assert parts["boot_a"] == gpt.Partition(first=1334, number=14, sectors=100)
    assert parts["boot_a"].size == 100 * 512


def test_stock_gpt_undoes_amonets_table() -> None:
    names = [*OTHERS, "boot_a", "boot_b", "userdata", "boot_a_x", "boot_b_x"]
    parts = check(names)
    assert list(parts) == [*OTHERS, "userdata", "boot_a", "boot_b"]
    assert parts["boot_a"].first == 34 + 15 * 100 + 1000
