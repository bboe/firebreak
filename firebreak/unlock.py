from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING

from firebreak.bootrom_step import bootrom_step
from firebreak.cache import digest, fetch, unpack
from firebreak.devices import (
    BISCUIT,
    FASTBRICKS,
    FIREOS5_CHAINS,
    LITTLE_KERNEL_DESCRIPTION,
    LK_VALUES,
    TARGETS,
)
from firebreak.host import (
    PUSH_TRIES,
    adb_shell,
    getvar,
    in_fastboot,
    last_line,
    pyserial_wheel,
    reconnect,
    run,
)
from firebreak.recovery import MD5_DIGITS
from firebreak.twrp import DISK, partitions
from firebreak.ui import (
    ARGUMENTS,
    PROGRESS,
    SESSION,
    FatalError,
    again,
    asked_for,
    say,
    title,
)

if TYPE_CHECKING:
    import pathlib

    from firebreak.cache import Download
    from firebreak.plugin import Device, Unlock


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
            held = last_line(said=read).split(sep=" ")[0]
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


def amonet_payload() -> pathlib.Path:
    device = current_device() if ARGUMENTS.target else SESSION.device
    amonet = unpack(
        download=FASTBRICKS[device if device in FASTBRICKS else BISCUIT].source
    )
    return amonet / "brom-payload" / "build" / "payload.bin"


def amonet_sources() -> tuple[Download, ...]:
    device = current_device()
    others = (
        target.unlock.source
        for target in TARGETS[device].values()
        if target.unlock is not None
    )
    return tuple(dict.fromkeys((FASTBRICKS[device].source, *others)))


def check_product() -> None:
    product = getvar(name="product")
    if not product:
        raise FatalError(
            message="fastboot reports no product, so nothing was written. " + again()
        )
    device = current_device()
    if product != device.product:
        asked = ARGUMENTS.target.name if ARGUMENTS.target else "this run"
        raise FatalError(
            message=f"fastboot reports {product!r}, not {device.product}, so"
            f" nothing was written. {asked} is for the {device.title}."
        )


def current_device() -> Device:
    if ARGUMENTS.target:
        return ARGUMENTS.target.device
    if SESSION.device is not None:
        return SESSION.device
    raise FatalError(
        message="firebreak cannot tell which Echo this is, so it cannot say what"
        " to do with it. Run it again with --device:"
        f" {', '.join(sorted(each.name for each in TARGETS))}."
    )


def erase_by_fastboot() -> str:
    erased = run(arguments=["fastboot", "erase", "boot0"], timeout=60)
    if erased.returncode != 0:
        SESSION.boot0_erased = False
        return f"fastboot erase boot0 failed:\n{erased.stdout}"
    rebooted = run(arguments=["fastboot", "reboot"], timeout=60)
    if rebooted.returncode != 0:
        return f"fastboot reboot failed:\n{rebooted.stdout}"
    return ""


def fastbrick_payload(
    *, little_kernel: str, unlock: Unlock
) -> tuple[pathlib.Path, str, str]:
    image = unlock.fastbricks.get(little_kernel, "bin/fastbrick.img")
    held = unlock.payloads.get(little_kernel)
    archive = held or unlock.source
    return unpack(download=archive), image, archive.name.removesuffix(".zip")


def newer_than_known(*, little_kernel: str) -> None:
    known = LK_VALUES[current_device()]
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
        " Its bootrom still unlocks it: `firebreak bootrom --short` says where"
        " its test point is."
        if current_device().short_gesture
        else ""
    )
    raise FatalError(
        message=f"the bootloader {little_kernel} is no older than any firebreak"
        f" has a payload for on the {current_device().title}, and a"
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


def stage_amonet_recovery(*, carries_twrp: bool = True) -> bool:
    if not unlocked_fastboot():
        return False
    unlock = FASTBRICKS[current_device()]
    if not carries_twrp or (
        unlock.little_kernel
        and getvar(name="lk_build_desc", strict=True) == unlock.little_kernel
    ):
        PROGRESS.begin(estimate="40 s", label="writing TWRP and waiting for it")
        run(
            arguments=["fastboot", "-S", "256M", "flash", "recovery", "bin/twrp.img"],
            check=True,
            directory=unpack(download=unlock.source),
            timeout=120,
        )
    else:
        PROGRESS.begin(estimate="40 s", label="waiting for TWRP to start")
    if restart_refusals():
        PROGRESS.end(skipped=True)
        say(
            text=f"This {title()}'s fastboot took neither command that starts its"
            " TWRP. Unplug it, and hold the + button while you plug it back in,"
            " which starts TWRP itself. A fastboot older than platform-tools r29"
            " has no reboot-recovery command of its own, so check this host's"
            " `fastboot --version` as well."
        )
        return False
    return True


def stage_downgrade() -> bool:
    chain = FIREOS5_CHAINS[current_device()]
    amonet = unpack(download=chain.unlock.source)
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
    if little_kernel == chain.little_kernel:
        raise FatalError(
            message=f"the {title()} already runs the bootloader this would write. "
            + again()
        )
    if little_kernel == FASTBRICKS[current_device()].little_kernel:
        stage_amonet_recovery()
        return False
    PROGRESS.begin(estimate="5 s", label="erasing boot0 to reach the bootrom")
    bootrom_step(
        amonet=amonet,
        erase=erase_by_fastboot,
        little_kernel=chain.little_kernel,
        payload=amonet_payload(),
        tail=None,
        unlock=chain.unlock,
        wheel=wheel,
    )
    return stage_fireos5_recovery()


def stage_fastbrick() -> None:
    fastbrick = FASTBRICKS[current_device()]
    check_product()
    little_kernel = getvar(name="lk_build_desc", strict=True)
    if not little_kernel and getvar(name="pl_build_desc", strict=True):
        raise FatalError(
            message="fastboot reported the preloader version but not the"
            f" bootloader's; the {title()} was not modified. " + again()
        )
    newer_than_known(little_kernel=little_kernel)
    amonet, image, release = fastbrick_payload(
        little_kernel=little_kernel, unlock=fastbrick
    )
    PROGRESS.begin(estimate="10 s", label=f"unlocking with {release}")
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


def stage_fireos5_recovery() -> bool:
    if not unlocked_fastboot():
        return False
    chain = FIREOS5_CHAINS[current_device()]
    amonet = unpack(download=chain.unlock.source)
    twrp = fetch(download=chain.recovery)
    PROGRESS.begin(
        estimate="30 s",
        label=f"waiting for TWRP {chain.twrp_version}",
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


def unlocked_fastboot() -> bool:
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
            " and continues from amonet's recovery."
        )
        return False
    if unlocked != "true":
        raise FatalError(
            message=f"the {title()}'s fastboot did not say whether it is unlocked. "
            + again()
        )
    return True
