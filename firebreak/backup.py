from __future__ import annotations

import collections
import csv
import dataclasses
import datetime
import gzip
import hashlib
import json
import pathlib
import re
import struct
import subprocess
from typing import TYPE_CHECKING

from firebreak import __version__
from firebreak.android.gpt import ENTRIES_SIZE, SECTOR_SIZE, gpt_intact, partition_map
from firebreak.devices import BUILDS
from firebreak.entry import known_device, twrp_entry
from firebreak.host import PUSH_TRIES, adb_shell, reconnect, run
from firebreak.plan import TABLE_SECTORS
from firebreak.report import whole
from firebreak.twrp import DISK, detect_dd, read_sectors, unmount, wait_for_twrp_start
from firebreak.ui import PROGRESS, FatalError, passed, say, title

if TYPE_CHECKING:
    from firebreak.cache import Download
    from firebreak.plugin import Device

BACKUP_RATE = 11 << 19
BOOT_AREAS = ("boot0", "boot1")
CATALOGS = pathlib.Path(__file__).parent / "devices"
CHUNK = 1 << 20
CID = re.compile(r"[0-9a-f]{32}")
ECHO_FIELDS = 3
FORMAT = 1
IDENTITY_OK = "identity-ok"
LABEL = re.compile(r"Fire OS (?:6 )?(\S+)")
MANIFEST = "backup.json"
READ_OK = "read-ok"


@dataclasses.dataclass(frozen=True)
class Area:
    name: str
    node: str
    first: int | None = None
    size: int | None = None


@dataclasses.dataclass(frozen=True)
class Image:
    build: str
    image: str
    sha256: str
    size: int


def areas_of(*, raw: bytes) -> tuple[list[Area], list[dict[str, int]]]:
    header = raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    entries = raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE]
    if not gpt_intact(entries=entries, header=header):
        raise FatalError(
            message=f"the {title()}'s primary partition table does not pass its"
            " own checksums, so this cannot tell what to read"
        )
    alternate, first_usable, last_usable = struct.unpack_from("<QQQ", header, 32)
    partitions = sorted(
        partition_map(entries=entries).items(), key=lambda item: item[1].first
    )
    gaps = []
    after = first_usable
    for _, partition in partitions:
        if partition.first > after:
            gaps.append({"first": after, "sectors": partition.first - after})
        after = max(after, partition.first + partition.sectors)
    if last_usable + 1 > after:
        gaps.append({"first": after, "sectors": last_usable + 1 - after})
    return [
        Area(first=0, name="gpt-primary", node=DISK, size=TABLE_SECTORS * SECTOR_SIZE),
        *(Area(name=area, node=f"{DISK}{area}") for area in BOOT_AREAS),
        *(
            Area(
                first=partition.first,
                name=name,
                node=f"{DISK}p{partition.number}",
                size=partition.size,
            )
            for name, partition in partitions
        ),
        Area(
            first=last_usable + 1,
            name="gpt-backup",
            node=DISK,
            size=(alternate - last_usable) * SECTOR_SIZE,
        ),
    ], gaps


def backup(*, directory: str, force: bool) -> None:
    if directory:
        emptied(folder=pathlib.Path(directory))
    twrp_entry(force=force)
    wait_for_twrp_start()
    device = known_device()
    detect_dd(asked=adb_shell)
    serial, cid = identity()
    now = datetime.datetime.now(tz=datetime.UTC).astimezone()
    folder = pathlib.Path(
        directory
        or f"{device.name}-{serial or 'unknown'}-{now.strftime('%Y%m%d-%H%M%S')}"
    )
    emptied(folder=folder)
    folder.mkdir(exist_ok=True, parents=True)
    unmount()
    areas, gaps = areas_of(raw=read_sectors(count=TABLE_SECTORS, start=0))
    images = catalog(device=device)
    PROGRESS.step, PROGRESS.steps = 0, len(areas)
    recorded = named(
        builds=BUILDS.get(device, {}),
        found=[stored(area=area, folder=folder, images=images) for area in areas],
    )
    PROGRESS.end()
    (folder / MANIFEST).write_text(
        json.dumps(
            {
                "areas": recorded,
                "cid": cid,
                "created": now.isoformat(timespec="seconds"),
                "device": device.name,
                "firebreak": __version__,
                "format": FORMAT,
                "gaps": gaps,
                "serial": serial,
            },
            indent=2,
        )
        + "\n"
    )
    held = sum(path.stat().st_size for path in folder.iterdir())
    passed(message=f"The {title()}'s eMMC is backed up to {folder}.")
    say(
        text=f"It takes {held >> 20} MiB here. The partitions that match an OTA"
        " image name it rather than copy it, and the gaps between partitions,"
        f" which nothing reads, are listed in {MANIFEST} and not copied. The"
        " RPMB cannot be read from TWRP, so it is not in it."
    )


def build_of(*, label: str) -> str:
    found = LABEL.fullmatch(label)
    return found.group(1) if found else ""


def catalog(*, device: Device) -> list[Image]:
    builds = BUILDS.get(device, {})
    path = CATALOGS / f"{device.name}-partitions.csv"
    if not path.is_file():
        return []
    with path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    return [
        Image(
            build=build_of(label=row["build"]),
            image=row["partition"],
            sha256=row["sha256"],
            size=int(row["bytes"]),
        )
        for row in rows
        if build_of(label=row["build"]) in builds
    ]


