from __future__ import annotations

import subprocess
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
from firebreak.ui import PROGRESS, FatalError, again, asked_for
from firebreak.unlocks import (
    amonet_biscuit_v1_1_0,
    amonet_biscuit_v1_1_0_bboe,
    amonet_biscuit_v2_0_0,
)

if TYPE_CHECKING:
    import pathlib

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
        message="neither lk_a nor lk_b holds amonet v2.0.0's or v1.1.0's LK, so"
        " this Dot is locked and the recovery it started is one amonet left"
        " behind. Nothing was written. Unlock it first: unplug the USB cable,"
        " hold the action button, plug it back in, and let go when the ring"
        " turns green. " + again()
    )


def amonet_lk(*, node: str) -> bool:
    for download in (amonet_biscuit_v2_0_0.SOURCE, amonet_biscuit_v1_1_0.SOURCE):
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


def amonet_v2_0_0_payload() -> pathlib.Path:
    amonet = unpack(download=amonet_biscuit_v2_0_0.SOURCE)
    return amonet / "brom-payload" / "build" / "payload.bin"


def check_product() -> None:
    product = getvar(name="product")
    if not product:
        raise FatalError(
            message="fastboot reports no product, so nothing was written. " + again()
        )
    if product != BISCUIT.product:
        raise FatalError(
            message=f"fastboot reports {product!r}, not {BISCUIT.product}, so"
            " nothing was"
            " written. firebreak supports only the Echo Dot (2nd Generation)."
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
    amonet = unpack(download=amonet_biscuit_v2_0_0.SOURCE)
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if not little_kernel and getvar(name="pl_build_desc"):
        raise FatalError(
            message="fastboot reported the preloader version but not the"
            " bootloader's; the Dot was not modified. " + again()
        )
    image = "bin/fastbrick.img"
    if little_kernel in {LK.FIREOS6.value, LK.FIREOS6_4315.value}:
        image = "bin/fastbrick-20221007.img"
    PROGRESS.begin(estimate="10 s", label="unlocking with amonet v2.0.0")
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
    work = CACHE / ("stock-" + build)
    work.mkdir(exist_ok=True, parents=True)
    extract(update=updates.download(build=build), wanted=("lk",), work=work)
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
    ERASED.touch()
    failed = erase_by_fastboot()
    if failed:
        raise FatalError(message=failed + " " + again())
    return True
