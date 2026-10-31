from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import lzma
import pathlib
import re
import struct
import tempfile
import zipfile
import zlib

from firebreak.android import ota
from firebreak.cache import CACHE, digest
from firebreak.report import labelled
from firebreak.ui import FatalError, show, warn

BL_FIRST = 0xF000
BL_FIRST_MASK = 0xF800
BL_SECOND = 0xD000
BUILD_TIME = re.compile(rb"\d{8}_\d{6}")
BX_LR = 0x4770
COMMIT = re.compile(rb"[0-9a-fA-F]{7}")
CSV_LABEL = re.compile(r"Fire OS (\S+) \((?:\w+/)?(\d+)M?\)")
DESCRIPTION = re.compile(rb"[0-9a-f]{7}-\d{8}_\d{6}")
INSTRUCTIONS_SEARCHED = 16
LDR_LITERAL = 0x4800
LDR_LITERAL_MASK = 0xF800
LITERAL_SEARCHED = 8
LK_TRAILER = 0x2000
MOVS_R0 = 0x2000
MOVS_R0_MASK = 0xFF00
NEARBY_STRINGS = 3
PC_ADD = 0x4478
PC_ADD_MASK = 0xFFF8
PL_CALL = 1
PL_UPDATE = b"[ANTI-ROLLBACK] Updating PL version"
PROPERTIES = "META-INF/com/amazon/android/target.build.prop"
STRING = re.compile(rb"[\x20-\x7e]{6,}")
TEE_HEADER = b"EET KTM"
TEE_NAMES = ("tee", "tee1", "tee2")
TEE_VERSION = slice(0xF, 0x11)
WIDE_PREFIXES = frozenset({0b11101, 0b11110, 0b11111})


@dataclasses.dataclass(frozen=True)
class Image:
    sha256: str
    size: int
    data: bytes = b""


def branch_target(*, at: int, first: int, second: int) -> int:
    sign = (first >> 10) & 1
    high = (~((second >> 13) ^ sign) & 1) << 23
    low = (~((second >> 11) ^ sign) & 1) << 22
    offset = high | low | (first & 0x3FF) << 12 | (second & 0x7FF) << 1
    return at + 4 + offset - (sign << 24)


def build_description(*, data: bytes) -> str:
    joined = sorted({found.decode() for found in DESCRIPTION.findall(data)})
    if joined:
        return ", ".join(joined)
    words = STRING.findall(data)
    found = set()
    for index, word in enumerate(words):
        if not BUILD_TIME.fullmatch(word):
            continue
        near = words[max(0, index - NEARBY_STRINGS) : index + NEARBY_STRINGS + 1]
        commits = [each for each in near if COMMIT.fullmatch(each)]
        if commits:
            found.add(f"{commits[0].decode().lower()}-{word.decode()}")
    return ", ".join(sorted(found)) or "<none>"


def build_properties(*, archive: zipfile.ZipFile) -> dict[str, str]:
    try:
        text = archive.read(name=PROPERTIES).decode(errors="replace")
    except KeyError:
        return {}
    found = {}
    for line in text.splitlines():
        key, equals, value = line.partition("=")
        if equals and not key.lstrip().startswith("#"):
            found[key.strip()] = value.strip()
    return found


def calls(*, data: bytes, start: int) -> list[int]:
    found = []
    at = start
    for _ in range(INSTRUCTIONS_SEARCHED):
        first = halfword(at=at, data=data)
        if first >> 11 not in WIDE_PREFIXES:
            at += 2
            continue
        second = halfword(at=at + 2, data=data)
        if first & BL_FIRST_MASK == BL_FIRST and second & BL_SECOND == BL_SECOND:
            found.append(branch_target(at=at, first=first, second=second))
        at += 4
    return found


def csv_label(*, name: str) -> str:
    found = CSV_LABEL.fullmatch(name)
    if found is None:
        return name
    version, build = found.groups()
    return f"Fire OS {version}" if version.startswith("5.") else f"Fire OS 6 {build}"


def csv_partitions(*, tees: tuple[str, ...]) -> tuple[str, ...]:
    return ("boot", "system", "lk", *tees, "preloader")


def csv_row(*fields: object) -> str:
    text = io.StringIO()
    csv.writer(text, lineterminator="").writerow(fields)
    return text.getvalue()


def halfword(*, at: int, data: bytes) -> int:
    return int.from_bytes(data[at : at + 2], "little")


def images(*, archive: zipfile.ZipFile) -> dict[str, Image]:
    names = set(archive.namelist())
    if "payload.bin" in names:
        return payload_images(archive=archive)
    missing = sorted(
        {*ota.BLOCK_IMAGES.values(), "system.new.dat", "system.transfer.list"} - names
    )
    if missing:
        raise FatalError(message="the OTA has no " + ", ".join(missing))
    found = {}
    for name, member in ota.BLOCK_IMAGES.items():
        data = archive.read(name=member)
        found[name] = Image(
            data=data, sha256=hashlib.sha256(data).hexdigest(), size=len(data)
        )
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        path = pathlib.Path(temporary) / "system.img"
        ota.write_system(archive=archive, path=path)
        found["system"] = Image(
            sha256=digest(kind="sha256", path=path), size=path.stat().st_size
        )
    return found


def literal(*, at: int, data: bytes, register: int) -> int | None:
    for back in range(1, LITERAL_SEARCHED + 1):
        where = at - 2 * back
        if where < 0:
            return None
        half = halfword(at=where, data=data)
        if half & LDR_LITERAL_MASK == LDR_LITERAL and (half >> 8) & 7 == register:
            pool = ((where + 4) & ~3) + (half & 0xFF) * 4
            return int.from_bytes(data[pool : pool + 4], "little")
    return None


