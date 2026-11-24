from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from firebreak import vega
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

IMAGE = """                    {{
                        filename = "{name}";
                        {key} = "{target}";
                        type = "raw";{extra}
                        sha256 = "{sha256}";
                    }},
"""
SCRIPT = (
    "\\nfunction do_version_check(image)\\n"
    "    image_version=tonumber('6401030007120')\\n"
    "    image_timestamp=tonumber('1789271599')\\n"
    "end\\n"
)


def copy(*, images: str, name: str) -> str:
    return f"""            {name} =
            {{
                scripts =
                (
                    {{
                        filename = "version_check.sh";
                        type = "preinstall";
                        hook = "do_version_check";
                        sha256 = "beef";
                    }}
                );
                images =
                (
{images}                );
            }};
"""


def description(
    *, device: str = "galileo", images: str | None = None, script: str = SCRIPT
) -> str:
    held = IMAGE.format(
        extra="", key="device", name="boot.img", sha256="b007", target="/dev/boot_a"
    ) + IMAGE.format(
        extra="""
                        compressed = "zlib";
                        properties =
                        {
                            decompressed-size = "4096";
                        };""",
        key="volume",
        name="prod_fip.bin",
        sha256="f1b",
        target="bootloader_a",
    )
    if images is None:
        images = held
    return f"""software =
{{
    version = "0.1.0";
    {device} =
    {{
        embedded-script = "{script}";
        stable =
        {{
{copy(images=images, name="copyA")}{copy(images=images, name="copyB")}        }};
    }};
}};
"""


def member(*, body: bytes, name: str) -> bytes:
    raw = name.encode() + b"\0"
    fields = (0, 0o100644, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(raw), 0)
    head = b"070701" + b"".join(f"{field:08x}".encode() for field in fields)
    return (
        head + raw + bytes(-(len(head) + len(raw)) % 4) + body + bytes(-len(body) % 4)
    )


def swu(*, path: pathlib.Path, **members: bytes) -> pathlib.Path:
    body = b"".join(member(body=data, name=name) for name, data in members.items())
    path.write_bytes(data=body + member(body=b"", name="TRAILER!!!"))
    return path


