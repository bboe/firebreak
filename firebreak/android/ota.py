from __future__ import annotations

import bz2
import dataclasses
import enum
import lzma
import struct
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator
    from typing import IO

from firebreak.cache import digest
from firebreak.ui import _die, passed

BLOCK_IMAGES = {
    "boot": "boot.img",
    "lk": "images/lk.bin",
    "preloader": "images/preloader.img",
    "tee": "images/tz.img",
}
IMAGES = ("preloader", "lk", "tee", "boot", "system")
LABEL_WIDTH = max(map(len, IMAGES))
PAYLOAD_VERSION = 2
TRANSFER_FIELDS = 2
VARINT_MORE = 0x80


@dataclasses.dataclass(frozen=True)
class BlockRange:
    end: int
    start: int


class ExtentField(enum.IntEnum):
    START_BLOCK = 1
    NUM_BLOCKS = 2


class InfoField(enum.IntEnum):
    SIZE = 1
    HASH = 2


@dataclasses.dataclass(frozen=True)
class Manifest:
    block_size: int
    data_start: int
    partitions: dict[str, PayloadPartition]


class ManifestField(enum.IntEnum):
    BLOCK_SIZE = 3
    PARTITIONS = 13


@dataclasses.dataclass(frozen=True)
class Operation:
    data_length: int
    data_offset: int
    extents: list[tuple[int, int]]
    kind: int


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


@dataclasses.dataclass(frozen=True)
class PayloadPartition:
    info: dict[int, int | bytes]
    operations: list[bytes]


@dataclasses.dataclass(frozen=True)
class TransferCommand:
    ranges: list[BlockRange]
    verb: str


@dataclasses.dataclass(frozen=True)
class TransferList:
    commands: list[TransferCommand]
    size: int


class WireType(enum.IntEnum):
    VARINT = 0
    FIXED64 = 1
    LEN = 2
    FIXED32 = 5


def blob(*, value: int | bytes) -> bytes:
    if isinstance(value, int):
        _die(message="the OTA's manifest has a number where it needs bytes")
        return b""
    return value


def by_start(*, ranges: list[BlockRange]) -> list[BlockRange]:
    return sorted(ranges, key=lambda block_range: block_range.start)


def decompress(*, data: bytes, kind: int, name: str) -> bytes:
    if kind == OperationType.REPLACE:
        return data
    if kind == OperationType.REPLACE_BZ:
        return bz2.decompress(data=data)
    if kind == OperationType.REPLACE_XZ:
        return lzma.decompress(data=data)
    _die(message=f"{name} has op type {kind}")
    return b""


def extract(*, update: pathlib.Path, work: pathlib.Path) -> None:
    with zipfile.ZipFile(file=update) as archive:
        if "payload.bin" in archive.namelist():
            extract_payload(archive=archive, work=work)
        else:
            extract_blocks(archive=archive, work=work)


def extract_blocks(*, archive: zipfile.ZipFile, work: pathlib.Path) -> None:
    for name, member in BLOCK_IMAGES.items():
        data = archive.read(name=member)
        if name != "preloader":
            data += bytes(-len(data) % 4096)
        (work / (name + ".img")).write_bytes(data=data)
        passed(message=f"{name:>{LABEL_WIDTH}} taken from the OTA")
    transfers = transfer_list(text=archive.read(name="system.transfer.list").decode())
    with (
        (work / "system.img").open(mode="wb") as image,
        archive.open(name="system.new.dat") as new_data,
    ):
        image.truncate(transfers.size)
        for command in transfers.commands:
            if command.verb != "new":
                continue
            for block_range in command.ranges:
                image.seek(block_range.start)
                for offset in range(block_range.start, block_range.end, 1 << 20):
                    length = min(1 << 20, block_range.end - offset)
                    chunk = new_data.read(length)
                    if len(chunk) != length:
                        _die(message="the OTA's system.new.dat is short")
                    image.write(chunk)
        if new_data.read(1):
            _die(message="the OTA's system.new.dat outlasts its transfer list")
    passed(message=f"{'system':>{LABEL_WIDTH}} built from the transfer list")


def extract_payload(*, archive: zipfile.ZipFile, work: pathlib.Path) -> None:
    with archive.open(name="payload.bin") as payload:
        manifest = read_manifest(payload=payload)
        for name in IMAGES:
            if name not in manifest.partitions:
                _die(message=f"the OTA has no {name} image")
            partition = manifest.partitions[name]
            want = blob(value=partition.info[InfoField.HASH]).hex()
            path = work / (name + ".img")
            if not path.is_file() or digest(kind="sha256", path=path) != want:
                path.write_bytes(
                    data=image_bytes(
                        manifest=manifest,
                        name=name,
                        partition=partition,
                        payload=payload,
                    )
                )
                if digest(kind="sha256", path=path) != want:
                    _die(message=name + " does not match the manifest")
            passed(message=f"{name:>{LABEL_WIDTH}} matches the manifest")


