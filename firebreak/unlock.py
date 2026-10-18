from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

from firebreak import lk_unlock, updates
from firebreak.android.ota import extract
from firebreak.bootrom_step import bootrom_step
from firebreak.cache import CACHE, ERASED, digest, fetch, unpack
from firebreak.devices import BISCUIT, LITTLE_KERNEL_DESCRIPTION, LK, UNLOCK_BUILDS
from firebreak.host import PUSH_TRIES, adb_shell, getvar, pyserial_wheel, reconnect, run
from firebreak.recovery import MD5_DIGITS
from firebreak.twrp import DISK, partitions
from firebreak.ui import (
    ARGUMENTS,
    PROGRESS,
    FatalError,
    again,
    asked_for,
    invocation,
)
from firebreak.unlocks import (
    amonet_biscuit_v1_1_0,
    amonet_biscuit_v1_1_0_bboe,
    amonet_biscuit_v2_0_0,
)
from firebreak.unlocks.targets import FASTBRICKS, TARGETS

if TYPE_CHECKING:
    import pathlib

    from firebreak.cache import Download

UNLOCK_TARGET = "firebreak"


def amonet_chain() -> None:
    part = partitions()
    for slot in ("lk_a", "lk_b"):
        if slot not in part:
            raise FatalError(
                message=f"the Dot's partition table has no {slot}. " + again()
            )
    if any(amonet_lk(node=f"{DISK}p{part[slot][0]}") for slot in ("lk_a", "lk_b")):
        return
    raise FatalError(
        message="neither lk_a nor lk_b holds an amonet LK for this device, so"
        " this Dot is locked and the recovery it started is one amonet left"
        " behind. Nothing was written. Unlock it first: unplug the USB cable,"
        " hold the action button, plug it back in, and let go when the ring"
        " turns green. " + again()
    )


def amonet_lk(*, node: str) -> bool:
    for download in amonet_sources():
        local = unpack(download=download) / "bin" / "lk.bin"
        want = digest(kind="md5", path=local)
        for attempt in range(PUSH_TRIES):
            read = adb_shell(
                command=f"[ -b {node} ] && dd if={node} bs={local.stat().st_size}"
                " count=1 2>/dev/null | md5sum",
                timeout=120,
            )
            held = read.split(sep="\n")[-1].split(sep=" ")[0]
            if held == want:
                return True
            if len(held) == MD5_DIGITS:
                break
            if attempt + 1 < PUSH_TRIES:
                reconnect(remote=DISK)
        if len(held) != MD5_DIGITS:
            raise FatalError(
                message=f"{node} did not answer with an md5 of its first"
                f" {local.stat().st_size} bytes: {held or 'nothing'}. Nothing"
                " was written. " + again() + " " + asked_for()
            )
    return False


def amonet_sources() -> tuple[Download, ...]:
    device = ARGUMENTS.target.device
    return tuple(
        dict.fromkeys((
            FASTBRICKS[device].source,
            *(
                target.unlock.source
                for target in TARGETS[device].values()
                if target.unlock
            ),
        ))
    )


def amonet_v2_0_0_payload() -> pathlib.Path:
    amonet = unpack(download=amonet_biscuit_v2_0_0.SOURCE)
    return amonet / "brom-payload" / "build" / "payload.bin"


def check_product() -> None:
    device = ARGUMENTS.target.device
    product = getvar(name="product")
    if not product:
        raise FatalError(
            message="fastboot reports no product, so nothing was written. " + again()
        )
    if product != device.product:
        raise FatalError(
            message=f"fastboot reports {product!r}, not {device.product}, so"
            f" nothing was written. {ARGUMENTS.target.name} is for the"
            f" {device.title}."
        )


def erase_by_fastboot() -> str:
    erased = run(arguments=["fastboot", "erase", "boot0"], timeout=60)
    if erased.returncode != 0:
        ERASED.unlink(missing_ok=True)
        return f"fastboot erase boot0 failed:\n{erased.stdout}"
    rebooted = run(arguments=["fastboot", "reboot"], timeout=60)
    if rebooted.returncode != 0:
        return f"fastboot reboot failed:\n{rebooted.stdout}"
    return ""


def stage_amonet_v1_1_0_recovery() -> bool:
    unlocked = ""
    for _ in range(PUSH_TRIES):
        unlocked = getvar(name="unlock_status").lower()
        if unlocked in {"true", "false"}:
            break
        time.sleep(1)
    if unlocked == "false":
        PROGRESS.note(
            message="The Dot came back in its own locked fastboot rather than"
            " amonet's, which accepts nothing this needs. This run unlocks it again"
            " and goes on from v2.0.0's recovery."
        )
        return False
    if unlocked != "true":
        raise FatalError(
            message="the Dot's fastboot did not say whether it is unlocked. " + again()
        )
    amonet = unpack(download=amonet_biscuit_v1_1_0.SOURCE)
    twrp = fetch(download=amonet_biscuit_v1_1_0_bboe.RECOVERY)
    PROGRESS.begin(
        estimate="30 s",
        label=f"waiting for TWRP {amonet_biscuit_v1_1_0_bboe.TWRP_VERSION}",
    )
    run(
        arguments=["fastboot", "-S", "256M", "flash", "tee2", "bin/tz.img"],
        check=True,
        directory=amonet,
        timeout=120,
    )
    run(
        arguments=["fastboot", "-S", "256M", "flash", "recovery", twrp],
        check=True,
        timeout=120,
    )
    run(
        arguments=["fastboot", "oem", "reboot-recovery"],
        check=True,
        directory=amonet,
        timeout=60,
    )
    return True