def test_a_damaged_header(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu")
    update.write_bytes(data=update.read_bytes().replace(b"070701", b"07070x", 1))
    assert not vega.is_swu(update=update)


def test_a_header_field_that_is_signed(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu")
    body = bytearray(update.read_bytes())
    body[vega.CPIO_SIZE : vega.CPIO_SIZE + 8] = b"-0000004"
    update.write_bytes(data=bytes(body))
    with pytest.raises(expected_exception=FatalError, match="damaged header"):
        vega.read(update=update)


def test_a_header_with_a_field_that_is_not_hex(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu")
    body = bytearray(update.read_bytes())
    body[vega.CPIO_SIZE : vega.CPIO_SIZE + 8] = b"zzzzzzzz"
    update.write_bytes(data=bytes(body))
    with pytest.raises(expected_exception=FatalError, match="damaged header"):
        vega.read(update=update)


def test_a_swu_that_ends_inside_a_header(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu")
    update.write_bytes(data=update.read_bytes()[: vega.CPIO_HEADER - 1])
    with pytest.raises(expected_exception=FatalError, match="has no sw-description"):
        vega.read(update=update)


def test_a_swu_that_ends_inside_a_name(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu")
    update.write_bytes(data=update.read_bytes()[: vega.CPIO_HEADER + 2])
    with pytest.raises(expected_exception=FatalError, match="has no sw-description"):
        vega.read(update=update)


def test_a_swu_with_no_images(*, tmp_path: pathlib.Path) -> None:
    text = description().replace("images =", "pictures =")
    with pytest.raises(expected_exception=FatalError, match="no copyA images"):
        vega.read(update=written(path=tmp_path / "ota.swu", text=text))


def test_a_swu_with_no_software_block(*, tmp_path: pathlib.Path) -> None:
    text = description().replace("software =", "hardware =")
    with pytest.raises(expected_exception=FatalError, match="names no device"):
        vega.read(update=written(path=tmp_path / "ota.swu", text=text))


def test_an_image_that_holds_a_list_of_its_own(*, tmp_path: pathlib.Path) -> None:
    extra = """
                        hooks =
                        (
                            "one"
                        );"""
    images = IMAGE.format(
        extra=extra, key="device", name="boot.img", sha256="b007", target="/dev/boot_a"
    ) + IMAGE.format(
        extra="", key="volume", name="fip.bin", sha256="f1b", target="bootloader_a"
    )
    update = written(path=tmp_path / "ota.swu", text=description(images=images))
    manifest, _ = vega.read(update=update)
    assert [image.filename for image in manifest.images] == ["boot.img", "fip.bin"]


def test_an_image_with_no_sha256(*, tmp_path: pathlib.Path) -> None:
    text = description().replace('sha256 = "b007";', "")
    with pytest.raises(
        expected_exception=FatalError, match="no filename, device or sha256"
    ):
        vega.read(update=written(path=tmp_path / "ota.swu", text=text))


def test_an_images_list_with_no_entries(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu", text=description(images=""))
    with pytest.raises(expected_exception=FatalError, match="no copyA images"):
        vega.read(update=update)


def test_an_unterminated_images_list(*, tmp_path: pathlib.Path) -> None:
    text = description().replace("                );\n            };\n", "", 1)
    with pytest.raises(expected_exception=FatalError, match="unterminated"):
        vega.read(update=written(path=tmp_path / "ota.swu", text=text))


def test_is_swu_says_no_to_a_path_it_cannot_open(*, tmp_path: pathlib.Path) -> None:
    assert not vega.is_swu(update=tmp_path / "nothing.swu")


def test_is_swu_says_no_to_another_file(*, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "ota.zip"
    path.write_bytes(data=b"PK\x03\x04")
    assert not vega.is_swu(update=path)


def test_read_takes_the_manifest_and_the_member_sizes(
    *, tmp_path: pathlib.Path
) -> None:
    update = written(path=tmp_path / "ota.swu")
    assert vega.is_swu(update=update)
    manifest, sizes = vega.read(update=update)
    assert manifest.device == "galileo"
    assert manifest.stamp == 1789271599
    assert manifest.version == "6401030007120"
    assert sizes == {
        "boot.img": 4,
        "prod_fip.bin": 4,
        "sw-description": sizes["sw-description"],
    }
    assert manifest.images == (
        vega.Wanted(filename="boot.img", partition="boot", sha256="b007"),
        vega.Wanted(filename="prod_fip.bin", partition="bootloader_prod", sha256="f1b"),
    )


def test_read_without_a_script(*, tmp_path: pathlib.Path) -> None:
    update = written(path=tmp_path / "ota.swu", text=description(script=""))
    manifest, _ = vega.read(update=update)
    assert manifest.stamp is None
    assert manifest.version is None


@pytest.mark.parametrize(
    argnames=("name", "target", "want"),
    argvalues=[
        ("boot.img", "/dev/block/platform/boot_a", "boot"),
        ("boot.img", "/dev/block/platform/boot_b", "boot"),
        ("bl2.img", "/dev/mmcblk0boot0", "boot0"),
        ("prod_fip_bl2.bin", "/dev/mtd1", "mtd1_prod"),
        ("rootfs.gz", "system_a", "system"),
    ],
)
def test_the_partition_a_target_names(*, name: str, target: str, want: str) -> None:
    assert vega.partition(name=name, target=target) == want


def written(*, path: pathlib.Path, text: str | None = None) -> pathlib.Path:
    members = {"boot.img": b"boot", "prod_fip.bin": b"fip!"}
    if text is None:
        text = description()
    return swu(path=path, **{vega.DESCRIPTION: text.encode()}, **members)
