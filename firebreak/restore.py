from __future__ import annotations

import gzip
import hashlib
import json
import pathlib
import shutil
import struct
import subprocess
import zlib
from typing import TYPE_CHECKING, BinaryIO

from firebreak.android.ota import extract
from firebreak.backup import CHUNK, FORMAT, MANIFEST, READ_OK, identity
from firebreak.cache import CACHE, Download, digest, fetch
from firebreak.devices import DEVICES
from firebreak.entry import known_device, twrp_entry
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    PUSH_TRIES,
    adb_shell,
    devices,
    push_checked,
    run,
    usb_serial,
)
from firebreak.report import whole
from firebreak.stock import Shell
from firebreak.twrp import (
    DISK,
    clear_boot0,
    detect_dd,
    hashed,
    unmount,
    wait_for_twrp_start,
    write,
)
from firebreak.ui import PROGRESS, SESSION, FatalError, confirm, passed, say, title

if TYPE_CHECKING:
    from firebreak.plugin import Device

AREA_KEYS = ("extents", "first", "md5", "name", "node", "sha256", "size")
BOOTCOUNT = b"bootcount\0"
IDME = "boot1"
IDME_SIZE_AT = 16
IDME_VALUE_AT = 28
IDME_VALUE_MOST = 16
MANIFEST_KEYS = ("areas", "cid", "device", "serial")


def appended(
    *, device: Device, extent: dict, folder: pathlib.Path, target: BinaryIO
) -> int:
    if extent["kind"] == "copy":
        source = gzip.GzipFile(filename=folder / extent["file"], mode="rb")
    else:
        source = ota_image(device=device, extent=extent).open(mode="rb")
    with source:
        left = extent["length"]
        while left:
            chunk = source.read(min(CHUNK, left))
            if not chunk:
                break
            target.write(chunk)
            left -= len(chunk)
    return left


def attached_serial() -> str | None:
    serial = usb_serial()
    if serial:
        return serial
    serials = [
        line.split()[0]
        for line in devices(arguments=["fastboot", "devices"]).splitlines()
        if line.split()[1:2] == ["fastboot"]
    ]
    return serials[0] if len(serials) == 1 else None


def bootcount(*, image: bytes) -> slice | None:
    at = image.find(BOOTCOUNT)
    if at < 0 or len(image) < at + IDME_VALUE_AT:
        return None
    (size,) = struct.unpack_from("<I", image, at + IDME_SIZE_AT)
    start = at + IDME_VALUE_AT
    if not 0 < size <= IDME_VALUE_MOST or len(image) < start + size:
        return None
    return slice(start, start + size)


def built(
    *, area: dict, device: Device, folder: pathlib.Path, work: pathlib.Path
) -> pathlib.Path:
    path = work / f"{area['name']}.img"
    try:
        with path.open(mode="wb") as target:
            short = sum(
                appended(device=device, extent=extent, folder=folder, target=target)
                for extent in area["extents"]
            )
    except (EOFError, KeyError, OSError, zlib.error) as error:
        raise FatalError(
            message=f"{area['name']} could not be rebuilt from the backup"
            f" ({error!r}), so nothing was written"
        ) from error
    if short:
        raise FatalError(
            message=f"{area['name']} came up {short} bytes short of its backup,"
            " so nothing was written"
        )
    if (
        path.stat().st_size != area["size"]
        or digest(kind="sha256", path=path) != area["sha256"]
    ):
        raise FatalError(
            message=f"{area['name']} does not rebuild to the bytes the backup"
            " read, so nothing was written"
        )
    return path


def counted_on(*, area: dict, path: pathlib.Path) -> dict:
    held = path.with_suffix(".now")
    if run(arguments=["adb", "pull", area["node"], held], timeout=60).returncode:
        return area
    now = held.read_bytes() if held.is_file() else b""
    image = bytearray(path.read_bytes())
    there, here = bootcount(image=now), bootcount(image=bytes(image))
    if there is None or here is None:
        return area
    value = now[there].rstrip(b"\0")
    width = here.stop - here.start
    if not value.isdigit() or len(value) > width:
        return area
    image[here] = value.ljust(width, b"\0")
    path.write_bytes(image)
    passed(message=f"boot1 keeps this {title()}'s boot count, {value.decode()}")
    return {**area, "md5": hashlib.md5(image, usedforsecurity=False).hexdigest()}