def field_values(*, message: bytes) -> dict[int, int | bytes]:
    return {field: value for field, _, value in fields(message=message)}


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


def image_bytes(
    *, manifest: Manifest, name: str, partition: PayloadPartition, payload: IO[bytes]
) -> bytearray:
    size = number(value=partition.info[InfoField.SIZE])
    image = bytearray(size)
    for message in partition.operations:
        operation = payload_operation(message=message)
        payload.seek(manifest.data_start + operation.data_offset)
        data = decompress(
            data=payload.read(operation.data_length), kind=operation.kind, name=name
        )
        position = 0
        for start_block, block_count in operation.extents:
            length = block_count * manifest.block_size
            offset = start_block * manifest.block_size
            image[offset : offset + length] = data[position : position + length]
            position += length
    del image[size:]
    return image


def number(*, value: int | bytes) -> int:
    if isinstance(value, bytes):
        _die(message="the OTA's manifest has bytes where it needs a number")
        return 0
    return value


def payload_operation(*, message: bytes) -> Operation:
    values, extents = {}, []
    for field, _, value in fields(message=message):
        if field == OperationField.DST_EXTENTS:
            extent = field_values(message=blob(value=value))
            extents.append((
                number(value=extent.get(ExtentField.START_BLOCK, 0)),
                number(value=extent[ExtentField.NUM_BLOCKS]),
            ))
        else:
            values[field] = value
    return Operation(
        data_length=number(value=values.get(OperationField.DATA_LENGTH, 0)),
        data_offset=number(value=values.get(OperationField.DATA_OFFSET, 0)),
        extents=extents,
        kind=number(value=values[OperationField.TYPE]),
    )


def payload_partition(*, message: bytes) -> tuple[str, PayloadPartition]:
    details, operations = {}, []
    for field, _, value in fields(message=message):
        if field == PartitionField.OPERATIONS:
            operations.append(blob(value=value))
        else:
            details[field] = value
    return blob(value=details[PartitionField.NAME]).decode(), PayloadPartition(
        info=field_values(message=blob(value=details[PartitionField.NEW_INFO])),
        operations=operations,
    )


def read_manifest(*, payload: IO[bytes]) -> Manifest:
    header = payload.read(24)
    if header[:4] != b"CrAU" or struct.unpack(">Q", header[4:12])[0] != PAYLOAD_VERSION:
        _die(message="the OTA's payload.bin is not a version 2 update payload")
    manifest_size, signature_size = struct.unpack(">QI", header[12:24])
    block_size = 4096
    partitions = {}
    for field, _, value in fields(message=payload.read(manifest_size)):
        if field == ManifestField.BLOCK_SIZE:
            block_size = number(value=value)
        elif field == ManifestField.PARTITIONS:
            name, partition = payload_partition(message=blob(value=value))
            partitions[name] = partition
    return Manifest(
        block_size=block_size,
        data_start=24 + manifest_size + signature_size,
        partitions=partitions,
    )


def transfer_command(*, words: list[str]) -> TransferCommand:
    numbers = words[1].split(sep=",") if len(words) == TRANSFER_FIELDS else []
    if words[0] not in {"erase", "new", "zero"} or not all(
        number.isdigit() for number in numbers
    ):
        _die(message=f"the OTA's transfer list has a {words[0]!r} command")
    bounds = [int(number) * 4096 for number in numbers[1:]]
    ranges = [
        BlockRange(end=end, start=start)
        for start, end in zip(bounds[::2], bounds[1::2])
    ]
    if any(block_range.start >= block_range.end for block_range in ranges):
        _die(message="the OTA's transfer list has an empty or reversed range")
    return TransferCommand(ranges=ranges, verb=words[0])


def transfer_list(*, text: str) -> TransferList:
    lines = text.split(sep="\n")
    if lines[0] not in {"3", "4"}:
        _die(message=f"the OTA's transfer list is version {lines[0]}")
    commands = [
        transfer_command(words=words)
        for words in (line.split() for line in lines[4:])
        if words
    ]
    size = 0
    for block_range in by_start(
        ranges=[block_range for command in commands for block_range in command.ranges]
    ):
        if block_range.start > size:
            _die(message="the OTA's transfer list leaves a gap")
        size = max(size, block_range.end)
    if not size:
        _die(message="the OTA's transfer list writes nothing")
    written = 0
    for block_range in by_start(
        ranges=[
            block_range
            for command in commands
            if command.verb != "erase"
            for block_range in command.ranges
        ]
    ):
        if block_range.start < written:
            _die(message="the OTA's transfer list writes a block twice")
        written = block_range.end
    return TransferList(commands=commands, size=size)


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
