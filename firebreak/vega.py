from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator
    from typing import IO

from firebreak.ui import FatalError

COPY = re.compile(r"copyA =.*?images =\s*\(", re.DOTALL)
CPIO_HEADER = 110
CPIO_MAGIC = (b"070701", b"070702")
CPIO_NAME = 94
CPIO_SIZE = 54
DESCRIPTION = "sw-description"
FIELD = re.compile(r"([\w-]+) = \"([^\"]*)\"")
HEX = re.compile(rb"[0-9A-Fa-f]{8}")
PROD = "prod_"
SIGNATURE = DESCRIPTION + ".sig"
SOFTWARE = re.compile(r"software =\s*\{\s*version = \"[^\"]*\";\s*(\w+) =")
STAMP = re.compile(r"image_timestamp=tonumber\('(\d+)'\)")
TRAILER = "TRAILER!!!"
VERSION = re.compile(r"image_version=tonumber\('(\d+)'\)")


@dataclasses.dataclass(frozen=True)
class Manifest:
    device: str
    files: frozenset[str]
    images: tuple[Wanted, ...]
    stamp: int | None
    version: str | None


@dataclasses.dataclass(frozen=True)
class Member:
    at: int
    name: str
    size: int


@dataclasses.dataclass(frozen=True)
class Wanted:
    filename: str
    partition: str
    sha256: str


def description(*, stream: IO[bytes]) -> tuple[str, dict[str, int]]:
    text, sizes = "", {}
    for member in members(stream=stream):
        sizes[member.name] = member.size
        if member.name == DESCRIPTION:
            here = stream.tell()
            stream.seek(member.at)
            text = stream.read(member.size).decode(errors="replace")
            stream.seek(here)
    if not text:
        raise FatalError(message=f"the .swu has no {DESCRIPTION}")
    return text, sizes


def entries(*, block: str) -> Iterator[str]:
    deep, start = 0, 0
    for at, letter in enumerate(block):
        if letter == "{":
            deep += 1
            if deep == 1:
                start = at + 1
        elif letter == "}":
            deep -= 1
            if deep == 0:
                yield block[start:at]


def is_swu(*, update: pathlib.Path) -> bool:
    try:
        with update.open("rb") as stream:
            return stream.read(len(CPIO_MAGIC[0])) in CPIO_MAGIC
    except OSError:
        return False


def manifest(*, text: str) -> Manifest:
    named = SOFTWARE.search(text)
    if named is None:
        raise FatalError(message="the .swu names no device")
    opened = COPY.search(text)
    if opened is None:
        raise FatalError(message="the .swu lists no copyA images")
    wanted = []
    for entry in entries(block=span(start=opened.end() - 1, text=text)):
        fields = dict(FIELD.findall(entry))
        target = fields.get("device") or fields.get("volume")
        name = fields.get("filename")
        if target is None or name is None or "sha256" not in fields:
            raise FatalError(
                message="an image in the .swu has no filename, device or sha256"
            )
        wanted.append(
            Wanted(
                filename=name,
                partition=partition(name=name, target=target),
                sha256=fields["sha256"],
            )
        )
    if not wanted:
        raise FatalError(message="the .swu lists no copyA images")
    version = VERSION.search(text)
    stamp = STAMP.search(text)
    return Manifest(
        device=named.group(1),
        files=frozenset(
            value for key, value in FIELD.findall(text) if key == "filename"
        ),
        images=tuple(wanted),
        stamp=None if stamp is None else int(stamp.group(1)),
        version=None if version is None else version.group(1),
    )


def members(*, stream: IO[bytes]) -> Iterator[Member]:
    stream.seek(0)
    while True:
        head = stream.read(CPIO_HEADER)
        if len(head) < CPIO_HEADER or head[:6] not in CPIO_MAGIC:
            return
        size = number(data=head, start=CPIO_SIZE)
        name_size = number(data=head, start=CPIO_NAME)
        name = stream.read(name_size)
        if len(name) < name_size:
            return
        stream.seek(-(CPIO_HEADER + name_size) % 4, 1)
        at = stream.tell()
        if name[:-1] == TRAILER.encode():
            return
        yield Member(at=at, name=name[:-1].decode(errors="replace"), size=size)
        stream.seek(at + size + -size % 4)


def number(*, data: bytes, start: int) -> int:
    field = data[start : start + 8]
    if HEX.fullmatch(field) is None:
        raise FatalError(message=f"the .swu has a damaged header: {field!r}")
    return int(field, 16)


def partition(*, name: str, target: str) -> str:
    base = target.rsplit("/", 1)[-1]
    if base.endswith(("_a", "_b")):
        base = base[:-2]
    base = base.removeprefix("mmcblk0")
    return base + "_prod" if name.startswith(PROD) else base


def read(*, update: pathlib.Path) -> tuple[Manifest, dict[str, int]]:
    with update.open("rb") as stream:
        text, sizes = description(stream=stream)
    return manifest(text=text), sizes


def span(*, start: int, text: str) -> str:
    deep = 0
    for at in range(start, len(text)):
        if text[at] == "(":
            deep += 1
        elif text[at] == ")":
            deep -= 1
            if deep == 0:
                return text[start + 1 : at]
    raise FatalError(message="the .swu has an unterminated copyA images list")