def loaded(*, folder: pathlib.Path) -> dict:
    try:
        manifest = json.loads((folder / MANIFEST).read_text())
    except (OSError, ValueError) as error:
        raise FatalError(
            message=f"{folder / MANIFEST} could not be read: {error}"
        ) from error
    if manifest.get("format") != FORMAT:
        raise FatalError(
            message=f"{folder / MANIFEST} is format {manifest.get('format')}, and"
            f" this firebreak reads format {FORMAT}"
        )
    if any(key not in manifest for key in MANIFEST_KEYS) or any(
        key not in area for area in manifest["areas"] for key in AREA_KEYS
    ):
        raise FatalError(message=f"{folder / MANIFEST} is missing fields it needs")
    return manifest


def ota_extents(*, manifest: dict) -> list[dict]:
    return [
        extent
        for area in manifest["areas"]
        for extent in area["extents"]
        if extent["kind"] == "ota"
    ]


def ota_image(*, device: Device, extent: dict) -> pathlib.Path:
    update = ota_update(extent=extent)
    path = ota_path(device=device.name, extent=extent)
    work = path.parent
    work.mkdir(exist_ok=True, parents=True)
    extract(update=update, wanted=(extent["image"],), work=work)
    if (
        not path.is_file()
        or digest(kind="sha256", limit=extent["length"], path=path) != extent["sha256"]
    ):
        raise FatalError(
            message=f"the {extent['image']} image of {extent['ota']['name']} is not"
            " the one the backup names, so nothing was written"
        )
    return path


def ota_path(*, device: str, extent: dict) -> pathlib.Path:
    return CACHE / f"stock-{device}-{extent['build']}" / f"{extent['image']}.img"


def ota_update(*, extent: dict) -> pathlib.Path:
    ota = extent["ota"]
    return fetch(
        download=Download(name=ota["name"], sha256=ota["sha256"], url=ota["url"])
    )


def reread(*, areas: list[dict]) -> None:
    unmount(started=True)
    adb_shell(command=f"blockdev --rereadpt {DISK}")
    said = whole(
        marker=READ_OK, said=adb_shell(command=f"cat /proc/partitions; echo {READ_OK}")
    )
    held = {" ".join(row.split()[-2:]) for row in (said or "").splitlines()}
    wrong = [
        area["name"]
        for area in areas
        if area["node"].startswith(f"{DISK}p")
        and f"{area['size'] // 1024} {area['node'].rsplit('/', 1)[1]}" not in held
    ]
    if said is None:
        wrong = ["no answer"]
    if wrong:
        raise FatalError(
            message="the kernel does not see the backup's partition table, so no"
            f" partition was written ({', '.join(wrong)}); do not reboot"
        )


def restore(*, directory: str, force: bool) -> None:
    folder = pathlib.Path(directory)
    manifest = loaded(folder=folder)
    work = CACHE / f"restore-{manifest['serial'] or 'unknown'}"
    shutil.rmtree(ignore_errors=True, path=work)
    work.mkdir(parents=True)
    try:
        restored(folder=folder, force=force, manifest=manifest, work=work)
    finally:
        shutil.rmtree(ignore_errors=True, path=work)


