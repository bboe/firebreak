from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

from firebreak.bootrom_step import bootrom_step
from firebreak.cache import ERASED, digest, fetch, unpack
from firebreak.devices import (
    FASTBRICKS,
    LITTLE_KERNEL_DESCRIPTION,
    LK_VALUES,
    TARGETS,
    biscuit,
)
from firebreak.host import (
    PUSH_TRIES,
    adb_shell,
    getvar,
    in_fastboot,
    pyserial_wheel,
    reconnect,
    run,
)
from firebreak.recovery import MD5_DIGITS
from firebreak.twrp import DISK, partitions
from firebreak.ui import (
    ARGUMENTS,
    PROGRESS,
    FatalError,
    again,
    asked_for,
    say,
    title,
)

if TYPE_CHECKING:
    import pathlib

    from firebreak.cache import Download


def amonet_chain() -> None:
    part = partitions()
    for slot in ("lk_a", "lk_b"):
        if slot not in part:
            raise FatalError(
                message=f"the {title()}'s partition table has no {slot}. " + again()
            )
    if any(amonet_lk(node=f"{DISK}p{part[slot][0]}") for slot in ("lk_a", "lk_b")):
        return
    raise FatalError(
        message="neither lk_a nor lk_b holds an amonet LK for this device, so"
        f" this {title()} is locked and the recovery it started is one amonet left"
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
    others = (
        target.unlock.source
        for target in TARGETS[device].values()
        if target.unlock is not None
    )
    return tuple(dict.fromkeys((FASTBRICKS[device].source, *others)))


def amonet_v2_payload() -> pathlib.Path:
    amonet = unpack(download=biscuit.V2_0_1_SOURCE)
    return amonet / "brom-payload" / "build" / "payload.bin"


def check_product() -> None:
    product = getvar(name="product")
    if not product:
        raise FatalError(
            message="fastboot reports no product, so nothing was written. " + again()
        )
    device = ARGUMENTS.target.device
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


def newer_than_known(*, little_kernel: str) -> None:
    known = LK_VALUES[ARGUMENTS.target.device]
    if not little_kernel or little_kernel in known:
        return
    if not LITTLE_KERNEL_DESCRIPTION.fullmatch(string=little_kernel):
        raise FatalError(
            message=f"the {title()} did not report a bootloader version firebreak"
            f" can read; the {title()} was not modified. " + again()
        )
    newest = max((each.split(sep="-")[1] for each in known), default="")
    if little_kernel.split(sep="-")[1] < newest:
        return
    bootrom = (
        " Its bootrom still unlocks it: README.md's --short section says how to"
        " open it."
        if ARGUMENTS.target.device == biscuit.UNLOCK_FROM_BOOTROM.device
        else ""
    )
    raise FatalError(
        message=f"the bootloader {little_kernel} is no older than any firebreak"
        f" has a payload for on the {ARGUMENTS.target.device.title}, and a"
        " fastbrick payload only unlocks the bootloaders it was built for, so"
        f" the {title()} was not modified.{bootrom}"
    )


def one_line(*, said: str) -> str:
    return "; ".join(part.strip() for part in said.split(sep="\n") if part.strip())


def restart_refusals() -> list[tuple[str, str]]:
    refused = []
    for words in (["oem", "reboot-recovery"], ["reboot-recovery"]):
        try:
            asked = run(arguments=["fastboot", *words], timeout=60)
        except subprocess.TimeoutExpired:
            return []
        if asked.returncode == 0 or not in_fastboot():
            return []
        refused.append((
            "fastboot " + " ".join(words),
            one_line(said=asked.stdout) or f"exit {asked.returncode}",
        ))
    return refused


def stage_amonet_v1_1_0_recovery() -> bool:
    unlocked = ""
    for _ in range(PUSH_TRIES):
        unlocked = getvar(name="unlock_status").lower()
        if unlocked in {"true", "false"}:
            break
        time.sleep(1)
    if unlocked == "false":
        PROGRESS.note(
            message=f"The {title()} came back in its own locked fastboot rather than"
            " amonet's, which accepts nothing this needs. This run unlocks it again"
            " and goes on from v2's recovery."
        )
        return False
    if unlocked != "true":
        raise FatalError(
            message=f"the {title()}'s fastboot did not say whether it is unlocked. "
            + again()
        )
    amonet = unpack(download=biscuit.V1_1_0_SOURCE)
    twrp = fetch(download=biscuit.BBOE_RECOVERY)
    PROGRESS.begin(
        estimate="30 s",
        label=f"waiting for TWRP {biscuit.BBOE_TWRP_VERSION}",
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


def stage_amonet_v2_recovery() -> bool:
    say(text=f"This {title()} is in amonet v2's fastboot. Starting its TWRP.")
    if restart_refusals():
        say(
            text=f"This {title()}'s fastboot took neither command that starts its"
            " TWRP. Unplug it, and hold the + button while you plug it back in,"
            " which starts TWRP itself."
        )
        return False
    PROGRESS.begin(estimate="40 s", label="waiting for TWRP to start")
    return True


def stage_downgrade() -> bool:
    amonet = unpack(download=biscuit.V1_1_0_SOURCE)
    wheel = pyserial_wheel()
    if getvar(name="unlock_status").lower() != "true":
        raise FatalError(message="not in amonet's fastboot")
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if not LITTLE_KERNEL_DESCRIPTION.fullmatch(string=little_kernel):
        raise FatalError(
            message=f"the {title()} did not report its bootloader version;"
            " boot0 was not erased. " + again()
        )
    if little_kernel == biscuit.AMONET_V1_1_0_LK:
        raise FatalError(
            message=f"the {title()} already runs amonet v1.1.0's bootloader. " + again()
        )
    PROGRESS.begin(estimate="5 s", label="erasing boot0 to reach the bootrom")
    bootrom_step(
        amonet=amonet,
        erase=erase_by_fastboot,
        payload=amonet_v2_payload(),
        wheel=wheel,
    )
    return stage_amonet_v1_1_0_recovery()


def stage_fastbrick() -> None:
    fastbrick = FASTBRICKS[ARGUMENTS.target.device]
    amonet = unpack(download=fastbrick.source)
    check_product()
    little_kernel = getvar(name="lk_build_desc")
    if not little_kernel and getvar(name="pl_build_desc"):
        raise FatalError(
            message="fastboot reported the preloader version but not the"
            f" bootloader's; the {title()} was not modified. " + again()
        )
    newer_than_known(little_kernel=little_kernel)
    image = fastbrick.fastbricks.get(little_kernel, "bin/fastbrick.img")
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
            raise FatalError(
                message=f"the {title()}'s eMMC is read-only; it was not modified"
            )
        if "Device mismatch" in output:
            raise FatalError(
                message="the payload rejected this device; it was not modified"
            )
        if started:
            PROGRESS.begin(estimate="40 s", label="waiting for TWRP to start")
            return
    raise FatalError(
        message=f"the unlock did not start after 10 attempts, with {image} for"
        f" the bootloader {little_kernel}; the {title()} was not modified"
    )