def stage_downgrade() -> bool:
    amonet = unpack(download=amonet_biscuit_v1_1_0.SOURCE)
    wheel = pyserial_wheel()
    if getvar(name="unlock_status").lower() != "true":
        raise FatalError(message="not in amonet's fastboot")
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if not LITTLE_KERNEL_DESCRIPTION.fullmatch(string=little_kernel):
        raise FatalError(
            message="the Dot did not report its bootloader version;"
            " boot0 was not erased. " + again()
        )
    if little_kernel == LK.FIREOS5.value:
        raise FatalError(
            message="the Dot already runs amonet v1.1.0's bootloader. " + again()
        )
    PROGRESS.begin(
        estimate="5 s", label="erasing boot0 so the Dot falls into its bootrom"
    )
    bootrom_step(
        amonet=amonet,
        erase=erase_by_fastboot,
        payload=amonet_v2_0_0_payload(),
        wheel=wheel,
    )
    return stage_amonet_v1_1_0_recovery()


def stage_fastbrick() -> None:
    fastbrick = FASTBRICKS[ARGUMENTS.target.device]
    amonet = unpack(download=fastbrick.source)
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if not little_kernel:
        raise FatalError(
            message="fastboot did not report the bootloader version;"
            " the Dot was not modified"
        )
    image = fastbrick.fastbricks.get(little_kernel)
    if not image:
        short = invocation(options=["--short", *sys.argv[1:]])
        raise FatalError(
            message=f"no Fire OS that firebreak knows ships the bootloader"
            f" {little_kernel}, so {fastbrick.name} has no fastbrick for it;"
            " the Dot was not modified. "
            + (
                "Its bootrom can still unlock it: open it as README.md's --short"
                f" section says, then run {short}."
                if fastbrick.device == BISCUIT
                else asked_for()
            )
        )
    PROGRESS.begin(estimate="10 s", label=f"unlocking with {fastbrick.name}")
    for attempt in range(10):
        if attempt:
            time.sleep(2)
        arguments = ["fastboot", "-S", "256M", "flash", "brick", image]
        try:
            output = run(arguments=arguments, directory=amonet, timeout=8).stdout
            started = False
        except subprocess.TimeoutExpired as error:
            output = (error.output or b"").decode(encoding="utf-8", errors="replace")
            started = True
        if "eMMC-RO" in output:
            raise FatalError(message="the Dot's eMMC is read-only; it was not modified")
        if "Device mismatch" in output:
            raise FatalError(
                message="the payload rejected this device; it was not modified"
            )
        if started:
            PROGRESS.begin(
                estimate="40 s", label="waiting for v2.0.0 recovery to start"
            )
            return
    raise FatalError(
        message=f"the unlock did not start after 10 attempts, with {image} for"
        f" the bootloader {little_kernel}; the Dot was not modified"
    )


def stage_unlock() -> bool:
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if little_kernel not in UNLOCK_BUILDS:
        raise FatalError(
            message=f"the Dot reports the bootloader {little_kernel!r}, which"
            " this cannot unlock, so nothing was written. " + again()
        )
    build = UNLOCK_BUILDS[little_kernel]
    device = ARGUMENTS.target.device
    if build not in updates.BUILDS[device]:
        raise FatalError(
            message=f"the bootloader {little_kernel!r} is Fire OS {build}'s, and"
            f" firebreak has no {build} for the {device.title}, so nothing was"
            " written. " + again()
        )
    work = CACHE / ("stock-" + build)
    work.mkdir(exist_ok=True, parents=True)
    extract(
        update=updates.download(build=build, device=ARGUMENTS.target.device),
        wanted=("lk",),
        work=work,
    )
    payload = lk_unlock.write(
        image=work / "lk.img", path=CACHE / ("unlock-" + build + ".img")
    )
    PROGRESS.begin(estimate="10 s", label="unlocking the Dot's own bootloader")
    run(
        arguments=["fastboot", "-S", "256M", "flash", UNLOCK_TARGET, str(payload)],
        timeout=300,
    )
    PROGRESS.begin(
        estimate="5 s", label="erasing boot0 so the Dot falls into its bootrom"
    )
    ERASED.write_text(ARGUMENTS.target.device.name)
    failed = erase_by_fastboot()
    if failed:
        raise FatalError(message=failed + " " + again())
    return True
