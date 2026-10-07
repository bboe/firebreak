from __future__ import annotations

import bz2
import hashlib
import lzma
import struct
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak.android import ota

if TYPE_CHECKING:
    import pathlib

BLOCK = 4096
KINDS = {
    "lk": ota.OperationType.REPLACE_BZ,
    "tee": ota.OperationType.REPLACE_XZ,
}


def block_ota(*, new_data: bytes, path: pathlib.Path, transfer: str) -> pathlib.Path:
    members = {
        member: image(name=name, size=1000) for name, member in ota.BLOCK_IMAGES.items()
    }
    return write_ota(
        members={
            **members,
            "system.new.dat": new_data,
            "system.transfer.list": transfer.encode(),
        },
        path=path,
    )


def extent(*, blocks: int, start: int) -> bytes:
    head = number(field=ota.ExtentField.START_BLOCK, value=start) if start else b""
    return nested(
        body=head + number(field=ota.ExtentField.NUM_BLOCKS, value=blocks),
        field=ota.OperationField.DST_EXTENTS,
    )


def image(*, name: str, size: int) -> bytes:
    seed = hashlib.sha256(name.encode()).digest()
    return (seed * (size // len(seed) + 1))[:size]


IMAGES = {
    "boot": image(name="boot", size=BLOCK + 1),
    "lk": image(name="lk", size=2 * BLOCK),
    "preloader": image(name="preloader", size=5000),
    "system": image(name="system", size=3 * BLOCK),
    "tee": image(name="tee", size=3000),
}


def nested(*, body: bytes, field: int) -> bytes:
    return varint(value=field << 3 | 2) + varint(value=len(body)) + body


def number(*, field: int, value: int) -> bytes:
    return varint(value=field << 3) + varint(value=value)


def payload(  # ruff: ignore[too-many-arguments]
    *,
    block_size: int = BLOCK,
    images: dict[str, bytes],
    kinds: dict[str, int],
    omit_block_size: bool = False,
    short: str = "",
    stale: str = "",
    version: int = 2,
) -> bytes:
    manifest = (
        b""
        if omit_block_size
        else number(field=ota.ManifestField.BLOCK_SIZE, value=block_size)
    )
    data = b""
    for name, body in images.items():
        padded = body.ljust(-(-len(body) // block_size) * block_size, b"\0")
        kind = kinds.get(name, ota.OperationType.REPLACE)
        blob = {
            ota.OperationType.REPLACE_BZ: bz2.compress,
            ota.OperationType.REPLACE_XZ: lzma.compress,
        }.get(kind, lambda *, data: data)(data=padded)
        blocks = len(padded) // block_size
        if name == "system":
            extents = extent(blocks=1, start=blocks - 1) + extent(
                blocks=blocks - 1, start=0
            )
            blob = padded[-block_size:] + padded[:-block_size]
        else:
            extents = extent(blocks=blocks, start=0)
        if name == short:
            blob = blob[:-block_size]
        offset = (
            number(field=ota.OperationField.DATA_OFFSET, value=len(data))
            if data
            else b""
        )
        operation = (
            number(field=ota.OperationField.TYPE, value=kind)
            + offset
            + number(field=ota.OperationField.DATA_LENGTH, value=len(blob))
            + extents
        )
        info = number(field=ota.InfoField.SIZE, value=len(body)) + nested(
            body=hashlib.sha256(body + b"x" * (name == stale)).digest(),
            field=ota.InfoField.HASH,
        )
        manifest += nested(
            body=nested(body=name.encode(), field=ota.PartitionField.NAME)
            + nested(body=info, field=ota.PartitionField.NEW_INFO)
            + nested(body=operation, field=ota.PartitionField.OPERATIONS),
            field=ota.ManifestField.PARTITIONS,
        )
        data += blob
    head = b"CrAU" + struct.pack(">QQI", version, len(manifest), 0)
    return head + manifest + data


def test_extract(*, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path) -> None:
    update = write_ota(
        members={"payload.bin": payload(images=IMAGES, kinds=KINDS)},
        path=tmp_path / "ota.zip",
    )
    ota.extract(update=update, work=tmp_path)
    for name, body in IMAGES.items():
        assert (tmp_path / f"{name}.img").read_bytes() == body
    assert capsys.readouterr().out.count("matches the manifest") == 5
    (tmp_path / "boot.img").write_bytes(data=b"stale")
    ota.extract(update=update, work=tmp_path)
    assert (tmp_path / "boot.img").read_bytes() == IMAGES["boot"]


def test_extract_blocks(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    new_data = image(name="a", size=BLOCK) + image(name="b", size=2 * BLOCK)
    transfer = "4\n6\n0\n0\nerase 2,0,6\nnew 2,4,6\nnew 2,0,1\nzero 2,1,4\n"
    ota.extract(
        update=block_ota(
            new_data=new_data, path=tmp_path / "ota.zip", transfer=transfer
        ),
        work=tmp_path,
    )
    for name in ota.BLOCK_IMAGES:
        want = image(name=name, size=1000)
        if name != "preloader":
            want += bytes(BLOCK - 1000)
        assert (tmp_path / f"{name}.img").read_bytes() == want
    system = (tmp_path / "system.img").read_bytes()
    assert len(system) == 6 * BLOCK
    assert system[4 * BLOCK :] == new_data[: 2 * BLOCK]
    assert system[:BLOCK] == new_data[2 * BLOCK :]
    assert system[BLOCK : 4 * BLOCK] == bytes(3 * BLOCK)
    assert "system built from the transfer list" in capsys.readouterr().out


@pytest.mark.parametrize(
    argnames=("new_data", "message"),
    argvalues=[
        (bytes(BLOCK), "system.new.dat is short"),
        (bytes(3 * BLOCK), "system.new.dat outlasts its transfer list"),
    ],
)
def test_extract_blocks_checks_the_data(
    *, message: str, new_data: bytes, tmp_path: pathlib.Path
) -> None:
    update = block_ota(
        new_data=new_data, path=tmp_path / "ota.zip", transfer="4\n2\n0\n0\nnew 2,0,2\n"
    )
    with pytest.raises(expected_exception=SystemExit, match=message):
        ota.extract(update=update, work=tmp_path)


def test_extract_catches_a_short_blob(*, tmp_path: pathlib.Path) -> None:
    body = payload(images=IMAGES, kinds=KINDS, short="system")
    update = write_ota(members={"payload.bin": body}, path=tmp_path / "ota.zip")
    with pytest.raises(
        expected_exception=SystemExit, match="system does not match the manifest"
    ):
        ota.extract(update=update, work=tmp_path)


def test_extract_checks_the_hash(*, tmp_path: pathlib.Path) -> None:
    body = payload(images=IMAGES, kinds=KINDS, stale="system")
    update = write_ota(members={"payload.bin": body}, path=tmp_path / "ota.zip")
    with pytest.raises(
        expected_exception=SystemExit, match="system does not match the manifest"
    ):
        ota.extract(update=update, work=tmp_path)


def test_extract_defaults_the_block_size(*, tmp_path: pathlib.Path) -> None:
    body = payload(block_size=BLOCK, images=IMAGES, kinds=KINDS, omit_block_size=True)
    update = write_ota(members={"payload.bin": body}, path=tmp_path / "ota.zip")
    ota.extract(update=update, work=tmp_path)
    for name, image_bytes in IMAGES.items():
        assert (tmp_path / f"{name}.img").read_bytes() == image_bytes


@pytest.mark.parametrize(
    argnames=("change", "message"),
    argvalues=[
        ({"version": 1}, "not a version 2 update payload"),
        ({"drop": "tee"}, "the OTA has no tee image"),
        ({"kind": 4}, "lk has op type 4"),
    ],
)
def test_extract_fails(
    *, change: dict[str, object], message: str, tmp_path: pathlib.Path
) -> None:
    images = {key: value for key, value in IMAGES.items() if key != change.get("drop")}
    kinds = {**KINDS, "lk": change.get("kind", KINDS["lk"])}
    body = payload(images=images, kinds=kinds, version=int(change.get("version", 2)))
    update = write_ota(members={"payload.bin": body}, path=tmp_path / "ota.zip")
    with pytest.raises(expected_exception=SystemExit, match=message):
        ota.extract(update=update, work=tmp_path)


def test_extract_reads_another_block_size_and_skips_other_partitions(
    *, tmp_path: pathlib.Path
) -> None:
    images = {**IMAGES, "vendor": image(name="vendor", size=100)}
    body = payload(block_size=512, images=images, kinds=KINDS)
    update = write_ota(members={"payload.bin": body}, path=tmp_path / "ota.zip")
    ota.extract(update=update, work=tmp_path)
    for name, body in IMAGES.items():
        assert (tmp_path / f"{name}.img").read_bytes() == body
    assert not (tmp_path / "vendor.img").exists()


def test_fields() -> None:
    message = (
        number(field=1, value=300)
        + nested(body=b"hi", field=2)
        + varint(value=3 << 3 | 1)
        + bytes(range(8))
        + varint(value=4 << 3 | 5)
        + b"abcd"
    )
    assert list(ota.fields(message=message)) == [
        (1, 0, 300),
        (2, 2, b"hi"),
        (3, 1, bytes(range(8))),
        (4, 5, b"abcd"),
    ]
    with pytest.raises(expected_exception=SystemExit, match="wire type 3"):
        list(ota.fields(message=varint(value=5 << 3 | 3)))


@pytest.mark.parametrize(
    argnames=("message", "error"),
    argvalues=[
        (b"\x08", "ends inside a number"),
        (b"\x88", "ends inside a number"),
        (b"\x12\x05ab", "ends inside a field"),
        (b"\x19" + bytes(4), "ends inside a field"),
        (b"\x25ab", "ends inside a field"),
    ],
)
def test_fields_stops_at_a_cut_manifest(*, error: str, message: bytes) -> None:
    with pytest.raises(expected_exception=SystemExit, match=error):
        list(ota.fields(message=message))


def test_transfer_list() -> None:
    commands, size = ota.transfer_list(text="3\n4\n0\n0\nerase 2,0,4\nnew 4,0,1,2,4\n")
    assert size == 4 * BLOCK
    assert commands == [
        ("erase", [(0, 4 * BLOCK)]),
        ("new", [(0, BLOCK), (2 * BLOCK, 4 * BLOCK)]),
    ]


@pytest.mark.parametrize(
    argnames=("text", "message"),
    argvalues=[
        ("2\n1\n0\n0\nnew 2,0,1\n", "transfer list is version 2"),
        ("4\n1\n0\n0\nmove 2,0,1\n", "has a 'move' command"),
        ("4\n1\n0\n0\nnew 2,0,x\n", "has a 'new' command"),
        ("4\n1\n0\n0\nnew 2,1,1\n", "an empty or reversed range"),
        ("4\n1\n0\n0\nnew 2,1,2\n", "leaves a gap"),
        ("4\n1\n0\n0\n", "writes nothing"),
        ("4\n1\n0\n0\nnew 2,0,2\nzero 2,1,2\n", "writes a block twice"),
    ],
)
def test_transfer_list_fails(*, message: str, text: str) -> None:
    with pytest.raises(expected_exception=SystemExit, match=message):
        ota.transfer_list(text=text)


def test_varint() -> None:
    assert ota.varint(data=b"\x00\xac\x02", index=1) == (300, 3)


def varint(*, value: int) -> bytes:
    encoded = bytearray()
    while True:
        low, value = value & 0x7F, value >> 7
        encoded.append(low | (0x80 if value else 0))
        if not value:
            return bytes(encoded)


def write_ota(*, members: dict[str, bytes], path: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(file=path, mode="w") as archive:
        for name, body in members.items():
            archive.writestr(data=body, zinfo_or_arcname=name)
    return path
