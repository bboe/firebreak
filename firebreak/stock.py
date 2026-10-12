from __future__ import annotations

import contextlib
import dataclasses
import enum
import os
import subprocess
import time
from typing import TYPE_CHECKING

from firebreak import updates
from firebreak.android.gpt import gpt_intact, stock_gpt
from firebreak.android.ota import extract
from firebreak.cache import CACHE, ERASED, digest
from firebreak.host import DOT_TEMPORARY_DIRECTORY, adb_shell, md5_mismatch, run
from firebreak.twrp import (
    DISK,
    clear_boot0,
    read_sectors,
    restore_failed,
    unmount,
    write,
)
from firebreak.ui import (
    ARGUMENTS,
    PROGRESS,
    SESSION,
    ANSIColor,
    FatalError,
    Kind,
    again,
    paint,
    passed,
    show,
    warn,
)
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import TWRP_VERSION

if TYPE_CHECKING:
    import pathlib

    from firebreak.android.gpt import Partition


BOOTLOADER_CONTROL_BLOCK = b"\0ABB\x01\x8f\0"
BOOTLOADER_CONTROL_BLOCK_OFFSET = 0x360
CHAIN_TEE = ("tee2", "tee1")
STOCK_STEPS = 16
TWRP_VERSIONS = ("3.2.", "3.7.")


class Shell(enum.Enum):
    BOOT0 = (
        "d=dd; toybox dd --help >/dev/null 2>&1 && d='toybox dd'; "
        "echo 0 > /sys/block/mmcblk0boot0/force_ro; "
        "$d if={source} of=/dev/block/mmcblk0boot0 bs=1048576 2>/dev/null; "
        "echo 1 > /sys/block/mmcblk0boot0/force_ro; sync; "
        "echo 3 > /proc/sys/vm/drop_caches"
    )
    TOOLS = (
        "m=; for t in sgdisk mke2fs blockdev md5sum; do"
        ' command -v "$t" >/dev/null 2>&1 || which "$t" >/dev/null 2>&1'
        ' || m="$m $t"; done; echo "tools:$m"'
    )


@dataclasses.dataclass(frozen=True)
class Step:
    estimate: str
    image: str
    label: str
    partition: str


WRITES = (
    Step(
        estimate="4 min",
        image="system",
        label="write the system image to system_a",
        partition="system_a",
    ),
    Step(
        estimate="4 min",
        image="system",
        label="write the system image to system_b",
        partition="system_b",
    ),
    Step(
        estimate="10 s",
        image="boot",
        label="write boot image to boot_a",
        partition="boot_a",
    ),
    Step(
        estimate="10 s",
        image="boot",
        label="write boot image to boot_b",
        partition="boot_b",
    ),
    Step(
        estimate="5 s",
        image="misc",
        label="write misc, slot a marked good",
        partition="misc",
    ),
)


def chain_writes() -> tuple[Step, ...]:
    live = (
        "lk_b" if adb_shell(command="getprop ro.boot.slot_suffix") == "_b" else "lk_a"
    )
    spare = "lk_a" if live == "lk_b" else "lk_b"
    first, last = CHAIN_TEE
    return (
        Step(
            estimate="5 s",
            image="lk",
            label=f"write LK image to {spare} (spare slot)",
            partition=spare,
        ),
        Step(
            estimate="5 s",
            image="tee",
            label=f"write TEE image to {first} (backup)",
            partition=first,
        ),
        Step(
            estimate="5 s",
            image="expdb",
            label="zero expdb (amonet kaeru payload)",
            partition="expdb",
        ),
        Step(
            estimate="5 s",
            image="lk",
            label=f"write LK image to {live} (live slot)",
            partition=live,
        ),
        Step(
            estimate="5 s",
            image="tee",
            label=f"write TEE image to {last} (primary)",
            partition=last,
        ),
    )


