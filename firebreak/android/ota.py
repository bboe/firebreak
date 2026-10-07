from __future__ import annotations

import bz2
import enum
import lzma
import struct
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

from firebreak.cache import digest
from firebreak.ui import _die, passed

BLOCK_IMAGES = {
    "boot": "boot.img",
    "lk": "images/lk.bin",
    "preloader": "images/preloader.img",
    "tee": "images/tz.img",
}
IMAGES = ("preloader", "lk", "tee", "boot", "system")
PAYLOAD_VERSION = 2
TRANSFER_FIELDS = 2
VARINT_MORE = 0x80


class ExtentField(enum.IntEnum):
    START_BLOCK = 1
    NUM_BLOCKS = 2


class InfoField(enum.IntEnum):
    SIZE = 1
    HASH = 2


class ManifestField(enum.IntEnum):
    BLOCK_SIZE = 3
    PARTITIONS = 13


class OperationField(enum.IntEnum):
    TYPE = 1
    DATA_OFFSET = 2
    DATA_LENGTH = 3
    DST_EXTENTS = 6


class OperationType(enum.IntEnum):
    REPLACE = 0
    REPLACE_BZ = 1
    REPLACE_XZ = 8


class PartitionField(enum.IntEnum):
    NAME = 1
    NEW_INFO = 7
    OPERATIONS = 8


class WireType(enum.IntEnum):
    VARINT = 0
    FIXED64 = 1
    LEN = 2
    FIXED32 = 5


def extract(*, ota: pathlib.Path, work: pathlib.Path) -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    with zipfile.ZipFile(ota) as z:  # ruff: ignore[too-many-nested-blocks]
        if "payload.bin" not in z.namelist():
            extract_blocks(work=work, z=z)
            return
        with z.open("payload.bin") as f:
            h = f.read(24)
            if h[:4] != b"CrAU" or struct.unpack(">Q", h[4:12])[0] != PAYLOAD_VERSION:
                _die(message="the OTA's payload.bin is not a version 2 update payload")
            msize = struct.unpack(">Q", h[12:20])[0]
            sig = struct.unpack(">I", h[20:24])[0]
            manifest = f.read(msize)
        base = 24 + msize + sig
        block = 4096
        partitions = {}
        for fn, _, v in fields(manifest):
            if fn == ManifestField.BLOCK_SIZE:
                block = v
            if fn == ManifestField.PARTITIONS:
                d, ops = {}, []
                for a, _, c in fields(v):
                    if a == PartitionField.OPERATIONS:
                        ops.append(c)
                    else:
                        d[a] = c
                partitions[d[PartitionField.NAME].decode()] = (
                    {a: c for a, _, c in fields(d[PartitionField.NEW_INFO])},
                    ops,
                )
        with z.open("payload.bin") as payload:
            for name in IMAGES:
                if name not in partitions:
                    _die(message=f"the OTA has no {name} image")
                info, ops = partitions[name]
                path = work / (name + ".img")
                if (
                    path.is_file()
                    and digest(kind="sha256", path=path) == info[InfoField.HASH].hex()
                ):
                    passed(f"{name:>{max(map(len, IMAGES))}} matches the manifest")
                    continue
                img = bytearray(info[InfoField.SIZE])
                for op in ops:
                    o, extents = {}, []
                    for a, _, c in fields(op):
                        if a == OperationField.DST_EXTENTS:
                            extents.append({x: y for x, _, y in fields(c)})
                        else:
                            o[a] = c
                    payload.seek(base + o.get(OperationField.DATA_OFFSET, 0))
                    blob = payload.read(o.get(OperationField.DATA_LENGTH, 0))
                    kind = o[OperationField.TYPE]
                    if kind == OperationType.REPLACE:
                        raw = blob
                    elif kind == OperationType.REPLACE_BZ:
                        raw = bz2.decompress(blob)
                    elif kind == OperationType.REPLACE_XZ:
                        raw = lzma.decompress(blob)
                    else:
                        _die(message=f"{name} has op type {kind}")
                    pos = 0
                    for e in extents:
                        n = e[ExtentField.NUM_BLOCKS] * block
                        at = e.get(ExtentField.START_BLOCK, 0) * block
                        img[at : at + n] = raw[pos : pos + n]
                        pos += n
                path.write_bytes(memoryview(img)[: info[InfoField.SIZE]])
                if digest(kind="sha256", path=path) != info[InfoField.HASH].hex():
                    _die(message=name + " does not match the manifest")
                passed(f"{name:>{max(map(len, IMAGES))}} matches the manifest")