def lk_version(*, data: bytes) -> int | None:
    at = data.rfind(b"LK", max(0, len(data) - LK_TRAILER))
    return None if at < 0 else int.from_bytes(data[at + 2 : at + 4], "big")


def payload_images(*, archive: zipfile.ZipFile) -> dict[str, Image]:
    found = {}
    with archive.open(name="payload.bin") as payload:
        manifest = ota.read_manifest(payload=payload)
        wanted = tuple(name for name in ota.IMAGES if name != "tee")
        tees = tee_names(names=frozenset(manifest.partitions))
        for name in (*wanted, *tees):
            partition = manifest.partitions.get(name)
            if partition is None:
                raise FatalError(message=f"the OTA has no {name} image")
            want = ota.blob(value=partition.info[ota.InfoField.HASH]).hex()
            data = b""
            if name not in {"boot", "system"}:
                data = bytes(
                    ota.image_bytes(
                        manifest=manifest,
                        name=name,
                        partition=partition,
                        payload=payload,
                    )
                )
                if hashlib.sha256(data).hexdigest() != want:
                    raise FatalError(message=name + " does not match the manifest")
            found[name] = Image(
                data=data,
                sha256=want,
                size=ota.number(value=partition.info[ota.InfoField.SIZE]),
            )
    return found


def pl_version(*, data: bytes) -> int | None:
    text = data.find(PL_UPDATE)
    if text < 0:
        return None
    for at in range(0, len(data) - 1, 2):
        half = halfword(at=at, data=data)
        if half & PC_ADD_MASK != PC_ADD:
            continue
        base = literal(at=at, data=data, register=half & 7)
        if base is None or (base + at + 4) & 0xFFFFFFFF != text:
            continue
        called = calls(data=data, start=at + 2)
        if len(called) <= PL_CALL or not 0 <= called[PL_CALL] <= len(data) - 4:
            continue
        target = called[PL_CALL]
        first = halfword(at=target, data=data)
        if (
            first & MOVS_R0_MASK == MOVS_R0
            and halfword(at=target + 2, data=data) == BX_LR
        ):
            return first & 0xFF
    return None


def survey(*, update: pathlib.Path) -> None:
    try:
        archive = zipfile.ZipFile(file=update)
    except (OSError, zipfile.BadZipFile) as error:
        raise FatalError(message=f"not an OTA zip: {error}") from error
    with archive:
        properties = build_properties(archive=archive)
        try:
            found = images(archive=archive)
        except (
            EOFError,
            KeyError,
            OSError,
            ValueError,
            lzma.LZMAError,
            struct.error,
            zipfile.BadZipFile,
            zlib.error,
        ) as error:
            raise FatalError(message=f"could not be read: {error!r}") from error
    tees = tee_names(names=frozenset(found))
    tee = found[tees[0]]
    tee_md5 = hashlib.md5(tee.data, usedforsecurity=False).hexdigest()
    show(text=labelled(label="OTA", value=update.name))
    name = properties.get("ro.build.version.name", "<unnamed>")
    device = properties.get("ro.product.device", "<unknown>").removesuffix("_puffin")
    model = properties.get("ro.product.model", "<unknown>")
    show(text=labelled(label="build", value=name))
    show(text=labelled(label="device", value=device))
    show(text=labelled(label="model", value=model))
    show(
        text=labelled(
            label="lk_build_desc", value=build_description(data=found["lk"].data)
        )
    )
    show(
        text=labelled(
            label="pl_build_desc", value=build_description(data=found["preloader"].data)
        )
    )
    show(
        text=labelled(
            label="anti-rollback",
            value=", ".join(
                f"{label} {version_text(version=version)}"
                for label, version in (
                    ("PL", pl_version(data=found["preloader"].data)),
                    ("TEE", tee_version(data=tee.data)),
                    ("LK", lk_version(data=found["lk"].data)),
                )
            ),
        )
    )
    show(
        text=labelled(
            label="TEE",
            value=f"{tee.size} bytes, md5 {tee_md5}, sha256 {tee.sha256}",
        )
    )
    if any(found[name].sha256 != tee.sha256 for name in tees[1:]):
        warn(text=f"{', '.join(tees)} do not hold the same image")
    show(text="\ndevice,model,build,partition,bytes,sha256")
    label = csv_label(name=name)
    for partition in csv_partitions(tees=tees):
        image = found[partition]
        show(text=csv_row(device, model, label, partition, image.size, image.sha256))


def survey_all(*, paths: list[pathlib.Path]) -> None:
    failed = []
    for index, path in enumerate(paths):
        if index:
            show(text="")
        try:
            survey(update=path)
        except FatalError as error:
            warn(text=f"{path.name}: {error.message}")
            failed.append(path.name)
    if failed:
        raise FatalError(message="could not survey " + ", ".join(failed))


def tee_names(*, names: frozenset[str]) -> tuple[str, ...]:
    return tuple(name for name in TEE_NAMES if name in names) or ("tee",)


def tee_version(*, data: bytes) -> int | None:
    at = data.find(TEE_HEADER)
    if at < 0:
        return None
    return int.from_bytes(data[at + TEE_VERSION.start : at + TEE_VERSION.stop], "big")


def version_text(*, version: int | None) -> str:
    return "<not found>" if version is None else f"0x{version:04x}"