def restored(
    *, folder: pathlib.Path, force: bool, manifest: dict, work: pathlib.Path
) -> None:
    serial = attached_serial()
    if serial and manifest["serial"] and serial != manifest["serial"]:
        raise FatalError(
            message=f"the backup is of the Echo {manifest['serial']}, and this is"
            f" {serial}. It holds that Echo's IDME and keys, so nothing was written"
        )
    extents = ota_extents(manifest=manifest)
    for extent in extents:
        ota_update(extent=extent)
    pending = {
        ota_path(device=manifest["device"], extent=extent): extent["length"]
        for extent in extents
    }
    needed = sum(area["size"] for area in manifest["areas"]) + sum(
        length for path, length in pending.items() if not path.is_file()
    )
    free = shutil.disk_usage(work).free
    if free < needed:
        raise FatalError(
            message=f"rebuilding the backup takes {needed >> 20} MiB in"
            f" {work.parent}, which has {free >> 20} MiB free, so nothing was"
            " written"
        )
    twrp_entry(
        force=force,
        named=next(
            (device for device in DEVICES if device.name == manifest["device"]),
            None,
        ),
    )
    wait_for_twrp_start()
    device = known_device()
    if manifest["device"] != device.name:
        raise FatalError(
            message=f"the backup is of a {manifest['device']}, and this is a"
            f" {device.name}, so nothing was written"
        )
    serial, cid = identity()
    if manifest["cid"] != cid:
        raise FatalError(
            message=f"the backup is of the Echo {manifest['serial']}, whose eMMC is"
            f" not this one, {serial}. It holds that Echo's IDME and keys, so"
            " nothing was written"
        )
    detect_dd(asked=adb_shell)
    areas = manifest["areas"]
    images = {
        area["name"]: built(area=area, device=device, folder=folder, work=work)
        for area in areas
    }
    passed(message=f"Every area of the backup rebuilt to the bytes it read in {work}")
    areas = [
        counted_on(area=area, path=images[IDME]) if area["name"] == IDME else area
        for area in areas
    ]
    confirm(
        force=force,
        what=f"restoring {folder} overwrites every partition of this {title()},"
        " its boot areas and its partition table",
    )
    unmount()
    PROGRESS.step, PROGRESS.steps = 0, len(areas) + 1
    PROGRESS.begin(estimate=5, label="clear the preloader header (boot0)")
    SESSION.boot0_erased = True
    clear_boot0()
    order = sorted(
        areas,
        key=lambda area: (
            area["name"] != "gpt-backup",
            area["name"] != "gpt-primary",
            area["name"] == "boot0",
        ),
    )
    try:
        for area in order:
            written(area=area, path=images[area["name"]])
            if area["name"] == "gpt-primary":
                reread(areas=areas)
    except subprocess.TimeoutExpired as error:
        raise FatalError(
            message=f"{' '.join(map(str, error.cmd))} did not finish in"
            f" {error.timeout:.0f} seconds; do not reboot"
        ) from error
    SESSION.boot0_erased = False
    PROGRESS.end()
    passed(message=f"The {title()} holds the bytes of {folder} again.")
    say(
        text="It waits in TWRP. The gaps between partitions were not in the"
        " backup and are as they were. Run `firebreak reboot` to start it."
    )


def written(*, area: dict, path: pathlib.Path) -> None:
    label = f"write {area['name']}"
    estimate = max(1, area["size"] >> 24)
    node = area["node"]
    if node == DISK:
        write(estimate=estimate, label=label, path=path, sector=area["first"])
        return
    if node.startswith(f"{DISK}p"):
        write(
            estimate=estimate,
            label=label,
            number=int(node[len(DISK) + 1 :]),
            path=path,
            sector=area["first"],
        )
        return
    PROGRESS.begin(estimate=estimate, label=label)
    want = area["md5"]
    if hashed(command=f"md5sum {node}", remote=node, size=area["size"]) == want:
        PROGRESS.end(skipped=True)
        return
    staged = DOT_TEMPORARY_DIRECTORY / path.name
    push_checked(advice="Do not reboot. ", local=path, remote=staged)
    got = ""
    for _ in range(PUSH_TRIES):
        adb_shell(
            command=Shell.BOOT_AREA.value.format(area=area["name"], source=staged)
        )
        got = hashed(command=f"md5sum {node}", remote=node, size=area["size"])
        if got in {want, ""}:
            break
    if not got:
        raise FatalError(
            message=f"{area['name']} could not be read back after {PUSH_TRIES}"
            " tries; do not reboot"
        )
    if got != want:
        raise FatalError(
            message=f"{area['name']} did not verify: read {got}, expected {want};"
            " do not reboot"
        )
    PROGRESS.end()