def extract_blocks(*, work: pathlib.Path, z: zipfile.ZipFile) -> None:
    for name, member in BLOCK_IMAGES.items():
        data = z.read(member)
        if name != "preloader":
            data += bytes(-len(data) % 4096)
        (work / (name + ".img")).write_bytes(data)
        passed(f"{name:>{max(map(len, IMAGES))}} taken from the OTA")
    commands, size = transfer_list(z.read("system.transfer.list").decode())
    with (work / "system.img").open("wb") as out, z.open("system.new.dat") as dat:
        out.truncate(size)
        for verb, ranges in commands:
            if verb != "new":
                continue
            for start, end in ranges:
                out.seek(start)
                for offset in range(start, end, 1 << 20):
                    n = min(1 << 20, end - offset)
                    chunk = dat.read(n)
                    if len(chunk) != n:
                        _die(message="the OTA's system.new.dat is short")
                    out.write(chunk)
        if dat.read(1):
            _die(message="the OTA's system.new.dat outlasts its transfer list")
    passed(f"{'system':>{max(map(len, IMAGES))}} built from the transfer list")


def fields(b: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    i = 0
    while i < len(b):
        k, i = varint(b=b, i=i)
        fn, wt = k >> 3, k & 7
        if wt == WireType.VARINT:
            v, i = varint(b=b, i=i)
        elif wt == WireType.LEN:
            n, i = varint(b=b, i=i)
            v = b[i : i + n]
            i += n
        elif wt == WireType.FIXED64:
            v = b[i : i + 8]
            i += 8
        elif wt == WireType.FIXED32:
            v = b[i : i + 4]
            i += 4
        else:
            _die(message=f"the OTA's manifest has wire type {wt}")
        yield fn, wt, v


def transfer_command(words: list[str]) -> tuple[str, list[tuple[int, int]]]:
    numbers = words[1].split(",") if len(words) == TRANSFER_FIELDS else []
    if words[0] not in {"erase", "new", "zero"} or not all(
        n.isdigit() for n in numbers
    ):
        _die(message=f"the OTA's transfer list has a {words[0]!r} command")
    bounds = [int(n) * 4096 for n in numbers[1:]]
    ranges = list(zip(bounds[::2], bounds[1::2]))
    if any(start >= end for start, end in ranges):
        _die(message="the OTA's transfer list has an empty or reversed range")
    return words[0], ranges


def transfer_list(text: str) -> tuple[list[tuple[str, list[tuple[int, int]]]], int]:
    lines = text.split("\n")
    if lines[0] not in {"3", "4"}:
        _die(message=f"the OTA's transfer list is version {lines[0]}")
    commands = [
        transfer_command(words)
        for words in (line.split() for line in lines[4:])
        if words
    ]
    size = 0
    for start, end in sorted(r for _, ranges in commands for r in ranges):
        if start > size:
            _die(message="the OTA's transfer list leaves a gap")
        size = max(size, end)
    if not size:
        _die(message="the OTA's transfer list writes nothing")
    written = 0
    for start, end in sorted(
        r for verb, ranges in commands if verb != "erase" for r in ranges
    ):
        if start < written:
            _die(message="the OTA's transfer list writes a block twice")
        written = end
    return commands, size


def varint(*, b: bytes, i: int) -> tuple[int, int]:
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if x < VARINT_MORE:
            return r, i
