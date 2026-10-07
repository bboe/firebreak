from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import lzma
import re
import sqlite3
import struct
import zipfile
import zlib
from typing import TYPE_CHECKING

from firebreak.cache import MAGISK
from firebreak.ui import _die

if TYPE_CHECKING:
    import pathlib

COMMAND_LINE_SIZE = 512
CPIO_HEADER_SIZE = 110


def boot_image(*, fireos: pathlib.Path, magisk: pathlib.Path) -> bytes:
    with zipfile.ZipFile(file=fireos) as archive:
        stock = archive.read(name="boot.img")
    with zipfile.ZipFile(file=magisk) as archive:
        magiskinit = archive.read(name="arm/magiskinit")
    kernel_size, ramdisk_size, page = (
        struct.unpack_from("<I", buffer=stock, offset=offset)[0]
        for offset in (8, 16, 36)
    )
    header = bytearray(stock[:page])
    command_line = bytes(header[64:576]).split(sep=b"\0")[0]
    command_line += b" androidboot.selinux=permissive"
    if len(command_line) >= COMMAND_LINE_SIZE:
        _die(
            message="the stock boot image's command line has no room for"
            " androidboot.selinux=permissive"
        )
    header[64:576] = command_line.ljust(COMMAND_LINE_SIZE, b"\0")
    kernel = stock[page : page + kernel_size]
    start = page + -(-kernel_size // page) * page
    files = cpio_files(data=gzip.decompress(data=stock[start : start + ramdisk_size]))
    mode, prop = files[b"default.prop"]
    prop = re.sub(pattern=rb"(?m)^ro\.secure=1$", repl=b"ro.secure=0", string=prop)
    prop = re.sub(
        pattern=rb"(?m)^ro\.debuggable=0$", repl=b"ro.debuggable=1", string=prop
    )
    prop = re.sub(
        pattern=rb"(?m)^persist\.sys\.usb\.config=.*",
        repl=b"persist.sys.usb.config=mtp,adb",
        string=prop,
    )
    files[b"default.prop"] = (mode, prop)
    for name, (mode, body) in files.items():
        if name.startswith(b"fstab"):
            files[name] = (mode, body.replace(b",verify", b"").replace(b"verify,", b""))
    files[b".backup"] = (0o40000, b"")
    files[b".backup/.magisk"] = (
        0o100000,
        b"KEEPVERITY=false\nKEEPFORCEENCRYPT=false\n\0",
    )
    files[b".backup/init"] = files[b"init"]
    files[b".backup/verity_key"] = files.pop(b"verity_key")
    files[b"init"] = (0o100750, magiskinit)
    return boot_pack(
        header=header,
        kernel=magisk_kernel(kernel=kernel),
        ramdisk=gzip.compress(compresslevel=9, data=cpio(files=files), mtime=0),
    )


def boot_pack(*, header: bytes | bytearray, kernel: bytes, ramdisk: bytes) -> bytes:
    page = len(header)
    kernel_size = struct.pack("<I", len(kernel))
    ramdisk_size = struct.pack("<I", len(ramdisk))
    image = bytearray(header)
    image[8:12] = kernel_size
    image[16:20] = ramdisk_size
    sha1 = hashlib.sha1(
        kernel + kernel_size + ramdisk + ramdisk_size + bytes(4), usedforsecurity=False
    )
    image[576:608] = sha1.digest().ljust(32, b"\0")
    for part in (kernel, ramdisk):
        image += part.ljust(-(-len(part) // page) * page, b"\0")
    return bytes(image)


def cpio(*, files: dict[bytes, tuple[int, bytes]]) -> bytes:
    archive = bytearray()
    for inode, name in enumerate(
        iterable=[*sorted(files), b"TRAILER!!!"], start=300000
    ):
        mode, body = files.get(name, (0, b""))
        fields = (inode, mode, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(name) + 1, 0)
        archive += (
            b"070701" + b"".join(b"%08x" % field for field in fields) + name + b"\0"
        )
        archive += bytes(-len(archive) % 4) + body
        archive += bytes(-len(archive) % 4)
    return bytes(archive)


def cpio_files(*, data: bytes) -> dict[bytes, tuple[int, bytes]]:
    files = {}
    offset = 0
    while offset < len(data):
        if data[offset : offset + 6] != b"070701":
            _die(message="the boot image's ramdisk is not a newc cpio archive")
        if len(data) - offset < CPIO_HEADER_SIZE:
            _die(message="the boot image's ramdisk ends inside a cpio header")
        fields = [
            int(data[offset + 6 + 8 * index : offset + 14 + 8 * index], 16)
            for index in range(13)
        ]
        name = data[offset + 110 : offset + 109 + fields[11]]
        offset = (offset + 110 + fields[11] + 3) & ~3
        body = data[offset : offset + fields[6]]
        offset = (offset + fields[6] + 3) & ~3
        if name == b"TRAILER!!!":
            return files
        files[name] = (fields[1], body)
    _die(message="the boot image's ramdisk ends without a cpio trailer")
    return {}


def magisk_binary(*, magiskinit: bytes) -> bytes:
    offset = magiskinit.find(b"\xfd7zXZ\0")
    while offset != -1:
        with contextlib.suppress(lzma.LZMAError):
            binary = lzma.LZMADecompressor().decompress(data=magiskinit[offset:])
            if binary.startswith(b"\x7fELF"):
                return binary
        offset = magiskinit.find(b"\xfd7zXZ\0", offset + 1)
    _die(message=f"{MAGISK.name}'s magiskinit holds no magisk binary")
    return b""


def magisk_db(*, path: pathlib.Path) -> None:
    with contextlib.closing(thing=sqlite3.connect(database=path)) as database:
        database.execute(
            "CREATE TABLE policies (uid INT, package_name TEXT, policy INT, "
            "until INT, logging INT, notification INT)"
        )
        database.execute(
            "INSERT INTO policies VALUES (2000, 'com.android.shell', 2, 0, 1, 0)"
        )
        database.commit()


def magisk_files(
    *, database: bytes, magisk: pathlib.Path
) -> dict[bytes, tuple[int, bytes]]:
    files = {
        b"data/adb": (0o40700, b""),
        b"data/adb/magisk": (0o40755, b""),
        b"data/adb/magisk/chromeos": (0o40755, b""),
        b"data/adb/magisk.db": (0o100600, database),
    }
    with zipfile.ZipFile(file=magisk) as archive:
        for info in archive.infolist():
            folder, _, name = info.filename.partition("/")
            if folder in {"arm", "common"}:
                path = name
            elif folder == "chromeos":
                path = info.filename
            else:
                continue
            files[f"data/adb/magisk/{path}".encode()] = (
                0o100755,
                archive.read(name=info),
            )
        script = archive.read(name="META-INF/com/google/android/update-binary").decode()
    packed = re.search(flags=re.MULTILINE, pattern=r"^BB_ARM=(\S+)", string=script)
    if not packed:
        _die(message=f"{MAGISK.name} has no busybox in its installer")
    files[b"data/adb/magisk/busybox"] = (
        0o100755,
        lzma.decompress(data=base64.b64decode(s=packed.group(1))),
    )
    files[b"data/adb/magisk/magisk"] = (
        0o100755,
        magisk_binary(magiskinit=files[b"data/adb/magisk/magiskinit"][1]),
    )
    return files


def magisk_kernel(*, kernel: bytes) -> bytes:
    stream = zlib.decompressobj(wbits=31)
    image = stream.decompress(kernel[512:])
    image = image.replace(b"skip_initramfs\0", b"want_initramfs\0")
    body = gzip.compress(compresslevel=9, data=image, mtime=0) + stream.unused_data
    return kernel[:4] + struct.pack("<I", len(body)) + kernel[8:512] + body
