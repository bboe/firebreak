from __future__ import annotations

import hashlib
import struct
import sys
import zipfile
from typing import TYPE_CHECKING

import pytest
from test_ota import payload, write_ota
from test_vega import description as swu_description
from test_vega import swu, written

from firebreak import __main__, survey, vega
from firebreak.android import ota
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

BLOCK = 4096

CODE = 0x100
LK_DESCRIPTION = b"\0%s-%s\x0063CB91B\x0020221007_072309\0true\0"
PL_DESCRIPTION = b"\0bd7ae89-20221003_215949\0"
PRINT = 0x80
PROPERTIES = (
    b"# comment=x\nro.build.version.name=Fire OS 6.5.7.2 (NS6572/6426)\n"
    b"ro.product.device=biscuit_puffin\nro.product.model=AEOBC\nno value\n"
)
TEXT = 0x400
VERSION = 0x300
try:
    import brotli
except ImportError:
    brotli = None

NEEDS_BROTLI = pytest.mark.skipif(brotli is None, reason="brotli is not installed")


def bl(*, at: int, target: int) -> bytes:
    offset = (target - (at + 4)) & 0x1FFFFFF
    sign = offset >> 24
    first = 0xF000 | sign << 10 | (offset >> 12) & 0x3FF
    jump1 = (1 - ((offset >> 23) & 1)) ^ sign
    jump2 = (1 - ((offset >> 22) & 1)) ^ sign
    second = 0xD000 | jump1 << 13 | jump2 << 11 | (offset >> 1) & 0x7FF
    return struct.pack("<HH", first, second)


def block_update(
    *,
    packed: bool = False,
    path: pathlib.Path,
    preloader_name: str = "images/preloader.img",
    properties: bytes = PROPERTIES,
    vendor: bool = False,
    **images: bytes,
) -> pathlib.Path:
    members = {
        "boot.img": b"boot",
        "images/lk.bin": lk(),
        preloader_name: preloader(),
        "images/tz.img": tee(),
        "system.new.dat": b"s" * BLOCK,
        "system.transfer.list": b"4\n1\n0\n0\nnew 2,1,2\nzero 2,0,1\n",
        survey.PROPERTIES: properties,
    }
    if packed:
        members["system.new.dat.br"] = brotli.compress(members.pop("system.new.dat"))
    if vendor:
        members["vendor.new.dat.br"] = brotli.compress(b"v" * BLOCK)
        members["vendor.transfer.list"] = b"4\n1\n0\n0\nnew 2,0,1\n"
    for name, body in images.items():
        member = preloader_name if name == "preloader" else ota.BLOCK_IMAGES[name][0]
        members[member] = body
    return write_ota(members=members, path=path)


def boot0(*, copy: int) -> bytes:
    return bytes(survey.BOOT0_PRELOADER - 1) + bytes([copy]) + preloader()


def fit(*, stamps: tuple[int, ...]) -> bytes:
    strings = b"timestamp\0description\0"
    body = struct.pack(">I", 1) + bytes(4) + struct.pack(">IIII", 3, 4, 10, 0)
    for stamp in stamps:
        body += struct.pack(">IIII", 3, 4, 0, stamp)
    body += struct.pack(">II", 2, 9)
    head = struct.pack(
        ">10I",
        survey.FIT_MAGIC,
        40 + len(body) + len(strings),
        40,
        40 + len(body),
        0,
        17,
        16,
        0,
        len(strings),
        len(body),
    )
    return head + body + strings


def lk(*, version: int = 1) -> bytes:
    return LK_DESCRIPTION + bytes(64) + b"LK" + struct.pack(">H", version) + bytes(8)


