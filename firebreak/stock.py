from __future__ import annotations

import contextlib
import dataclasses
import enum
import os
import subprocess
import time
import zipfile
from typing import TYPE_CHECKING

from firebreak import updates
from firebreak.android.gpt import SECTOR_SIZE, gpt_intact, stock_gpt
from firebreak.android.ota import extract
from firebreak.bootrom_step import stock_preloader
from firebreak.cache import CACHE, ERASED, digest
from firebreak.devices import BUILDS, biscuit
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    adb_shell,
    in_fastboot,
    md5_mismatch,
    pyserial_wheel,
    run,
)
from firebreak.plan import (
    BOOTLOADER_CONTROL_BLOCK,
    BOOTLOADER_CONTROL_BLOCK_OFFSET,
    TABLE_SECTORS,
)
from firebreak.report import whole
from firebreak.survey import build_properties
from firebreak.twrp import (
    DISK,
    clear_boot0,
    read_sectors,
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
from firebreak.unlock import amonet_v2_payload

if TYPE_CHECKING:
    import pathlib

    from firebreak.android.gpt import Partition


CHAIN_TEE = ("tee2", "tee1")
NAMED = "device-named"
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
        estimate="240 s",
        image="system",
        label="write the system image to system_a",
        partition="system_a",
    ),
    Step(
        estimate="240 s",
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


def made_for(*, update: pathlib.Path) -> str:
    with zipfile.ZipFile(file=update) as archive:
        named = build_properties(archive=archive).get("ro.product.device", "")
    return named.removesuffix("_puffin")


def reboot_into_fastboot() -> None:
    PROGRESS.begin(estimate="20 s", label="rebooting into fastboot")
    with contextlib.suppress(subprocess.TimeoutExpired):
        run(arguments=["adb", "reboot", "bootloader"], timeout=60)
    wait_for_fastboot()


def restore(  # ruff: ignore[complex-structure]
    *,
    backup_sector: int,
    build: str,
    files: dict[str, pathlib.Path],
    parts: dict[str, Partition],
    work: pathlib.Path,
) -> None:
    unmount()

    PROGRESS.begin(estimate="5 s", label="clear the preloader header (boot0)")
    ERASED.write_text(ARGUMENTS.target.device.name)
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
        raise FatalError(message="sgdisk does not accept the new table; do not reboot")
    unmount(started=True)
    adb_shell(command="blockdev --rereadpt " + DISK)
    if adb_shell(command='grep -c "mmcblk0p1[78]$" /proc/partitions') != "0":
        raise FatalError(
            message="the kernel still sees amonet's partitions; do not reboot,"
            " reread the table first"
        )
    userdata, cache = parts["userdata"], parts["cache"]
    kibibytes = userdata.size // 1024
    if not adb_shell(
        command=f'grep " {kibibytes} mmcblk0p{userdata.number}$" /proc/partitions'
    ):
        raise FatalError(message="userdata is not its stock size; do not reboot")
    output = adb_shell(
        command=f"mke2fs -q -t ext4 {DISK}p{cache.number}"
        f" && mke2fs -q -t ext4 {DISK}p{userdata.number} && echo formatted"
    )
    if output.split(sep="\n")[-1] != "formatted":
        raise FatalError(message="cache and userdata did not format; do not reboot")
    PROGRESS.end()

    for step in chain_writes():
        write(
            estimate=step.estimate,
            label=step.label,
            number=parts[step.partition].number,
            path=files[step.image],
            sector=parts[step.partition].first,
        )

    if build in biscuit.BOOTROM_BUILDS:
        PROGRESS.begin(estimate="5 s", label="rebooting into the bootrom")
        with contextlib.suppress(subprocess.TimeoutExpired):
            run(arguments=["adb", "shell", "-n", "reboot"], timeout=60)
        stock_preloader(
            build=build,
            payload=amonet_v2_payload(),
            preloader=(work / "preloader.img").read_bytes(),
            wheel=pyserial_wheel(),
        )
        return

    PROGRESS.begin(estimate="5 s", label="write preloader to boot0")
    preloader = work / "boot0.img"
    staged = DOT_TEMPORARY_DIRECTORY / "pl.img"
    if run(arguments=["adb", "push", preloader, staged], timeout=120).returncode != 0:
        raise FatalError(message="the preloader did not reach the Dot; do not reboot")
    adb_shell(command=Shell.BOOT0.value.format(source=staged))
    wrong = md5_mismatch(
        command="md5sum /dev/block/mmcblk0boot0",
        want=digest(kind="md5", path=preloader),
    )
    if wrong:
        raise FatalError(
            message=f"boot0 does not match the {build} preloader{wrong}; do not reboot"
        )
    ERASED.unlink(missing_ok=True)
    PROGRESS.end()

    if SESSION.fastboot:
        reboot_into_fastboot()
        return
    if build in biscuit.FIREOS5_BUILDS:
        PROGRESS.begin(estimate="5 s", label=f"rebooting into stock {build}")
    else:
        PROGRESS.begin(estimate="90 s", label=f"waiting for stock {build} to start")
    with contextlib.suppress(subprocess.TimeoutExpired):
        run(arguments=["adb", "shell", "-n", "reboot"], timeout=60)


def stage_restore() -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    build = ARGUMENTS.build
    device = ARGUMENTS.target.device
    work = CACHE / ("stock-" + build)
    work.mkdir(exist_ok=True, parents=True)
    update = updates.download(build=build, builds=BUILDS[device])
    made = made_for(update=update)
    if made != device.name:
        raise FatalError(
            message=f"OTA {build} is for {made!r}, not {device.name}, so nothing"
            " was written"
        )
    extract(update=update, work=work)
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
                f" v2's 3.7.0, or the {biscuit.BBOE_TWRP_VERSION} that firebreak"
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
    named = whole(
        marker=NAMED,
        said=adb_shell(command=f"getprop ro.product.device; echo {NAMED}"),
    )
    if named != device.name:
        raise FatalError(
            message=f"this is not an {device.title}: TWRP reports the device {named!r}"
        )

    raw = read_sectors(count=TABLE_SECTORS, start=0)
    if not gpt_intact(
        entries=raw[2 * SECTOR_SIZE :], header=raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    ):
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
    preloader = (work / "preloader.img").read_bytes()
    if not boot0.isdigit() or len(preloader) > int(boot0) * 512:
        raise FatalError(message=f"preloader.img does not fit boot0 ({boot0} sectors)")
    (work / "boot0.img").write_bytes(data=preloader.ljust(int(boot0) * 512, b"\0"))
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
        raise FatalError(
            message=f"{' '.join(map(str, error.cmd))} did not finish in"
            f" {error.timeout:.0f} seconds. Do not reboot. " + again()
        ) from error
    except KeyboardInterrupt:
        if PROGRESS.step == PROGRESS.steps:
            raise FatalError(
                message=f"stopped; stock {build} is in place", prefix=""
            ) from None
        raise FatalError(
            message="stopped part way. Do not reboot. " + again()
        ) from None


def wait_for_fastboot() -> None:
    deadline = time.monotonic() + 120
    while True:
        with contextlib.suppress(subprocess.TimeoutExpired):
            if in_fastboot():
                break
        if time.monotonic() > deadline:
            raise FatalError(
                message="the Dot did not reach fastboot within 2 minutes. " + again()
            )
        time.sleep(2)
    PROGRESS.end()
