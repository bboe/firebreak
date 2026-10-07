from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import lzma
import sqlite3
import struct
import zipfile
import zlib
from typing import TYPE_CHECKING

import pytest

from firebreak.android import bootimg

if TYPE_CHECKING:
    import pathlib

BUSYBOX = b"\x7fELF busybox"
ELF = b"\x7fELF magisk"
PAGE = 2048
RAMDISK = {
    b"default.prop": (
        0o100644,
        b"ro.secure=1\nro.debuggable=0\npersist.sys.usb.config=mtp\n",
    ),
    b"fstab.mt8163": (0o100640, b"/dev/system /system ext4 ro wait,verify\n"),
    b"fstab.other": (0o100640, b"/dev/data /data ext4 rw verify,wait\n"),
    b"init": (0o100750, b"stock init"),
    b"sbin": (0o40755, b""),
    b"verity_key": (0o100644, b"key"),
}


def kernel(*, image: bytes, tail: bytes = b"dtb") -> bytes:
    body = gzip.compress(data=image, mtime=0) + tail
    return b"KERN" + struct.pack("<I", len(body)) + bytes(504) + body


def magisk_zip(*, busybox: bool = True, path: pathlib.Path) -> pathlib.Path:
    script = "#!/sbin/sh\n"
    if busybox:
        script += (
            "BB_ARM=" + base64.b64encode(s=lzma.compress(data=BUSYBOX)).decode() + "\n"
        )
    with zipfile.ZipFile(file=path, mode="w") as archive:
        archive.writestr(data=magiskinit(), zinfo_or_arcname="arm/magiskinit")
        archive.writestr(data=b"util", zinfo_or_arcname="common/util_functions.sh")
        archive.writestr(data=b"futility", zinfo_or_arcname="chromeos/futility")
        archive.writestr(data=b"x86", zinfo_or_arcname="x86/magiskinit")
        archive.writestr(
            data=script, zinfo_or_arcname="META-INF/com/google/android/update-binary"
        )
    return path


def magiskinit() -> bytes:
    return (
        b"junk\xfd7zXZ\0junk" + lzma.compress(data=b"not elf") + lzma.compress(data=ELF)
    )


def stock_boot() -> bytes:
    header = bytearray(PAGE)
    header[:8] = b"ANDROID!"
    header[36:40] = struct.pack("<I", PAGE)
    header[64:76] = b"console=tty0"
    return bootimg.boot_pack(
        header=header,
        kernel=kernel(image=b"linux skip_initramfs\0 rest"),
        ramdisk=gzip.compress(data=bootimg.cpio(files=RAMDISK), mtime=0),
    )


def test_boot_image(*, tmp_path: pathlib.Path) -> None:
    fireos = tmp_path / "fireos.zip"
    with zipfile.ZipFile(file=fireos, mode="w") as archive:
        archive.writestr(data=stock_boot(), zinfo_or_arcname="boot.img")
    image = bootimg.boot_image(
        fireos=fireos, magisk=magisk_zip(path=tmp_path / "m.zip")
    )
    header, kernel_image, ramdisk = unpack(image=image)
    assert header[64:576].rstrip(b"\0") == (
        b"console=tty0 androidboot.selinux=permissive"
    )
    assert b"want_initramfs" in zlib.decompressobj(wbits=31).decompress(
        kernel_image[512:]
    )
    files = bootimg.cpio_files(data=gzip.decompress(data=ramdisk))
    assert files[b"init"] == (0o100750, magiskinit())
    assert files[b".backup/init"] == RAMDISK[b"init"]
    assert files[b".backup/verity_key"] == RAMDISK[b"verity_key"]
    assert b"verity_key" not in files
    assert files[b".backup"] == (0o40000, b"")
    assert files[b".backup/.magisk"][1].startswith(b"KEEPVERITY=false\n")
    assert files[b"default.prop"][1] == (
        b"ro.secure=0\nro.debuggable=1\npersist.sys.usb.config=mtp,adb\n"
    )
    assert files[b"fstab.mt8163"][1] == b"/dev/system /system ext4 ro wait\n"
    assert files[b"fstab.other"][1] == b"/dev/data /data ext4 rw wait\n"