def restore(
    *,
    backup_sector: int,
    build: str,
    files: dict[str, pathlib.Path],
    parts: dict[str, Partition],
    work: pathlib.Path,
) -> None:
    unmount()

    PROGRESS.begin(estimate="5 s", label="clear the preloader header (boot0)")
    ERASED.touch()
    clear_boot0()
    PROGRESS.end()

    for step in WRITES:
        write(
            estimate=step.estimate,
            label=step.label,
            number=parts[step.partition].number,
            path=files[step.image],
            sector=parts[step.partition].first,
        )
    write(
        estimate="5 s",
        label="write the stock table (backup)",
        path=files["gpt-backup.bin"],
        sector=backup_sector,
    )
    write(
        estimate="5 s",
        label="write the stock table (primary)",
        path=files["gpt-primary.bin"],
        sector=0,
    )

    PROGRESS.begin(estimate="30 s", label="format cache and userdata")
    if "No problems found" not in adb_shell(command="sgdisk --verify " + DISK):
        restore_failed(message="sgdisk does not accept the new table; do not reboot")
    unmount(started=True)
    adb_shell(command="blockdev --rereadpt " + DISK)
    if adb_shell(command='grep -c "mmcblk0p1[78]$" /proc/partitions') != "0":
        restore_failed(
            message="the kernel still sees amonet's partitions; do not reboot,"
            " reread the table first"
        )
    userdata, cache = parts["userdata"], parts["cache"]
    kibibytes = userdata.size // 1024
    if not adb_shell(
        command=f'grep " {kibibytes} mmcblk0p{userdata.number}$" /proc/partitions'
    ):
        restore_failed(message="userdata is not its stock size; do not reboot")
    output = adb_shell(
        command=f"mke2fs -q -t ext4 {DISK}p{cache.number}"
        f" && mke2fs -q -t ext4 {DISK}p{userdata.number} && echo formatted"
    )
    if output.split(sep="\n")[-1] != "formatted":
        restore_failed(message="cache and userdata did not format; do not reboot")
    PROGRESS.end()

    for step in chain_writes():
        write(
            estimate=step.estimate,
            label=step.label,
            number=parts[step.partition].number,
            path=files[step.image],
            sector=parts[step.partition].first,
        )

    PROGRESS.begin(estimate="5 s", label="write preloader to boot0")
    preloader = work / "preloader.img"
    staged = DOT_TEMPORARY_DIRECTORY / "pl.img"
    if run(arguments=["adb", "push", preloader, staged], timeout=120).returncode != 0:
        restore_failed(message="the preloader did not reach the Dot; do not reboot")
    adb_shell(command=Shell.BOOT0.value.format(source=staged))
    wrong = md5_mismatch(
        command="md5sum /dev/block/mmcblk0boot0",
        want=digest(kind="md5", path=preloader),
    )
    if wrong:
        restore_failed(
            message=f"boot0 does not match the {build} preloader{wrong}; do not reboot"
        )
    ERASED.unlink(missing_ok=True)
    PROGRESS.end()

    PROGRESS.begin(estimate="90 s", label=f"waiting for stock {build} to start")
    with contextlib.suppress(subprocess.TimeoutExpired):
        run(arguments=["adb", "shell", "-n", "reboot"], timeout=60)


