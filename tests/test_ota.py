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


def block_ota(path: pathlib.Path, transfer: str, dat: bytes) -> pathlib.Path:
    members = {member: image(name, 1000) for name, member in ota.BLOCK_IMAGES.items()}
    return write_ota(
        path,
        {**members, "system.new.dat": dat, "system.transfer.list": transfer.encode()},
    )


def extent(*, blocks: int, start: int) -> bytes:
    head = number(ota.ExtentField.START_BLOCK, start) if start else b""
    return nested(
        ota.OperationField.DST_EXTENTS,
        head + number(ota.ExtentField.NUM_BLOCKS, blocks),
    )


def image(name: str, size: int) -> bytes:
    seed = hashlib.sha256(name.encode()).digest()
    return (seed * (size // len(seed) + 1))[:size]


IMAGES = {
    "boot": image("boot", BLOCK + 1),
    "lk": image("lk", 2 * BLOCK),
    "preloader": image("preloader", 5000),
    "system": image("system", 3 * BLOCK),
    "tee": image("tee", 3000),
}


def nested(field: int, body: bytes) -> bytes:
    return varint(field << 3 | 2) + varint(len(body)) + body


def number(field: int, n: int) -> bytes:
    return varint(field << 3) + varint(n)


def payload(
    images: dict[str, bytes],
    kinds: dict[str, int],
    *,
    stale: str = "",
    version: int = 2,
) -> bytes:
    manifest = number(ota.ManifestField.BLOCK_SIZE, BLOCK)
    data = b""
    for name, body in images.items():
        padded = body.ljust(-(-len(body) // BLOCK) * BLOCK, b"\0")
        kind = kinds.get(name, ota.OperationType.REPLACE)
        blob = {
            ota.OperationType.REPLACE_BZ: bz2.compress,
            ota.OperationType.REPLACE_XZ: lzma.compress,
        }.get(kind, lambda b: b)(padded)
        blocks = len(padded) // BLOCK
        if name == "system":
            extents = extent(blocks=1, start=blocks - 1) + extent(
                blocks=blocks - 1, start=0
            )
            blob = padded[-BLOCK:] + padded[:-BLOCK]
        else:
            extents = extent(blocks=blocks, start=0)
        operation = (
            number(ota.OperationField.TYPE, kind)
            + number(ota.OperationField.DATA_OFFSET, len(data))
            + number(ota.OperationField.DATA_LENGTH, len(blob))
            + extents
        )
        info = number(ota.InfoField.SIZE, len(body)) + nested(
            ota.InfoField.HASH, hashlib.sha256(body + b"x" * (name == stale)).digest()
        )
        manifest += nested(
            ota.ManifestField.PARTITIONS,
            nested(ota.PartitionField.NAME, name.encode())
            + nested(ota.PartitionField.NEW_INFO, info)
            + nested(ota.PartitionField.OPERATIONS, operation),
        )
        data += blob
    head = b"CrAU" + struct.pack(">QQI", version, len(manifest), 0)
    return head + manifest + data


def test_extract(capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path) -> None:
    update = write_ota(tmp_path / "ota.zip", {"payload.bin": payload(IMAGES, KINDS)})
    ota.extract(ota=update, work=tmp_path)
    for name, body in IMAGES.items():
        assert (tmp_path / f"{name}.img").read_bytes() == body
    assert capsys.readouterr().out.count("matches the manifest") == 5
    (tmp_path / "boot.img").write_bytes(b"stale")
    ota.extract(ota=update, work=tmp_path)
    assert (tmp_path / "boot.img").read_bytes() == IMAGES["boot"]


def test_extract_blocks(
    capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    dat = image("a", BLOCK) + image("b", 2 * BLOCK)
    transfer = "4\n6\n0\n0\nerase 2,0,6\nnew 2,4,6\nnew 2,0,1\nzero 2,1,4\n"
    ota.extract(ota=block_ota(tmp_path / "ota.zip", transfer, dat), work=tmp_path)
    for name in ota.BLOCK_IMAGES:
        want = image(name, 1000)
        if name != "preloader":
            want += bytes(BLOCK - 1000)
        assert (tmp_path / f"{name}.img").read_bytes() == want
    system = (tmp_path / "system.img").read_bytes()
    assert len(system) == 6 * BLOCK
    assert system[4 * BLOCK :] == dat[: 2 * BLOCK]
    assert system[:BLOCK] == dat[2 * BLOCK :]
    assert system[BLOCK : 4 * BLOCK] == bytes(3 * BLOCK)
    assert "system built from the transfer list" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("dat", "message"),
    [
        (bytes(BLOCK), "system.new.dat is short"),
        (bytes(3 * BLOCK), "system.new.dat outlasts its transfer list"),
    ],
)
def test_extract_blocks_checks_the_data(
    dat: bytes, message: str, tmp_path: pathlib.Path
) -> None:
    update = block_ota(tmp_path / "ota.zip", "4\n2\n0\n0\nnew 2,0,2\n", dat)
    with pytest.raises(SystemExit, match=message):
        ota.extract(ota=update, work=tmp_path)


def test_extract_checks_the_hash(tmp_path: pathlib.Path) -> None:
    body = payload(IMAGES, KINDS, stale="system")
    update = write_ota(tmp_path / "ota.zip", {"payload.bin": body})
    with pytest.raises(SystemExit, match="system does not match the manifest"):
        ota.extract(ota=update, work=tmp_path)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"version": 1}, "not a version 2 update payload"),
        ({"drop": "tee"}, "the OTA has no tee image"),
        ({"kind": 4}, "lk has op type 4"),
    ],
)
def test_extract_fails(
    change: dict[str, object], message: str, tmp_path: pathlib.Path
) -> None:
    images = {k: v for k, v in IMAGES.items() if k != change.get("drop")}
    kinds = {**KINDS, "lk": change.get("kind", KINDS["lk"])}
    body = payload(images, kinds, version=int(change.get("version", 2)))
    update = write_ota(tmp_path / "ota.zip", {"payload.bin": body})
    with pytest.raises(SystemExit, match=message):
        ota.extract(ota=update, work=tmp_path)


