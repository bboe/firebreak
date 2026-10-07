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

CMDLINE_SIZE = 512


def boot_image(*, fireos: pathlib.Path, magisk: pathlib.Path) -> bytes:
    with zipfile.ZipFile(fireos) as z:
        stock = z.read("boot.img")
    with zipfile.ZipFile(magisk) as z:
        magiskinit = z.read("arm/magiskinit")
    kernel_size, ramdisk_size, page = (
        struct.unpack_from("<I", stock, offset)[0] for offset in (8, 16, 36)
    )
    header = bytearray(stock[:page])
    cmdline = bytes(header[64:576]).split(b"\0")[0]
    header[64:576] = (cmdline + b" androidboot.selinux=permissive").ljust(
        CMDLINE_SIZE, b"\0"
    )
    kernel = stock[page : page + kernel_size]
    start = page + -(-kernel_size // page) * page
    files = cpio_files(gzip.decompress(stock[start : start + ramdisk_size]))
    mode, prop = files[b"default.prop"]
    prop = re.sub(rb"(?m)^ro\.secure=1$", b"ro.secure=0", prop)
    prop = re.sub(rb"(?m)^ro\.debuggable=0$", b"ro.debuggable=1", prop)
    prop = re.sub(
        rb"(?m)^persist\.sys\.usb\.config=.*", b"persist.sys.usb.config=mtp,adb", prop
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
        kernel=magisk_kernel(kernel),
        ramdisk=gzip.compress(cpio(files), compresslevel=9, mtime=0),
    )


def boot_pack(*, header: bytes | bytearray, kernel: bytes, ramdisk: bytes) -> bytes:
    page = len(header)
    sizes = struct.pack("<I", len(kernel)), struct.pack("<I", len(ramdisk))
    out = bytearray(header)
    out[8:12], out[16:20] = sizes
    sha1 = hashlib.sha1(
        kernel + sizes[0] + ramdisk + sizes[1] + bytes(4), usedforsecurity=False
    )
    out[576:608] = sha1.digest().ljust(32, b"\0")
    for part in (kernel, ramdisk):
        out += part.ljust(-(-len(part) // page) * page, b"\0")
    return bytes(out)


def cpio(files: dict[bytes, tuple[int, bytes]]) -> bytes:
    out = bytearray()
    for inode, name in enumerate([*sorted(files), b"TRAILER!!!"], start=300000):
        mode, body = files.get(name, (0, b""))
        fields = (inode, mode, 0, 0, 1, 0, len(body), 0, 0, 0, 0, len(name) + 1, 0)
        out += b"070701" + b"".join(b"%08x" % field for field in fields) + name + b"\0"
        out += bytes(-len(out) % 4) + body
        out += bytes(-len(out) % 4)
    return bytes(out)


def cpio_files(data: bytes) -> dict[bytes, tuple[int, bytes]]:
    files = {}
    at = 0
    while True:
        if data[at : at + 6] != b"070701":
            _die(message="the boot image's ramdisk is not a newc cpio archive")
        fields = [int(data[at + 6 + 8 * i : at + 14 + 8 * i], 16) for i in range(13)]
        name = data[at + 110 : at + 109 + fields[11]]
        at = (at + 110 + fields[11] + 3) & ~3
        body = data[at : at + fields[6]]
        at = (at + fields[6] + 3) & ~3
        if name == b"TRAILER!!!":
            return files
        files[name] = (fields[1], body)


def magisk_binary(magiskinit: bytes) -> bytes:
    at = magiskinit.find(b"\xfd7zXZ\0")
    while at != -1:
        with contextlib.suppress(lzma.LZMAError):
            binary = lzma.LZMADecompressor().decompress(magiskinit[at:])
            if binary.startswith(b"\x7fELF"):
                return binary
        at = magiskinit.find(b"\xfd7zXZ\0", at + 1)
    _die(message=f"{MAGISK.name}'s magiskinit holds no magisk binary")
    return b""


def magisk_db(path: pathlib.Path) -> None:
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE policies (uid INT, package_name TEXT, policy INT, "
        "until INT, logging INT, notification INT)"
    )
    db.execute("INSERT INTO policies VALUES (2000, 'com.android.shell', 2, 0, 1, 0)")
    db.commit()
    db.close()


def magisk_files(*, db: bytes, magisk: pathlib.Path) -> dict[bytes, tuple[int, bytes]]:
    files = {
        b"data/adb": (0o40700, b""),
        b"data/adb/magisk": (0o40755, b""),
        b"data/adb/magisk/chromeos": (0o40755, b""),
        b"data/adb/magisk.db": (0o100600, db),
    }
    with zipfile.ZipFile(magisk) as z:
        for info in z.infolist():
            folder, _, name = info.filename.partition("/")
            if folder in {"arm", "common"}:
                path = name
            elif folder == "chromeos":
                path = info.filename
            else:
                continue
            files[f"data/adb/magisk/{path}".encode()] = (0o100755, z.read(info))
        script = z.read("META-INF/com/google/android/update-binary").decode()
    packed = re.search(r"^BB_ARM=(\S+)", script, re.MULTILINE)
    if not packed:
        _die(message=f"{MAGISK.name} has no busybox in its installer")
    files[b"data/adb/magisk/busybox"] = (
        0o100755,
        lzma.decompress(base64.b64decode(packed.group(1))),
    )
    files[b"data/adb/magisk/magisk"] = (
        0o100755,
        magisk_binary(files[b"data/adb/magisk/magiskinit"][1]),
    )
    return files


def magisk_kernel(kernel: bytes) -> bytes:
    stream = zlib.decompressobj(31)
    image = stream.decompress(kernel[512:])
    image = image.replace(b"skip_initramfs\0", b"want_initramfs\0")
    body = gzip.compress(image, compresslevel=9, mtime=0) + stream.unused_data
    return kernel[:4] + struct.pack("<I", len(body)) + kernel[8:512] + body