def stage_restore() -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    build = ARGUMENTS.build
    work = CACHE / ("stock-" + build)
    work.mkdir(exist_ok=True, parents=True)
    extract(update=updates.download(build=build), work=work)
    deadline = time.monotonic() + 30
    version = ""
    while not version or "mtp" not in adb_shell(command="getprop sys.usb.config"):
        if time.monotonic() > deadline:
            raise FatalError(message="TWRP did not finish starting within 30 seconds")
        time.sleep(1)
        version = adb_shell(command="getprop ro.twrp.version")
        if not version[:1].isdigit():
            version = ""
        elif not version.startswith(TWRP_VERSIONS):
            raise FatalError(
                message="this needs a TWRP for this Dot: v1.1.0's 3.2.3,"
                f" v2.0.0's 3.7.0, or the {TWRP_VERSION} that firebreak"
                " installs"
            )
    if (
        adb_shell(command="toybox dd --help >/dev/null 2>&1 && echo yes").split(
            sep="\n"
        )[-1]
        == "yes"
    ):
        SESSION.dd = "toybox dd"
    tools = adb_shell(command=Shell.TOOLS.value).split(sep="\n")[-1]
    if not tools.startswith("tools:"):
        raise FatalError(message="the Dot did not answer which tools it has: " + tools)
    if tools != "tools:":
        raise FatalError(message="this TWRP has no" + tools[len("tools:") :])
    device = adb_shell(command="getprop ro.product.device")
    if device != "biscuit":
        raise FatalError(
            message="this is not an Echo Dot (2nd Gen): TWRP reports the"
            f" device {device!r}"
        )

    raw = read_sectors(count=34, start=0)
    if not gpt_intact(entries=raw[1024:], header=raw[512:1024]):
        size = adb_shell(command=f"blockdev --getsize64 {DISK}")
        if not size.isdigit():
            raise FatalError(message="could not read the Dot's disk size")
        tail = read_sectors(count=33, start=int(size) // 512 - 33)
        raw = raw[:512] + tail[-512:] + tail[:-512]
        show(text="the primary partition table is damaged; using the backup")
    saved = work / f"current-gpt-{os.environ['ANDROID_SERIAL']}.bin"
    if not saved.exists():
        saved.write_bytes(data=raw)
    table = stock_gpt(raw=raw)
    files = {}
    for name, data in (
        ("gpt-primary.bin", table.primary),
        ("gpt-backup.bin", table.backup),
    ):
        files[name] = work / name
        files[name].write_bytes(data=data)
    boot = work / "boot.img"
    boot_size = table.partitions["boot_a"].size
    files["boot"] = work / "boot16.img"
    files["boot"].write_bytes(data=boot.read_bytes().ljust(boot_size, b"\0"))
    files["expdb"] = work / "expdb.zero"
    files["expdb"].write_bytes(data=b"\0" * table.partitions["expdb"].size)
    misc = bytearray(table.partitions["misc"].size)
    misc[
        BOOTLOADER_CONTROL_BLOCK_OFFSET : BOOTLOADER_CONTROL_BLOCK_OFFSET
        + len(BOOTLOADER_CONTROL_BLOCK)
    ] = BOOTLOADER_CONTROL_BLOCK
    files["misc"] = work / "misc.img"
    files["misc"].write_bytes(data=misc)
    for image in ("system", "tee", "lk"):
        files[image] = work / (image + ".img")
    for step in (*WRITES, *chain_writes()):
        if files[step.image].stat().st_size > table.partitions[step.partition].size:
            raise FatalError(
                message=f"{files[step.image].name} does not fit {step.partition}"
            )
    if (
        adb_shell(command="[ -b /dev/block/mmcblk0boot0 ] && echo block").split(
            sep="\n"
        )[-1]
        != "block"
    ):
        raise FatalError(
            message="/dev/block/mmcblk0boot0 is not a block device, so the"
            " preloader would be written to a file and read back from it"
        )
    boot0 = adb_shell(command="cat /sys/block/mmcblk0boot0/size")
    if (
        not boot0.isdigit()
        or (work / "preloader.img").stat().st_size != int(boot0) * 512
    ):
        raise FatalError(
            message=f"preloader.img is not the size of boot0 ({boot0} sectors)"
        )
    passed(message="stock partition table built from this Dot's own")
    warn(
        text="About to overwrite this Dot's bootloaders, system and data with"
        f" stock {build}."
    )
    warn(text="Root is gone afterwards; firebreak puts it back.")
    try:
        for left in range(10, 0, -1):
            show(
                end="",
                flush=True,
                kind=Kind.WARN,
                text="\r"
                + paint(
                    code=ANSIColor.YELLOW,
                    text=f"Starting in {left:2d} s. Ctrl-C cancels.",
                ),
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        raise FatalError(message="stopped; nothing was written", prefix="") from None
    show(
        kind=Kind.WARN,
        text="\r"
        + paint(code=ANSIColor.YELLOW, text="Starting now.                     "),
    )

    try:
        restore(
            backup_sector=table.backup_sector,
            build=build,
            files=files,
            parts=table.partitions,
            work=work,
        )
    except subprocess.TimeoutExpired as error:
        restore_failed(
            message=f"{' '.join(map(str, error.cmd))} did not finish in"
            f" {error.timeout:.0f} seconds. Do not reboot. " + again()
        )
    except KeyboardInterrupt:
        if PROGRESS.step == PROGRESS.steps:
            raise FatalError(
                message=f"stopped; stock {build} is in place", prefix=""
            ) from None
        restore_failed(message="stopped part way. Do not reboot. " + again())
