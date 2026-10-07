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


def extract(*, update: pathlib.Path, work: pathlib.Path) -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    with zipfile.ZipFile(file=update) as archive:  # ruff: ignore[too-many-nested-blocks]
        if "payload.bin" not in archive.namelist():
            extract_blocks(archive=archive, work=work)
            return
        with archive.open(name="payload.bin") as stream:
            header = stream.read(24)
            if (
                header[:4] != b"CrAU"
                or struct.unpack(">Q", header[4:12])[0] != PAYLOAD_VERSION
            ):
                _die(message="the OTA's payload.bin is not a version 2 update payload")
            manifest_size = struct.unpack(">Q", header[12:20])[0]
            signature_size = struct.unpack(">I", header[20:24])[0]
            manifest = stream.read(manifest_size)
        data_start = 24 + manifest_size + signature_size
        block_size = 4096
        partitions = {}
        for manifest_field, _, manifest_value in fields(message=manifest):
            if manifest_field == ManifestField.BLOCK_SIZE:
                block_size = manifest_value
            if manifest_field == ManifestField.PARTITIONS:
                details, operations = {}, []
                for field, _, value in fields(message=manifest_value):
                    if field == PartitionField.OPERATIONS:
                        operations.append(value)
                    else:
                        details[field] = value
                partitions[details[PartitionField.NAME].decode()] = (
                    {
                        field: value
                        for field, _, value in fields(
                            message=details[PartitionField.NEW_INFO]
                        )
                    },
                    operations,
                )
        with archive.open(name="payload.bin") as payload:
            for name in IMAGES:
                if name not in partitions:
                    _die(message=f"the OTA has no {name} image")
                info, operations = partitions[name]
                path = work / (name + ".img")
                if (
                    path.is_file()
                    and digest(kind="sha256", path=path) == info[InfoField.HASH].hex()
                ):
                    passed(
                        message=f"{name:>{max(map(len, IMAGES))}} matches the manifest"
                    )
                    continue
                image = bytearray(info[InfoField.SIZE])
                for operation in operations:
                    operation_fields, extents = {}, []
                    for field, _, value in fields(message=operation):
                        if field == OperationField.DST_EXTENTS:
                            extents.append({
                                extent_field: extent_value
                                for extent_field, _, extent_value in fields(
                                    message=value
                                )
                            })
                        else:
                            operation_fields[field] = value
                    payload.seek(
                        data_start + operation_fields.get(OperationField.DATA_OFFSET, 0)
                    )
                    blob = payload.read(
                        operation_fields.get(OperationField.DATA_LENGTH, 0)
                    )
                    kind = operation_fields[OperationField.TYPE]
                    if kind == OperationType.REPLACE:
                        decompressed = blob
                    elif kind == OperationType.REPLACE_BZ:
                        decompressed = bz2.decompress(data=blob)
                    elif kind == OperationType.REPLACE_XZ:
                        decompressed = lzma.decompress(data=blob)
                    else:
                        _die(message=f"{name} has op type {kind}")
                    position = 0
                    for extent in extents:
                        length = extent[ExtentField.NUM_BLOCKS] * block_size
                        offset = extent.get(ExtentField.START_BLOCK, 0) * block_size
                        image[offset : offset + length] = decompressed[
                            position : position + length
                        ]
                        position += length
                path.write_bytes(data=memoryview(object=image)[: info[InfoField.SIZE]])
                if digest(kind="sha256", path=path) != info[InfoField.HASH].hex():
                    _die(message=name + " does not match the manifest")
                passed(message=f"{name:>{max(map(len, IMAGES))}} matches the manifest")


def extract_blocks(*, archive: zipfile.ZipFile, work: pathlib.Path) -> None:
    for name, member in BLOCK_IMAGES.items():
        data = archive.read(name=member)
        if name != "preloader":
            data += bytes(-len(data) % 4096)
        (work / (name + ".img")).write_bytes(data=data)
        passed(message=f"{name:>{max(map(len, IMAGES))}} taken from the OTA")
    commands, size = transfer_list(
        text=archive.read(name="system.transfer.list").decode()
    )
    with (
        (work / "system.img").open(mode="wb") as image,
        archive.open(name="system.new.dat") as new_data,
    ):
        image.truncate(size)
        for verb, ranges in commands:
            if verb != "new":
                continue
            for start, end in ranges:
                image.seek(start)
                for offset in range(start, end, 1 << 20):
                    length = min(1 << 20, end - offset)
                    chunk = new_data.read(length)
                    if len(chunk) != length:
                        _die(message="the OTA's system.new.dat is short")
                    image.write(chunk)
        if new_data.read(1):
            _die(message="the OTA's system.new.dat outlasts its transfer list")
    passed(message=f"{'system':>{max(map(len, IMAGES))}} built from the transfer list")


def fields(*, message: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    index = 0
    while index < len(message):
        key, index = varint(data=message, index=index)
        field_number, wire_type = key >> 3, key & 7
        if wire_type == WireType.VARINT:
            value, index = varint(data=message, index=index)
        elif wire_type == WireType.LEN:
            length, index = varint(data=message, index=index)
            value = message[index : index + length]
            index += length
        elif wire_type == WireType.FIXED64:
            value = message[index : index + 8]
            index += 8
        elif wire_type == WireType.FIXED32:
            value = message[index : index + 4]
            index += 4
        else:
            _die(message=f"the OTA's manifest has wire type {wire_type}")
        if index > len(message):
            _die(message="the OTA's manifest ends inside a field")
        yield field_number, wire_type, value


def transfer_command(*, words: list[str]) -> tuple[str, list[tuple[int, int]]]:
    numbers = words[1].split(sep=",") if len(words) == TRANSFER_FIELDS else []
    if words[0] not in {"erase", "new", "zero"} or not all(
        number.isdigit() for number in numbers
    ):
        _die(message=f"the OTA's transfer list has a {words[0]!r} command")
    bounds = [int(number) * 4096 for number in numbers[1:]]
    ranges = list(zip(bounds[::2], bounds[1::2]))
    if any(start >= end for start, end in ranges):
        _die(message="the OTA's transfer list has an empty or reversed range")
    return words[0], ranges


def transfer_list(*, text: str) -> tuple[list[tuple[str, list[tuple[int, int]]]], int]:
    lines = text.split(sep="\n")
    if lines[0] not in {"3", "4"}:
        _die(message=f"the OTA's transfer list is version {lines[0]}")
    commands = [
        transfer_command(words=words)
        for words in (line.split() for line in lines[4:])
        if words
    ]
    size = 0
    for start, end in sorted(
        block_range for _, ranges in commands for block_range in ranges
    ):
        if start > size:
            _die(message="the OTA's transfer list leaves a gap")
        size = max(size, end)
    if not size:
        _die(message="the OTA's transfer list writes nothing")
    written = 0
    for start, end in sorted(
        block_range
        for verb, ranges in commands
        if verb != "erase"
        for block_range in ranges
    ):
        if start < written:
            _die(message="the OTA's transfer list writes a block twice")
        written = end
    return commands, size


def varint(*, data: bytes, index: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if index >= len(data):
            _die(message="the OTA's manifest ends inside a number")
        byte = data[index]
        index += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if byte < VARINT_MORE:
            return result, index