def checked_read(
    *, area: Area, images: list[Image], local: pathlib.Path
) -> tuple[int, str, str, list[Image]]:
    if area.node == DISK:
        data = read_sectors(
            count=(area.size or 0) // SECTOR_SIZE, start=area.first or 0
        )
        local.write_bytes(data=data)
        matches, md5, sha256 = scanned(images=images, path=local)
        return len(data), md5, sha256, matches
    size, want = on_echo(area=area)
    said = ""
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(read=True, remote=area.node)
        try:
            pulled = run(arguments=["adb", "pull", area.node, local], timeout=3600)
        except subprocess.TimeoutExpired as error:
            said = f"adb pull did not finish in {error.timeout:.0f} seconds"
            continue
        if pulled.returncode != 0:
            said = pulled.stdout.strip() or f"adb pull exited {pulled.returncode}"
            continue
        got = local.stat().st_size if local.is_file() else 0
        if got != size:
            said = f"{got} bytes arrived, not {size}"
            continue
        matches, held, sha256 = scanned(images=images, path=local)
        if held == want:
            return size, want, sha256, matches
        said = f"its md5 is {held}, not the {want} the {title()} read"
    raise FatalError(
        message=f"{area.node} did not arrive intact after {PUSH_TRIES} tries;"
        f" the last: {said}"
    )


def emptied(*, folder: pathlib.Path) -> None:
    if folder.exists() and not folder.is_dir():
        raise FatalError(
            message=f"{folder} is a file, so nothing was read. Name an empty or"
            " new directory."
        )
    if folder.exists() and any(folder.iterdir()):
        raise FatalError(
            message=f"{folder} already holds files, so nothing was read. Name an"
            " empty or new directory."
        )


def identity() -> tuple[str, str]:
    said = whole(
        marker=IDENTITY_OK,
        said=adb_shell(
            command='echo "serial=$(getprop ro.serialno)";'
            ' echo "cid=$(cat /sys/block/mmcblk0/device/cid 2>/dev/null)";'
            f" echo {IDENTITY_OK}"
        ),
    )
    fields = dict(row.strip().partition("=")[::2] for row in (said or "").splitlines())
    cid = fields.get("cid", "")
    if said is None or not CID.fullmatch(cid):
        raise FatalError(
            message=f"the {title()} did not say which Echo it is: its eMMC CID"
            f" reads {cid or 'nothing'}"
        )
    return fields.get("serial", ""), cid


def named(
    *, builds: dict[str, Download], found: list[tuple[dict, list[Image]]]
) -> list[dict]:
    chosen: list[str] = []
    left = [matches for _, matches in found if matches]
    while left:
        counts = collections.Counter(
            build for matches in left for build in {image.build for image in matches}
        )
        best = max(counts, key=counts.__getitem__)
        chosen.append(best)
        left = [
            matches for matches in left if all(image.build != best for image in matches)
        ]
    for record, matches in found:
        if not matches:
            continue
        match = next(
            image for build in chosen for image in matches if image.build == build
        )
        download = builds[match.build]
        record["extents"].insert(
            0,
            {
                "build": match.build,
                "image": match.image,
                "kind": "ota",
                "length": match.size,
                "ota": {
                    "name": download.name,
                    "sha256": download.sha256,
                    "url": download.url,
                },
                "sha256": match.sha256,
            },
        )
    return [record for record, _ in found]


def on_echo(*, area: Area) -> tuple[int, str]:
    command = (
        f'echo "$(blockdev --getsize64 {area.node})'
        f' $(md5sum {area.node} | cut -d" " -f1) {READ_OK}"'
    )
    said = adb_shell(command=command, timeout=600).split()
    if len(said) != ECHO_FIELDS or said[2] != READ_OK or not said[0].isdecimal():
        raise FatalError(
            message=f"the {title()} did not say how large {area.node} is and what"
            f" it holds: {' '.join(said) or 'nothing'}"
        )
    size = int(said[0])
    if area.size is not None and size != area.size:
        raise FatalError(
            message=f"{area.node} holds {size} bytes, where the partition table"
            f" gives {area.name} {area.size}, so the running table is not the one"
            " on the eMMC"
        )
    return size, said[1]


def scanned(*, images: list[Image], path: pathlib.Path) -> tuple[list[Image], str, str]:
    checksum = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    best: list[Image] = []
    read = 0
    with path.open(mode="rb") as file:
        for stop in (*sorted({image.size for image in images}), None):
            while stop is None or read < stop:
                chunk = file.read(CHUNK if stop is None else min(CHUNK, stop - read))
                if not chunk:
                    break
                read += len(chunk)
                checksum.update(chunk)
                md5.update(chunk)
            if read == stop:
                held = checksum.hexdigest()
                best = [
                    image
                    for image in images
                    if image.size == stop and image.sha256 == held
                ] or best
    return best, md5.hexdigest(), checksum.hexdigest()


def stored(
    *, area: Area, folder: pathlib.Path, images: list[Image]
) -> tuple[dict, list[Image]]:
    estimate = max(1, area.size // BACKUP_RATE) if area.size else 0
    PROGRESS.begin(estimate=estimate, label=f"record {area.name}")
    local = folder / f"{area.name}.img.part"
    size, md5, sha256, matches = checked_read(area=area, images=images, local=local)
    extents: list[dict[str, object]] = []
    start = matches[0].size if matches else 0
    if start < size:
        copy = f"{area.name}.gz"
        with (
            local.open(mode="rb") as source,
            gzip.open(compresslevel=6, filename=folder / copy, mode="wb") as target,
        ):
            source.seek(start)
            for chunk in iter(lambda: source.read(CHUNK), b""):
                target.write(chunk)
        extents.append({"file": copy, "kind": "copy", "length": size - start})
    local.unlink()
    return {
        "extents": extents,
        "first": area.first,
        "md5": md5,
        "name": area.name,
        "node": area.node,
        "sha256": sha256,
        "size": size,
    }, matches