def test_boot_pack() -> None:
    header = bytearray(PAGE)
    image = bootimg.boot_pack(header=header, kernel=b"k" * 3000, ramdisk=b"r" * 10)
    assert len(image) == PAGE * 4
    assert struct.unpack_from("<I", buffer=image, offset=8)[0] == 3000
    assert struct.unpack_from("<I", buffer=image, offset=16)[0] == 10
    sha1 = hashlib.sha1(  # ruff: ignore[hashlib-insecure-hash-function]
        b"k" * 3000
        + struct.pack("<I", 3000)
        + b"r" * 10
        + struct.pack("<I", 10)
        + bytes(4)
    ).digest()
    assert image[576:608] == sha1 + bytes(12)
    assert image[PAGE : PAGE + 3000] == b"k" * 3000
    assert image[3 * PAGE : 3 * PAGE + 10] == b"r" * 10


def test_cpio_files_refuses_other_formats() -> None:
    with pytest.raises(expected_exception=SystemExit, match="not a newc cpio archive"):
        bootimg.cpio_files(data=b"070707" + bytes(200))


def test_cpio_round_trip() -> None:
    archive = bootimg.cpio(files=RAMDISK)
    assert len(archive) % 4 == 0
    assert archive.startswith(b"070701")
    assert b"TRAILER!!!" in archive
    assert bootimg.cpio_files(data=archive) == RAMDISK


def test_magisk_binary() -> None:
    assert bootimg.magisk_binary(magiskinit=magiskinit()) == ELF
    with pytest.raises(expected_exception=SystemExit, match="holds no magisk binary"):
        bootimg.magisk_binary(magiskinit=b"junk" + lzma.compress(data=b"not elf"))


def test_magisk_db(*, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "magisk.db"
    bootimg.magisk_db(path=path)
    with contextlib.closing(thing=sqlite3.connect(database=path)) as database:
        assert database.execute("SELECT * FROM policies").fetchall() == [
            (2000, "com.android.shell", 2, 0, 1, 0)
        ]


def test_magisk_files(*, tmp_path: pathlib.Path) -> None:
    files = bootimg.magisk_files(
        database=b"db", magisk=magisk_zip(path=tmp_path / "m.zip")
    )
    assert files[b"data/adb/magisk.db"] == (0o100600, b"db")
    assert files[b"data/adb"] == (0o40700, b"")
    assert files[b"data/adb/magisk/magiskinit"] == (0o100755, magiskinit())
    assert files[b"data/adb/magisk/util_functions.sh"] == (0o100755, b"util")
    assert files[b"data/adb/magisk/chromeos/futility"] == (0o100755, b"futility")
    assert files[b"data/adb/magisk/busybox"] == (0o100755, BUSYBOX)
    assert files[b"data/adb/magisk/magisk"] == (0o100755, ELF)
    assert not any(b"x86" in name for name in files)


def test_magisk_files_needs_busybox(*, tmp_path: pathlib.Path) -> None:
    magisk = magisk_zip(busybox=False, path=tmp_path / "m.zip")
    with pytest.raises(
        expected_exception=SystemExit, match="has no busybox in its installer"
    ):
        bootimg.magisk_files(database=b"db", magisk=magisk)


def test_magisk_kernel() -> None:
    patched = bootimg.magisk_kernel(
        kernel=kernel(image=b"linux skip_initramfs\0 rest", tail=b"dtb")
    )
    assert patched[:4] == b"KERN"
    size = struct.unpack_from("<I", buffer=patched, offset=4)[0]
    assert size == len(patched) - 512
    stream = zlib.decompressobj(wbits=31)
    assert stream.decompress(patched[512:]) == b"linux want_initramfs\0 rest"
    assert stream.unused_data == b"dtb"


def unpack(*, image: bytes) -> tuple[bytes, bytes, bytes]:
    kernel_size, ramdisk_size, page = (
        struct.unpack_from("<I", buffer=image, offset=offset)[0]
        for offset in (8, 16, 36)
    )
    start = page + -(-kernel_size // page) * page
    return (
        image[:page],
        image[page : page + kernel_size],
        image[start : start + ramdisk_size],
    )
