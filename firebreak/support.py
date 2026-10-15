from __future__ import annotations

import os
import pathlib
import platform
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from firebreak import __version__
from firebreak.bootrom_write_test import bootrom_write_test
from firebreak.cache import CACHE
from firebreak.devices import BY_NAME, FASTBOOT_MODE
from firebreak.host import (
    adb_shell,
    getvar,
    in_fastboot,
    pyserial_wheel,
    run,
    usb_serial,
)
from firebreak.identify import identity_lines
from firebreak.probe import probed
from firebreak.report import (
    LEFT_IN_RECOVERY,
    LISTING_OK,
    PARTITIONS_OK,
    dot_details,
    labelled,
    masked,
    mmc_said,
    node_held,
    node_names,
    node_sizes,
    partition_rows,
    system_a_rows,
    system_record,
    whole,
)
from firebreak.twrp import DISK, TABLE_OK
from firebreak.ui import (
    PROGRESS,
    SESSION,
    SUPPORT,
    WAIT,
    invocation,
    program,
    say,
    show,
    status,
)
from firebreak.unlock import amonet_v2_0_0_payload
from firebreak.updates import BUILDS
from firebreak.write_test import (
    EMMC_TARGET,
    MEBIBYTE,
    TIMED_OUT,
    USB_TEST,
    emmc_leg,
    usb_leg,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def about_host() -> None:
    line("firebreak", " ".join(pathlib.Path(word).name for word in program()[1:]))
    line("firebreak version", __version__)
    line("host", f"{sys.platform} ({os.name}), {platform.platform()}")
    line("python", sys.version.split()[0])
    said = run(arguments=["adb", "version"], timeout=30).stdout.split(sep="\n")
    line("adb", ", ".join(part.strip() for part in said[:2] if part.strip()))


def finish(*, asked: Callable[..., str]) -> None:
    show(text="\nwhat the kernel says about the eMMC")
    for text in mmc_said(asked=asked):
        show(text=text)
    show(text="\n" + LEFT_IN_RECOVERY)


def into_recovery(*, line: Callable[[str, object], None]) -> bool:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    asked = False
    waiting = ""
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        if in_fastboot():
            unlocked = getvar(name="unlock_status")
            for name, value in (
                ("product", getvar(name="product")),
                ("unlock_status", unlocked),
                ("lk_build_desc", getvar(name="lk_build_desc")),
                *(
                    (name, getvar(name=name))
                    for name in (
                        "antirback_pl_version",
                        "antirback_tee_version",
                        "antirback_lk_version",
                    )
                ),
            ):
                line("fastboot " + name, value or "<nothing>")
            if not unlocked:
                say(
                    text="This Dot's fastboot did not say whether it is unlocked,"
                    " so this stops rather than guess. Check the cable, and that no"
                    " other program holds the Dot, then run it again."
                )
                return False
            if unlocked.lower() != "true":
                say(
                    text="This Dot's bootloader is locked, so it holds no recovery"
                    " to collect from and nothing here can give it one. Root it"
                    f" first: run {invocation(options=[])}, and follow what it"
                    " asks."
                )
                return False
            PROGRESS.begin(estimate="40 s", label="restarting the Dot in its recovery")
            run(arguments=["fastboot", "oem", "reboot-recovery"], timeout=60)
        else:
            adb_state = ""
            if usb_serial():
                adb_state = run(arguments=["adb", "get-state"], timeout=30).stdout
            adb_state = adb_state.strip()
            if adb_state == "recovery":
                if not adb_shell(command="getprop ro.twrp.version", timeout=30)[
                    :1
                ].isdigit():
                    say(
                        text="This Dot is in a recovery that is not TWRP, so it"
                        " holds nothing to collect from. It is left as it is."
                    )
                    return False
                if "mtp" in adb_shell(command="getprop sys.usb.config", timeout=30):
                    PROGRESS.end()
                    return True
                if waiting != "twrp":
                    waiting = "twrp"
                    status(text="Waiting for TWRP to finish starting.")
                time.sleep(2)
                continue
            if adb_state == "device":
                if "uid=0" not in adb_shell(command="id; su -c id", timeout=30):
                    say(
                        text="This Dot runs Fire OS without root, so its recovery"
                        " is Amazon's, which holds nothing to collect from. Root it"
                        f" first: run {invocation(options=[])}, and follow what it"
                        " asks."
                    )
                    return False
                PROGRESS.begin(
                    estimate="40 s", label="restarting the Dot in its recovery"
                )
                run(arguments=["adb", "reboot", "recovery"], timeout=60)
            else:
                if not asked:
                    asked = True
                    say(
                        text="The rest of this report comes from the Dot's recovery."
                        " Start the Dot in fastboot mode and this goes on by itself. "
                        + FASTBOOT_MODE
                        + " A Dot already unlocked with amonet v2.0.0 has no"
                        " fastboot: hold the + button instead while you plug it back"
                        " in, which starts its TWRP. A Dot that shows nothing on USB"
                        " is in its bootrom, and only a root run brings it back."
                        " Ctrl-C stops this."
                    )
                if waiting != "fastboot":
                    waiting = "fastboot"
                    status(
                        text="Waiting for the Dot in fastboot mode, with a green ring."
                    )
                time.sleep(2)
                continue
        try:
            run(arguments=["adb", "wait-for-recovery"], timeout=180)
        except subprocess.TimeoutExpired:
            PROGRESS.halt()
            say(
                text="The Dot did not come back in a recovery that answers adb"
                " within 3 minutes. It is most likely in Amazon's recovery, which a"
                f" root run replaces: run {invocation(options=[])}."
            )
            return False
        time.sleep(5)
    PROGRESS.halt()
    return False


def line(label: str, value: object) -> None:
    show(text=labelled(label=label, value=value))


def report() -> None:
    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            said = adb_shell(command=command, timeout=timeout)
        except subprocess.TimeoutExpired:
            return TIMED_OUT
        return masked(text=said) or "<nothing>"

    show(text=SUPPORT + "\n")
    about_host()
    line("state", probed())
    show(text="\n".join(identity_lines()))
    if not into_recovery(line=line):
        show(text="\nThe report stops with what is above.")
        return
    line("state in recovery", probed())
    for text in dot_details(asked=asked):
        show(text=text)
    held = CACHE / f"system-{BUILDS['5.5.5.4'].sha256[:12]}" / "md5"
    want, needs = system_record(text=held.read_text() if held.is_file() else "")
    if needs:
        line("system image", f"{needs} bytes, md5 {want}")
    else:
        line("system image", "not built yet, so its size is unknown")
    partitions = whole(
        marker=PARTITIONS_OK,
        said=asked(command=f"cat /proc/partitions; echo {PARTITIONS_OK}"),
    )
    listing = whole(
        marker=LISTING_OK, said=asked(command=f"ls -l {BY_NAME}/; echo {LISTING_OK}")
    )
    names = None if listing is None else node_names(listing=listing)
    for label, value in system_a_rows(names=names, needs=needs, partitions=partitions):
        line(label, value)
    show(text="\npartition table, with each name's node and any other name for it")
    printed = asked(command=f"sgdisk --print {DISK}; echo {TABLE_OK}", timeout=120)
    for row in partition_rows(names=names, printed=printed):
        show(text=row)
    finish(asked=asked)


def write_test() -> None:
    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            return masked(text=adb_shell(command=command, timeout=timeout))
        except subprocess.TimeoutExpired:
            return TIMED_OUT

    show(text=SUPPORT + "\n")
    about_host()
    if SESSION.short:
        bootrom_write_test(
            line=line, payload=amonet_v2_0_0_payload(), wheel=pyserial_wheel()
        )
        return
    line("state", probed())
    if not into_recovery(line=line):
        show(text="\nThe test needs a recovery, so it stops here.")
        return
    toybox = asked(command="toybox dd --help >/dev/null 2>&1 && echo yes")
    if toybox.split(sep="\n")[-1] == "yes":
        SESSION.dd = "toybox dd"
    line("dd on the Dot", SESSION.dd)
    listing = whole(
        marker=LISTING_OK, said=asked(command=f"ls -l {BY_NAME}/; echo {LISTING_OK}")
    )
    partitions = whole(
        marker=PARTITIONS_OK,
        said=asked(command=f"cat /proc/partitions; echo {PARTITIONS_OK}"),
    )
    try:
        chunk = usb_leg(asked=asked, line=line)
        if listing is None or partitions is None:
            line(
                "over the eMMC",
                "skipped: the Dot's partition lists did not arrive whole",
            )
        else:
            node = node_names(listing=listing).get(EMMC_TARGET, "")
            sizes = node_sizes(partitions=partitions)
            emmc_leg(
                asked=asked,
                blocks=sizes.get(node_held(target=node), 0) // MEBIBYTE,
                chunk=chunk,
                line=line,
                node=node,
            )
    finally:
        asked(command=f"rm -f {USB_TEST}")
    finish(asked=asked)