def test_fields() -> None:
    message = (
        number(1, 300)
        + nested(2, b"hi")
        + varint(3 << 3 | 1)
        + bytes(range(8))
        + varint(4 << 3 | 5)
        + b"abcd"
    )
    assert list(ota.fields(message)) == [
        (1, 0, 300),
        (2, 2, b"hi"),
        (3, 1, bytes(range(8))),
        (4, 5, b"abcd"),
    ]
    with pytest.raises(SystemExit, match="wire type 3"):
        list(ota.fields(varint(5 << 3 | 3)))


def test_transfer_list() -> None:
    commands, size = ota.transfer_list("3\n4\n0\n0\nerase 2,0,4\nnew 4,0,1,2,4\n")
    assert size == 4 * BLOCK
    assert commands == [
        ("erase", [(0, 4 * BLOCK)]),
        ("new", [(0, BLOCK), (2 * BLOCK, 4 * BLOCK)]),
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("2\n1\n0\n0\nnew 2,0,1\n", "transfer list is version 2"),
        ("4\n1\n0\n0\nmove 2,0,1\n", "has a 'move' command"),
        ("4\n1\n0\n0\nnew 2,0,x\n", "has a 'new' command"),
        ("4\n1\n0\n0\nnew 2,1,1\n", "an empty or reversed range"),
        ("4\n1\n0\n0\nnew 2,1,2\n", "leaves a gap"),
        ("4\n1\n0\n0\n", "writes nothing"),
        ("4\n1\n0\n0\nnew 2,0,2\nzero 2,1,2\n", "writes a block twice"),
    ],
)
def test_transfer_list_fails(message: str, text: str) -> None:
    with pytest.raises(SystemExit, match=message):
        ota.transfer_list(text)


def test_varint() -> None:
    assert ota.varint(b=b"\x00\xac\x02", i=1) == (300, 3)


def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        low, n = n & 0x7F, n >> 7
        out.append(low | (0x80 if n else 0))
        if not n:
            return bytes(out)


def write_ota(path: pathlib.Path, members: dict[str, bytes]) -> pathlib.Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return path