def preloader(*, calls: int = 2, function: bytes = b"\x05\x20\x70\x47") -> bytes:
    data = bytearray(0x500)
    pool = 0x120
    data[CODE : CODE + 4] = struct.pack(
        "<HH", 0x4800 | (pool - (CODE + 4)) // 4, 0x4478
    )
    data[pool : pool + 4] = struct.pack("<I", TEXT - (CODE + 2 + 4))
    targets = (PRINT, VERSION)[:calls]
    for index, target in enumerate(targets):
        at = CODE + 4 + 4 * index
        data[at : at + 4] = bl(at=at, target=target)
    data[PRINT : PRINT + 2] = b"\x70\x47"
    data[VERSION : VERSION + len(function)] = function
    data[TEXT : TEXT + len(survey.PL_UPDATE)] = survey.PL_UPDATE
    return bytes(data) + PL_DESCRIPTION


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tee(*, version: int = 0x0102) -> bytes:
    header = b"EET KTM" + bytes(8) + struct.pack(">H", version)
    return bytes(512) + header + bytes(100)


def test_a_backward_branch() -> None:
    first, second = struct.unpack("<HH", bl(at=0x200, target=0x80))
    assert survey.branch_target(at=0x200, first=first, second=second) == PRINT


def test_a_block_ota(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(update=block_update(path=tmp_path / "ota.zip"))
    out = capsys.readouterr().out.splitlines()
    name = "Fire OS 6.5.7.2 (NS6572/6426)"
    system = bytes(BLOCK) + b"s" * BLOCK
    data = tee()
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert out == [
        "OTA                      ota.zip",
        f"build                    {name}",
        "device                   biscuit",
        "model                    AEOBC",
        "lk_build_desc            63cb91b-20221007_072309",
        "pl_build_desc            bd7ae89-20221003_215949",
        "anti-rollback            PL 0x0005, TEE 0x0102, LK 0x0001",
        f"TEE                      {len(data)} bytes, md5 {md5}, sha256 {sha(data)}",
        "",
        "device,model,build,partition,bytes,sha256",
        f"biscuit,AEOBC,Fire OS 6 6426,boot,4,{sha(b'boot')}",
        f"biscuit,AEOBC,Fire OS 6 6426,system,{2 * BLOCK},{sha(system)}",
        f"biscuit,AEOBC,Fire OS 6 6426,lk,{len(lk())},{sha(lk())}",
        f"biscuit,AEOBC,Fire OS 6 6426,tee,{len(data)},{sha(data)}",
        f"biscuit,AEOBC,Fire OS 6 6426,preloader,{len(preloader())},{sha(preloader())}",
    ]


def test_a_block_ota_that_carries_coprocessor_images(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(
        update=write_ota(
            members={
                "boot.img": b"boot",
                "images/cam_vpu1.img": b"vpu1",
                "images/lk.bin": lk(),
                "images/preloader.img": preloader(),
                "images/spmfw.img": b"spm",
                "images/sspm.img": b"sspm",
                "images/tz.img": tee(),
                "system.new.dat": b"s" * BLOCK,
                "system.transfer.list": b"4\n1\n0\n0\nnew 2,1,2\nzero 2,0,1\n",
                survey.PROPERTIES: PROPERTIES,
            },
            path=tmp_path / "ota.zip",
        )
    )
    rows = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("biscuit,")
    ]
    assert [row.split(",")[3] for row in rows] == [
        "boot",
        "system",
        "lk",
        "spmfw",
        "sspm",
        "cam_vpu1",
        "tee",
        "preloader",
    ]


def test_a_block_ota_that_names_its_lk_and_tee_img(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(
        update=write_ota(
            members={
                "boot.img": b"boot",
                "images/lk.img": lk(),
                "images/preloader.img": preloader(),
                "images/tee.img": tee(),
                "system.new.dat": b"s" * BLOCK,
                "system.transfer.list": b"4\n1\n0\n0\nnew 2,1,2\nzero 2,0,1\n",
                survey.PROPERTIES: PROPERTIES,
            },
            path=tmp_path / "ota.zip",
        )
    )
    rows = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("biscuit,")
    ]
    assert [row.split(",")[3] for row in rows] == [
        "boot",
        "system",
        "lk",
        "tee",
        "preloader",
    ]
    assert rows[3].endswith(f",{len(tee())},{sha(tee())}")


def test_a_block_ota_that_names_its_preloader_bin(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(
        update=block_update(
            path=tmp_path / "ota.zip", preloader_name="images/preloader.bin"
        )
    )
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == (
        f"biscuit,AEOBC,Fire OS 6 6426,preloader,{len(preloader())},{sha(preloader())}"
    )


@NEEDS_BROTLI
def test_a_block_ota_with_a_vendor_list_and_no_vendor_data(
    *, tmp_path: pathlib.Path
) -> None:
    update = block_update(path=tmp_path / "ota.zip", vendor=True)
    with zipfile.ZipFile(file=update) as archive:
        members = {
            name: archive.read(name=name)
            for name in archive.namelist()
            if name != "vendor.new.dat.br"
        }
    with pytest.raises(expected_exception=FatalError, match=r"has no vendor\.new\.dat"):
        survey.survey(update=write_ota(members=members, path=tmp_path / "bad.zip"))


def test_a_block_ota_with_bootloader_images(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    update = write_ota(
        members={
            "boot.img": b"boot",
            "images/bootloader": b"esp",
            "images/bootloader_prod": b"esp_prod",
            "system.new.dat": b"s" * BLOCK,
            "system.transfer.list": b"4\n1\n0\n0\nnew 2,1,2\nzero 2,0,1\n",
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out.splitlines()
    system = bytes(BLOCK) + b"s" * BLOCK
    assert out == [
        "OTA                      ota.zip",
        "build                    Fire OS 6.5.7.2 (NS6572/6426)",
        "device                   biscuit",
        "model                    AEOBC",
        "",
        "device,model,build,partition,bytes,sha256",
        f"biscuit,AEOBC,Fire OS 6 6426,boot,4,{sha(b'boot')}",
        f"biscuit,AEOBC,Fire OS 6 6426,system,{2 * BLOCK},{sha(system)}",
        f"biscuit,AEOBC,Fire OS 6 6426,bootloader,3,{sha(b'esp')}",
        f"biscuit,AEOBC,Fire OS 6 6426,bootloader_prod,8,{sha(b'esp_prod')}",
    ]


@NEEDS_BROTLI
def test_a_block_ota_with_brotli_data_and_a_vendor(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(
        update=block_update(packed=True, path=tmp_path / "ota.zip", vendor=True)
    )
    rows = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("biscuit,")
    ]
    assert [row.split(",")[3] for row in rows] == [
        "boot",
        "system",
        "vendor",
        "lk",
        "tee",
        "preloader",
    ]
    assert rows[1].endswith(f",{2 * BLOCK},{sha(bytes(BLOCK) + b's' * BLOCK)}")
    assert rows[2].endswith(f",{BLOCK},{sha(b'v' * BLOCK)}")


@NEEDS_BROTLI
def test_a_block_ota_with_uboot_images(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(
        update=write_ota(
            members={
                "boot.img": b"boot",
                "images/logo.img": b"logo",
                "images/u-boot.bin": b"uboot",
                "images/u-boot.bin.signed": b"uboot signed",
                "odm.new.dat.br": brotli.compress(b"o" * BLOCK),
                "odm.transfer.list": b"4\n1\n0\n0\nnew 2,0,1\n",
                "product.new.dat.br": brotli.compress(b"p" * BLOCK),
                "product.transfer.list": b"4\n1\n0\n0\nnew 2,0,1\n",
                "system.new.dat.br": brotli.compress(b"s" * BLOCK),
                "system.transfer.list": b"4\n1\n0\n0\nnew 2,0,1\n",
                "vbmeta.img": b"vbmeta",
                survey.PROPERTIES: PROPERTIES,
            },
            path=tmp_path / "ota.zip",
        )
    )
    rows = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("biscuit,")
    ]
    assert [row.split(",")[3] for row in rows] == [
        "boot",
        "system",
        "odm",
        "product",
        "uboot",
        "uboot_signed",
        "logo",
        "vbmeta",
    ]
    assert rows[5].endswith(f",12,{sha(b'uboot signed')}")


def test_a_block_ota_without_an_image(*, tmp_path: pathlib.Path) -> None:
    update = write_ota(members={"boot.img": b"boot"}, path=tmp_path / "ota.zip")
    with pytest.raises(
        expected_exception=FatalError, match=r"the OTA has no images/lk\.bin, "
    ):
        survey.survey(update=update)


def test_a_damaged_ota(*, tmp_path: pathlib.Path) -> None:
    update = block_update(path=tmp_path / "ota.zip")
    data = bytearray(update.read_bytes())
    at = data.find(b"bd7ae89")
    data[at : at + 7] = b"0000000"
    update.write_bytes(data=bytes(data))
    with pytest.raises(
        expected_exception=FatalError, match="could not be read: BadZipFile"
    ):
        survey.survey(update=update)


def test_a_damaged_payload_could_not_be_read(*, tmp_path: pathlib.Path) -> None:
    images = {
        "boot": b"b",
        "lk": lk(),
        "preloader": preloader(),
        "system": b"s",
        "tee": tee(),
    }
    body = bytearray(
        payload(images=images, kinds={"tee": ota.OperationType.REPLACE_XZ})
    )
    at = body.find(b"\xfd7zXZ")
    body[at + 20 : at + 40] = bytes(20)
    update = write_ota(members={"payload.bin": bytes(body)}, path=tmp_path / "ota.zip")
    with pytest.raises(expected_exception=FatalError, match="could not be read: LZMA"):
        survey.survey(update=update)


def test_a_file_that_is_not_a_zip(*, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "ota.zip"
    path.write_bytes(data=b"not a zip")
    with pytest.raises(expected_exception=FatalError, match="not an OTA zip"):
        survey.survey(update=path)


def test_a_fit_image_reports_its_root_timestamp() -> None:
    assert (
        survey.fit_build_time(data=fit(stamps=(1721890907, 1800000000)))
        == "20240725_070147"
    )
    assert survey.fit_build_time(data=fit(stamps=())) == "<none>"
    assert survey.fit_build_time(data=bytes(survey.FIT_HEADER.size)) == "<none>"
    assert survey.fit_build_time(data=b"short") == "<none>"


def test_a_fit_image_skips_a_timestamp_outside_its_root_node() -> None:
    strings = b"timestamp\0"
    body = (
        struct.pack(">I", survey.FIT_START)
        + bytes(4)
        + struct.pack(">I", survey.FIT_START)
        + b"sig\0"
        + struct.pack(">IIII", survey.FIT_PROPERTY, 4, 0, 1721890907)
        + struct.pack(">II", survey.FIT_END_NODE, survey.FIT_END_NODE)
        + struct.pack(">I", survey.FIT_STOP)
    )
    head = struct.pack(
        ">10I",
        survey.FIT_MAGIC,
        40 + len(body) + len(strings),
        40,
        40 + len(body),
        0,
        17,
        16,
        0,
        len(strings),
        len(body),
    )
    assert survey.fit_build_time(data=head + body + strings) == "<none>"


def test_a_fit_node_name_that_never_ends() -> None:
    head = struct.pack(">10I", survey.FIT_MAGIC, 52, 40, 52, 0, 17, 16, 0, 0, 12)
    body = struct.pack(">I", survey.FIT_START) + b"\xff" * 8
    assert survey.fit_build_time(data=head + body) == "<none>"


def test_a_literal_search_stops_at_the_start() -> None:
    assert survey.literal(at=0, data=b"\x78\x44", register=0) is None


def test_a_row_quotes_a_comma() -> None:
    assert (
        survey.csv_row("biscuit", "Fire OS 7, beta", 1) == 'biscuit,"Fire OS 7, beta",1'
    )


def test_a_vega_swu(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    survey.survey(update=written(path=tmp_path / "ota.swu"))
    build = "Vega 6401030007120"
    assert capsys.readouterr().out.splitlines() == [
        "OTA                      ota.swu",
        "build                    6401030007120",
        "build_time               20260913_035319",
        "device                   galileo",
        "",
        "device,model,build,partition,bytes,sha256",
        f"galileo,<unknown>,{build},boot,4,b007",
        f"galileo,<unknown>,{build},bootloader_prod,4,f1b",
    ]


def test_a_vega_swu_that_carries_an_image_it_does_not_describe(
    *, tmp_path: pathlib.Path
) -> None:
    update = swu(
        path=tmp_path / "ota.swu",
        **{vega.DESCRIPTION: swu_description().encode()},
        **{"boot.img": b"boot", "prod_fip.bin": b"fip!", "stray.img": b"what"},
    )
    with pytest.raises(
        expected_exception=FatalError, match=r"does not describe stray\.img"
    ):
        survey.survey(update=update)


def test_a_vega_swu_that_is_missing_an_image(*, tmp_path: pathlib.Path) -> None:
    update = swu(
        path=tmp_path / "ota.swu",
        **{vega.DESCRIPTION: swu_description().encode()},
    )
    with pytest.raises(expected_exception=FatalError, match=r"has no boot\.img"):
        survey.survey(update=update)


def test_a_vega_swu_whose_build_time_is_unreadable(*, tmp_path: pathlib.Path) -> None:
    text = swu_description().replace("1789271599", "1789271599000")
    update = written(path=tmp_path / "ota.swu", text=text)
    with pytest.raises(expected_exception=FatalError, match="unreadable build time"):
        survey.survey(update=update)


def test_an_a_b_image_that_does_not_match_its_manifest(
    *, tmp_path: pathlib.Path
) -> None:
    images = {
        "boot": b"b",
        "lk": lk(),
        "preloader": preloader(),
        "system": b"s",
        "tee": tee(),
    }
    update = write_ota(
        members={"payload.bin": payload(images=images, kinds={}, stale="tee")},
        path=tmp_path / "ota.zip",
    )
    with pytest.raises(expected_exception=FatalError, match="tee does not match"):
        survey.survey(update=update)


def test_an_a_b_ota(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    images = {
        "boot": b"b" * (BLOCK + 1),
        "lk": lk(version=2),
        "preloader": preloader(),
        "system": b"y" * 3 * BLOCK,
        "tee": tee(version=0x0103),
    }
    update = write_ota(
        members={
            "payload.bin": payload(images=images, kinds={}),
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    assert "PL 0x0005, TEE 0x0103, LK 0x0002" in out
    for partition in survey.csv_partitions(names=frozenset(images)):
        body = images[partition]
        assert f",{partition},{len(body)},{sha(body)}\n" in out


def test_an_a_b_ota_needs_every_image(*, tmp_path: pathlib.Path) -> None:
    update = write_ota(
        members={"payload.bin": payload(images={"boot": b"b"}, kinds={})},
        path=tmp_path / "ota.zip",
    )
    with pytest.raises(expected_exception=FatalError, match="has no preloader image"):
        survey.survey(update=update)


def test_an_a_b_ota_that_names_two_tees(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    data = tee()
    images = {
        "boot": b"b",
        "lk": lk(),
        "preloader": preloader(),
        "system": b"y" * BLOCK,
        "tee1": data,
        "tee2": data,
    }
    update = write_ota(
        members={
            "payload.bin": payload(images=images, kinds={}),
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert f"TEE                      {len(data)} bytes, md5 {md5}" in out
    assert "PL 0x0005, TEE 0x0102, LK 0x0001" in out
    for partition in ("tee1", "tee2"):
        assert f",{partition},{len(data)},{sha(data)}\n" in out
    assert f",tee,{len(data)}," not in out


def test_an_a_b_ota_whose_boot0_holds_no_preloader(*, tmp_path: pathlib.Path) -> None:
    images = {
        "boot": b"b",
        "lk": lk(),
        "system": b"y" * BLOCK,
        "tee": tee(),
        f"{survey.BOOT0}0": b"short",
    }
    update = write_ota(
        members={"payload.bin": payload(images=images, kinds={})},
        path=tmp_path / "ota.zip",
    )
    with pytest.raises(expected_exception=FatalError, match="holds no preloader"):
        survey.survey(update=update)


def test_an_a_b_ota_whose_two_tees_differ(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    first = tee()
    second = tee(version=0x0103)
    images = {
        "boot": b"b",
        "lk": lk(),
        "preloader": preloader(),
        "system": b"y" * BLOCK,
        "tee1": first,
        "tee2": second,
    }
    update = write_ota(
        members={
            "payload.bin": payload(images=images, kinds={}),
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    assert "tee1, tee2 do not hold the same image" in out
    assert f",tee1,{len(first)},{sha(first)}\n" in out
    assert f",tee2,{len(second)},{sha(second)}\n" in out


def test_an_a_b_ota_with_a_uboot(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    trusted = fit(stamps=(1755154729,))
    images = {
        "boot": b"b",
        "brhgptlk_0": bytes(0x100),
        "brhgptlk_1": bytes(0x100),
        "reserve_0": bytes(BLOCK),
        "system": b"y" * BLOCK,
        "tee1": trusted,
        "tee2": trusted,
        "uboot": fit(stamps=(1721890907,)),
    }
    update = write_ota(
        members={
            "payload.bin": payload(images=images, kinds={}),
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    assert "uboot_build_time         20240725_070147" in out
    assert "tee_build_time           20250814_065849" in out
    assert "lk_build_desc" not in out
    assert "anti-rollback" not in out
    assert "biscuit,AEOBC,Fire OS 6 6426,boot," in out
    for partition, body in images.items():
        assert f",{partition},{len(body)},{sha(body)}\n" in out


def test_an_a_b_ota_with_a_uboot_needs_every_image(*, tmp_path: pathlib.Path) -> None:
    update = write_ota(
        members={
            "payload.bin": payload(
                images={"boot": b"b", "uboot": fit(stamps=(1721890907,))}, kinds={}
            )
        },
        path=tmp_path / "ota.zip",
    )
    with pytest.raises(expected_exception=FatalError, match="has no system"):
        survey.survey(update=update)


def test_an_a_b_ota_with_boot0_images(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    data = tee()
    copies = {f"{survey.BOOT0}{copy}": boot0(copy=copy) for copy in range(4)}
    images = {
        "boot": b"b",
        "lk": lk(),
        "system": b"y" * BLOCK,
        "tee1": data,
        "tee2": data,
        **copies,
    }
    update = write_ota(
        members={
            "payload.bin": payload(images=images, kinds={}),
            survey.PROPERTIES: PROPERTIES,
        },
        path=tmp_path / "ota.zip",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    assert "pl_build_desc            bd7ae89-20221003_215949" in out
    assert "PL 0x0005, TEE 0x0102, LK 0x0001" in out
    for name, body in copies.items():
        assert f",{name},{len(body)},{sha(body)}\n" in out
    assert ",preloader," not in out


def test_an_a_b_ota_with_boot0_images_needs_an_lk(*, tmp_path: pathlib.Path) -> None:
    images = {
        "boot": b"b",
        "system": b"y" * BLOCK,
        f"{survey.BOOT0}0": boot0(copy=0),
    }
    update = write_ota(
        members={"payload.bin": payload(images=images, kinds={})},
        path=tmp_path / "ota.zip",
    )
    with pytest.raises(expected_exception=FatalError, match="has no lk"):
        survey.survey(update=update)


def test_an_ota_that_names_and_marks_nothing(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    update = block_update(
        lk=b"no trailer",
        path=tmp_path / "ota.zip",
        preloader=b"x",
        properties=b"nothing=here\n",
        tee=b"y",
    )
    survey.survey(update=update)
    out = capsys.readouterr().out
    assert "lk_build_desc            <none>" in out
    assert "PL <not found>, TEE <not found>, LK <not found>" in out
    assert "<unknown>,<unknown>,<unnamed>,boot," in out


def test_an_ota_without_build_properties(*, tmp_path: pathlib.Path) -> None:
    update = write_ota(members={"x": b""}, path=tmp_path / "ota.zip")
    with zipfile.ZipFile(file=update) as archive:
        assert survey.build_properties(archive=archive) == {}


def test_build_description_reads_every_form() -> None:
    assert survey.build_description(data=LK_DESCRIPTION) == "63cb91b-20221007_072309"
    assert survey.build_description(data=PL_DESCRIPTION) == "bd7ae89-20221003_215949"
    assert survey.build_description(data=b"\x0020221007_072309\0") == "20221007_072309"
    assert survey.build_description(data=b"\0no stamp here\0") == "<none>"


def test_build_properties_strip_each_side(*, tmp_path: pathlib.Path) -> None:
    update = write_ota(
        members={survey.PROPERTIES: b" ro.product.model = AEOBC \n#a=b\n"},
        path=tmp_path / "ota.zip",
    )
    with zipfile.ZipFile(file=update) as archive:
        assert survey.build_properties(archive=archive) == {"ro.product.model": "AEOBC"}


@pytest.mark.parametrize(
    argnames=("name", "label"),
    argvalues=[
        ("Fire OS 5.5.5.4 (680767620)", "Fire OS 5.5.5.4"),
        ("Fire OS 6574.1 (NS65741/8146)", "Fire OS 6 8146"),
        ("Fire OS 6.5.5.5 (NS6555/4305M)", "Fire OS 6 4305"),
        ("<unnamed>", "<unnamed>"),
    ],
)
def test_csv_label(*, label: str, name: str) -> None:
    assert survey.csv_label(name=name) == label


@pytest.mark.parametrize(
    argnames=("data", "version"),
    argvalues=[
        (preloader(), 5),
        (preloader(calls=1), None),
        (preloader(function=b"\x05\x21\x70\x47"), None),
        (preloader()[:TEXT], None),
        (bytes(8) + b"\x78\x44" + preloader()[CODE + 4 :], None),
    ],
    ids=["found", "one-call", "not-movs-r0", "no-string", "no-literal"],
)
def test_pl_version(*, data: bytes, version: int | None) -> None:
    assert survey.pl_version(data=data) == version


def test_pl_version_tries_each_reference_to_the_string() -> None:
    data = bytearray(preloader())
    data[0x10:0x14] = data[CODE : CODE + 4]
    pool = ((0x10 + 4) & ~3) + (data[0x10] & 0xFF) * 4
    data[pool : pool + 4] = struct.pack("<I", TEXT - (0x12 + 4))
    data[0x14:0x18] = bl(at=0x14, target=PRINT)
    data[0x18:0x1C] = struct.pack("<HH", 0xF7FF, 0xFFF0)
    assert survey.pl_version(data=bytes(data)) == 5


@pytest.mark.parametrize(
    argnames=("name", "want"),
    argvalues=[
        ("biscuit_puffin", "biscuit"),
        ("hoya_ftv", "hoya"),
        ("hoya", "hoya"),
    ],
)
def test_the_codename_a_device_name_gives(*, name: str, want: str) -> None:
    assert survey.codename(name=name) == want


def test_the_subcommand_goes_on_past_an_ota_it_cannot_read(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(data=b"not a zip")
    good = block_update(path=tmp_path / "good.zip")
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "survey", str(bad), str(good)]
    )
    with pytest.raises(
        expected_exception=SystemExit, match=r"could not survey bad\.zip"
    ):
        __main__.main()
    out = capsys.readouterr().out
    assert "bad.zip: not an OTA zip" in out
    assert "OTA                      good.zip\n" in out


def test_the_subcommand_surveys_each_ota(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    first = block_update(path=tmp_path / "first.zip")
    second = block_update(path=tmp_path / "second.zip")
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "survey", str(first), str(second)]
    )
    __main__.main()
    out = capsys.readouterr().out
    assert "OTA                      first.zip\n" in out
    assert "\n\nOTA                      second.zip\n" in out
