"""Change the firmware on an Echo Dot (2nd Generation) over USB: root it, or
return it to stock. It finds where the Dot is, from stock, part way through, or
on another target, and keeps going until the Dot is on the target: it waits
while the Dot reboots, and while you take a step it asks for. Stopped, it picks
up where it left off on the next run. It uses the one Dot on USB; set
ANDROID_SERIAL when several are. It needs Python 3.9 or later, and adb and
fastboot from Android platform-tools.
https://github.com/bboe/firebreak/blob/main/docs/rooting.md says why each
step is there.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import functools
import os
import pathlib
import platform
import shutil
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


from firebreak import __version__, recovery, updates
from firebreak.bootrom_step import bootrom_step
from firebreak.cache import (
    CACHE,
    ERASED,
    MAGISK,
    cache_note,
    fetch,
    hold,
    lock_for,
    move_old_caches,
    unpack,
)
from firebreak.devices import BY_NAME, State
from firebreak.emos import child_emos, stage_emos
from firebreak.fireos import (
    BOOT_ROOT,
    UPDATER,
    hide_updater,
    stage_install_fireos,
    stage_install_fireos6,
    stage_replace_twrp,
    stage_swap_twrp,
    system_image,
)
from firebreak.host import (
    adb_shell,
    check_adb,
    check_user,
    getvar,
    in_fastboot,
    pyserial_wheel,
    run,
    usb_serial,
)
from firebreak.plugin import FireOs6
from firebreak.probe import probed, state
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
from firebreak.stock import STOCK_STEPS, stage_restore
from firebreak.twrp import (
    DISK,
    TABLE_OK,
    reboot,
)
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    PROGRESS,
    SESSION,
    SUPPORT,
    ANSIColor,
    FatalError,
    again,
    clock,
    passed,
    program,
    say,
    show,
    status,
    stop,
    warn,
)
from firebreak.unlock import (
    amonet_chain,
    amonet_v2_0_0_payload,
    stage_amonet_v1_1_0_recovery,
    stage_downgrade,
    stage_fastbrick,
)
from firebreak.unlocks import (
    amonet_biscuit_v1_1_0,
    amonet_biscuit_v1_1_0_bboe,
    amonet_biscuit_v2_0_0,
)
from firebreak.unlocks.targets import FIREOS, TARGETS
from firebreak.write_test import EMMC_TARGET, MEBIBYTE, USB_TEST, emmc_leg, usb_leg

AMONET_BISCUIT_V1_1_0 = amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0.name
AMONET_BISCUIT_V1_1_0_BBOE = amonet_biscuit_v1_1_0_bboe.AMONET_BISCUIT_V1_1_0_BBOE.name
AMONET_BISCUIT_V1_1_0_ZIP = amonet_biscuit_v1_1_0.SOURCE
AMONET_BISCUIT_V2_0_0 = amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0.name
AMONET_BISCUIT_V2_0_0_ZIP = amonet_biscuit_v2_0_0.SOURCE
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green."
)
FIREOS5_ROOTED = {
    State.ROOTED,
    State.AMONET_V1_1_0_BBOE_BOOTED,
    State.AMONET_V1_1_0_BOOTED,
}
TWRP = amonet_biscuit_v1_1_0_bboe.RECOVERY
TWRPS = frozenset({
    State.AMONET_V1_1_0_TWRP,
    State.AMONET_V2_0_0_TWRP,
    State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    State.AMONET_V1_1_0_BBOE_TWRP,
})
TWRP_VERSION = amonet_biscuit_v1_1_0_bboe.TWRP_VERSION
WAIT = 600


@dataclasses.dataclass(frozen=True)
class Stage:
    run: Callable[[], bool | None]
    steps: int
    then: State | None
    passes: frozenset[State] = frozenset()


def check_for_update() -> None:
    with contextlib.suppress(Exception):
        import update_checker  # ruff: ignore[import-outside-top-level]

        update_checker.update_check(
            package_name="firebreak", package_version=__version__
        )


def child_main(*, arguments: list[str], name: str) -> int:
    if sys.path[0] == str(pathlib.Path.cwd()):
        del sys.path[0]
    return {"emos": child_emos}[name](action=arguments[0], want=arguments[1])


def cli() -> None:
    installs = TARGETS[AMONET_BISCUIT_V2_0_0].installs
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""targets:
  {AMONET_BISCUIT_V1_1_0_BBOE}, the default
      rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP {TWRP_VERSION}.
  {AMONET_BISCUIT_V1_1_0}
      the same, with amonet v1.1.0's own TWRP 3.2.3.
  {AMONET_BISCUIT_V2_0_0}
      amonet v2.0.0's own procedure: Fire OS 6 {installs.build}
      with boot-root.zip's root adb.
  stock BUILD
      Amazon's Fire OS 6 BUILD, which erases the whole Dot.
Run again with another target to move the Dot to it.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog="firebreak",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print each adb and fastboot command, its exit status and the"
        " time, and each state the Dot reaches",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print what the Dot and this computer are, and the Dot's partition"
        " table, for a support request; it starts the Dot's recovery to read them"
        " and writes no partition",
    )
    parser.add_argument(
        "--write-test",
        action="store_true",
        help=f"write a known pattern over the Dot's {EMMC_TARGET} partition and"
        " read it back, which tells a failing eMMC from a failing USB cable"
        " because nothing crosses USB; it leaves a fresh empty filesystem there,"
        " or says it could not",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="for a Dot that shows no light and needs its test point shorted:"
        " wait for its bootrom, say when the short may come off, then go on",
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="do not ask PyPI whether a newer firebreak exists",
    )
    parser.add_argument(
        "target",
        choices=tuple(TARGETS),
        default=AMONET_BISCUIT_V1_1_0_BBOE,
        help="the target, one of those listed below",
        metavar="TARGET",
        nargs="?",
    )
    parser.add_argument(
        "build",
        choices=sorted(updates.BUILDS),
        help="with stock, and only with stock: the build to install, one of "
        + ", ".join(sorted(updates.BUILDS)),
        metavar="BUILD",
        nargs="?",
    )
    options = parser.parse_intermixed_args()
    target = TARGETS[options.target]
    if (target.installs == FireOs6(build=None)) != (options.build is not None):
        parser.error(
            message="stock takes a BUILD, and no other target does: "
            + ", ".join(sorted(updates.BUILDS))
        )
    ARGUMENTS.build = options.build or ""
    ARGUMENTS.target = target
    ARGUMENTS.verbose = options.verbose
    for tool in ("adb", "fastboot"):
        if not shutil.which(cmd=tool):
            raise FatalError(
                message=tool + " not found: install Android platform-tools"
            )
    check_user()
    if not options.no_update_check:
        check_for_update()
    check_adb()
    move_old_caches()
    SESSION.short = options.short
    if options.report:
        report()
        return
    if options.write_test:
        write_test()
        return
    root()


def fireos5_stages() -> dict[State, Stage]:
    downgrades = frozenset({
        State.AMONET_V2_0_0_TWRP,
        State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
        State.AMONET_V1_1_0_FASTBOOT,
        State.AMONET_V2_0_0_FASTBOOT,
    })
    goal = ARGUMENTS.target.goal
    chain = functools.partial(
        recovery.carry_out,
        after=functools.partial(
            reboot,
            estimate="4 min",
            into="",
            label="waiting for rooted Fire OS 5 to boot",
        ),
        before_preloader=functools.partial(
            stage_install_fireos, reboot=False, slot="_a"
        ),
        guard=amonet_chain,
        unlock=ARGUMENTS.target.unlock,
    )
    return {
        State.AMONET_V1_1_0_TWRP: Stage(
            run=stage_replace_twrp, steps=1, then=State.AMONET_V1_1_0_BBOE_TWRP
        ),
        State.AMONET_V2_0_0_TWRP: Stage(
            run=chain,
            steps=3,
            then=State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
        ),
        State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(run=chain, steps=17, then=goal),
        State.AMONET_V1_1_0_BBOE_TWRP: Stage(
            run=stage_install_fireos, steps=5, then=State.AMONET_V1_1_0_BBOE_BOOTED
        ),
        State.AMONET_V2_0_0_BOOTED: reboot_stages()[State.AMONET_V2_0_0_BOOTED],
        State.AMONET_V2_0_0_FASTBOOT: Stage(
            passes=downgrades,
            run=stage_downgrade,
            steps=2,
            then=State.AMONET_V1_1_0_BBOE_TWRP,
        ),
    } | {
        rooted: Stage(run=stage_swap_twrp, steps=1, then=goal)
        for rooted in FIREOS5_ROOTED - {goal}
    }


def fireos6_stages() -> dict[State, Stage]:
    install = functools.partial(
        recovery.carry_out,
        after=functools.partial(reboot, label="waiting for v2.0.0 recovery to start"),
        guard=amonet_chain,
        unlock=amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0,
        zero=("misc",),
    )
    return {
        State.AMONET_V1_1_0_TWRP: Stage(
            run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
        ),
        State.AMONET_V2_0_0_TWRP: Stage(
            run=stage_install_fireos6, steps=5, then=State.AMONET_V2_0_0_BOOTED
        ),
        State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(
            run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
        ),
        State.AMONET_V1_1_0_BBOE_TWRP: Stage(
            run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
        ),
    } | {
        state: stage
        for state, stage in reboot_stages().items()
        if state in FIREOS5_ROOTED
    }


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
                    " first: run firebreak again without --report, and follow"
                    " what it asks."
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
                        " first: run firebreak again without --report, and follow"
                        " what it asks."
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
                " root run replaces: run firebreak again without --report."
            )
            return False
        time.sleep(5)
    PROGRESS.halt()
    return False


def main() -> None:
    if sys.argv[1:2] == ["_child"]:
        sys.exit(child_main(arguments=sys.argv[3:], name=sys.argv[2]))
    try:
        cli()
    except FatalError as error:
        stop(error=error)
    except KeyboardInterrupt:
        stop(error=FatalError(message="stopped", prefix=""))
    except subprocess.TimeoutExpired as error:
        stop(
            error=FatalError(
                message=f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
        )


def prebuild() -> None:
    with contextlib.suppress(Exception):
        system_image(package=ARGUMENTS.target.installs.package)


def predownload() -> None:
    with contextlib.suppress(Exception):
        prefetch()


DOWNLOADER = threading.Thread(daemon=True, target=predownload)


def prefetch() -> None:
    if DOWNLOADER.is_alive() and threading.current_thread() is threading.main_thread():
        show(text="Finishing the downloads.")
    unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    installs = ARGUMENTS.target.installs
    if isinstance(installs, FireOs6):
        build = ARGUMENTS.build or installs.build
        with hold(lock=lock_for(key=build)):
            updates.download(build=build)
        return
    unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    pyserial_wheel()
    fetch(download=installs.package)
    fetch(download=MAGISK)
    fetch(download=TWRP)
    threading.Thread(daemon=True, target=prebuild).start()


def reboot_stages() -> dict[State, Stage]:
    to_twrp = functools.partial(reboot, label="waiting for recovery")
    return {
        State.AMONET_V2_0_0_BOOTED: Stage(
            run=functools.partial(reboot, label="waiting for v2.0.0 recovery to start"),
            steps=1,
            then=State.AMONET_V2_0_0_TWRP,
        ),
        State.BOOTED: Stage(run=to_twrp, steps=1, then=None),
        State.ROOTED: Stage(run=to_twrp, steps=1, then=State.AMONET_V1_1_0_TWRP),
        State.AMONET_V1_1_0_BBOE_BOOTED: Stage(
            run=to_twrp, steps=1, then=State.AMONET_V1_1_0_BBOE_TWRP
        ),
        State.AMONET_V1_1_0_BOOTED: Stage(
            run=to_twrp, steps=1, then=State.AMONET_V1_1_0_TWRP
        ),
    }


def remaining(*, start: State, table: dict[State, Stage]) -> int | None:
    total = 0
    for _ in range(len(table) + 1):
        if start == ARGUMENTS.target.goal:
            return total
        stage = table.get(start)
        if stage is None or stage.then is None:
            return None
        total += stage.steps
        start = stage.then
    return None


def report() -> None:
    def line(label: str, value: object) -> None:
        show(text=labelled(label=label, value=value))

    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            said = adb_shell(command=command, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "<timed out>"
        return masked(text=said) or "<nothing>"

    show(text=SUPPORT + "\n")
    line("firebreak", " ".join(pathlib.Path(word).name for word in program()[1:]))
    line("firebreak version", __version__)
    line("host", f"{sys.platform} ({os.name}), {platform.platform()}")
    line("python", sys.version.split()[0])
    said = run(arguments=["adb", "version"], timeout=30).stdout.split(sep="\n")
    line("adb", ", ".join(part.strip() for part in said[:2] if part.strip()))
    line("state", probed())
    if not into_recovery(line=line):
        show(text="\nThe report stops with what is above.")
        return
    line("state in recovery", probed())
    for text in dot_details(asked=asked):
        show(text=text)
    held = CACHE / f"system-{FIREOS.sha256[:12]}" / "md5"
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
    show(text="\nwhat the kernel says about the eMMC")
    for text in mmc_said(asked=asked):
        show(text=text)
    show(text="\n" + LEFT_IN_RECOVERY)


def restore_stages() -> dict[State, Stage]:
    return {
        twrp: Stage(
            passes=TWRPS,
            run=stage_restore,
            steps=STOCK_STEPS,
            then=State.STOCK_BOOTED,
        )
        for twrp in TWRPS
    } | reboot_stages()


def root() -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    usage = run(arguments=["fastboot", "--help"], timeout=30).stdout
    if not any(line.split()[:1] == ["-S"] for line in usage.splitlines()):
        raise FatalError(
            message="this fastboot has no -S option: install a newer"
            " Android platform-tools"
        )
    done: set[State] = set()
    table = stages()
    target = ARGUMENTS.target
    guided = False
    resumed = False
    seen = None
    shown = None
    deadline = None
    while True:
        current = state()
        installed = (
            target.goal == State.AMONET_V2_0_0_BOOTED
            and State.AMONET_V2_0_0_TWRP in done
        )
        restored = target.unlock is None and bool(done & TWRPS)
        gesture = current == State.AMONET_V2_0_0_FASTBOOT and current not in table
        if (
            DOWNLOADER.ident is None
            and current not in {State.BOOTED, State.STARTING, *FIREOS5_ROOTED}
            and not (
                target.unlock is None
                and current in {State.STOCK_BOOTED, State.STOCK_FASTBOOT}
            )
        ):
            DOWNLOADER.start()
        if current not in {State.NONE, State.STARTING, *TWRPS}:
            ERASED.unlink(missing_ok=True)
        SESSION.boot0_marker = ERASED
        if current != State.NONE:
            SESSION.short = False
        if current == State.NONE and (ERASED.exists() or SESSION.short) and not resumed:
            if target.goal == State.AMONET_V2_0_0_BOOTED:
                fetch(download=BOOT_ROOT)
            prefetch()
            resumed = True
            done.difference_update(TWRPS)
            done.add(State.AMONET_V1_1_0_FASTBOOT)
            if not SESSION.short:
                say(
                    code=ANSIColor.YELLOW,
                    text="The last run stopped after it erased boot0, so the Dot"
                    " cannot start. This run writes amonet v1.1.0 through the"
                    " bootrom, then goes on from v1.1.0's TWRP. If nothing"
                    " happens within a minute, unplug the Dot and plug it back"
                    " in.",
                )
            left = remaining(start=State.AMONET_V1_1_0_BBOE_TWRP, table=table)
            if left is not None:
                PROGRESS.steps = PROGRESS.step + (2 if SESSION.short else 3) + left
            if bootrom_step(
                amonet=unpack(download=AMONET_BISCUIT_V1_1_0_ZIP),
                erase=None,
                payload=amonet_v2_0_0_payload(),
                wheel=pyserial_wheel(),
            ):
                stage_amonet_v1_1_0_recovery()
            else:
                done.discard(State.AMONET_V1_1_0_FASTBOOT)
                resumed = False
            seen = None
            continue
        if current != seen:
            seen = current
            deadline = time.monotonic() + WAIT
            if ARGUMENTS.verbose and current != shown:
                shown = current
                show(text=f"{clock()} state: {current.value}")
            if (
                current not in done
                and current not in {State.NONE, State.STARTING, State.BOOTED}
                and not (current == State.STOCK_BOOTED and installed)
            ):
                PROGRESS.end()
            if (
                current == State.BOOTED
                and not PROGRESS.open
                and target.unlock is not None
            ):
                show(text="The Dot is starting Fire OS. Waiting for it to finish.")
            elif current == State.STOCK_BOOTED and installed:
                deadline = time.monotonic() + MINUTE
            elif current == State.STOCK_BOOTED and target.unlock is not None:
                guided = True
                say(
                    text="This Dot appears to be unmodified. To unlock and root it,"
                    " start it in fastboot mode. "
                    + FASTBOOT_MODE
                    + " A Dot already unlocked with amonet v2.0.0 has no fastboot:"
                    " hold the + button instead while you plug it back in, which"
                    " starts its TWRP."
                )
            elif current == State.EMOS and current not in done:
                say(
                    text="This Dot runs EchoMuse's emOS. Rebooting it into recovery"
                    " through its serial console."
                )
            elif gesture:
                say(
                    text="This Dot is in amonet v2.0.0's fastboot. Unplug it, and"
                    " hold the + button while you plug it back in: that starts"
                    " v2.0.0's TWRP."
                )
            elif (
                current == State.AMONET_V2_0_0_BOOTED
                and current not in done
                and current != target.goal
            ):
                say(
                    text="This Dot runs rooted Fire OS 6 on amonet v2.0.0."
                    " Rebooting it into recovery."
                )
            elif current == State.NONE and not done and not PROGRESS.open and guided:
                show(text="Waiting for the Dot in fastboot mode, with a green ring.")
            elif current == State.NONE and not done and not PROGRESS.open:
                guided = True
                say(
                    text="Waiting for a Dot on USB. Connect it with a USB cable."
                    " A Dot that runs Amazon's own software needs fastboot mode. "
                    + FASTBOOT_MODE
                    + " Ctrl-C stops the script."
                )
        if current == State.AMONET_V2_0_0_BOOTED == target.goal:
            version = adb_shell(command="getprop ro.build.version.name")
            warn(text=f"The Dot is rooted: {version}, with root adb.")
            cache_note()
            return
        if target.unlock is None and current in {
            State.STOCK_BOOTED,
            State.STOCK_FASTBOOT,
        }:
            if done:
                passed(message=f"The Dot runs stock {ARGUMENTS.build}.")
                warn(
                    text="If you will root it again, do not set it up in the Alexa app"
                    " first: on Wi-Fi it can take an update to a build"
                    " firebreak does not support."
                )
            else:
                say(
                    text="This Dot appears to run stock Fire OS 6, so there is"
                    " nothing to restore. However, if you unlocked it with amonet"
                    " v2.0.0, hold its + button while you plug it in. That starts"
                    " its TWRP. Then run this again."
                )
            cache_note()
            return
        if current == target.goal:
            hide_updater()
            version = adb_shell(command="getprop ro.build.version.name")
            selinux = adb_shell(command="getenforce")
            warn(
                text=f"The Dot is rooted: {version}, SELinux {selinux},"
                f" {UPDATER} hidden."
            )
            cache_note()
            return
        if (
            gesture
            or current in done
            or current in {State.NONE, State.STOCK_BOOTED, State.STARTING}
            or (current == State.BOOTED and target.unlock is not None)
        ):
            waits = {State.NONE} if installed else {State.NONE, State.STOCK_BOOTED}
            if restored:
                waits = set()
            if not gesture and current not in waits and time.monotonic() > deadline:
                if restored:
                    raise FatalError(
                        message=f"stock {ARGUMENTS.build} has not started"
                        f" {WAIT // 60} minutes after the restore"
                    )
                if current == State.STOCK_BOOTED:
                    raise FatalError(
                        message="Fire OS 6 started without root adb, so"
                        " boot-root.zip did not take. " + again()
                    )
                if current == State.BOOTED:
                    raise FatalError(
                        message="Fire OS has not finished booting with root."
                        " Reboot to recovery. " + again()
                    )
                raise FatalError(
                    message=f"the Dot has been {current.value} for"
                    f" {WAIT // 60} minutes. " + again()
                )
            time.sleep(2)
            continue
        if not done:
            if target.goal == State.AMONET_V2_0_0_BOOTED:
                fetch(download=BOOT_ROOT)
            if isinstance(target.installs, FireOs6) or current not in FIREOS5_ROOTED:
                prefetch()
            warn(text="Keep the Dot plugged in until firebreak finishes.")
        done.add(current)
        stage = table.get(current)
        if stage:
            left = remaining(start=current, table=table)
            PROGRESS.steps = 0 if left is None else PROGRESS.step + left
            if stage.run() is not False:
                done.update(stage.passes)
        seen = None


def stages() -> dict[State, Stage]:
    table = {
        State.EMOS: Stage(run=stage_emos, steps=1, then=None),
        State.STOCK_FIREOS5_FASTBOOT: Stage(
            run=stage_fastbrick, steps=2, then=State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE
        ),
        State.STOCK_FASTBOOT: Stage(
            run=stage_fastbrick, steps=2, then=State.AMONET_V2_0_0_TWRP
        ),
        State.AMONET_V1_1_0_FASTBOOT: Stage(
            run=stage_amonet_v1_1_0_recovery,
            steps=1,
            then=State.AMONET_V1_1_0_BBOE_TWRP,
        ),
    }
    if ARGUMENTS.target.unlock is None:
        return table | restore_stages()
    if isinstance(ARGUMENTS.target.installs, FireOs6):
        return table | fireos6_stages()
    return table | fireos5_stages()


def write_test() -> None:
    def line(label: str, value: object) -> None:
        show(text=labelled(label=label, value=value))

    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            return masked(text=adb_shell(command=command, timeout=timeout))
        except subprocess.TimeoutExpired:
            return "<timed out>"

    show(text=SUPPORT + "\n")
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
    show(text="\nwhat the kernel says about the eMMC")
    for text in mmc_said(asked=asked):
        show(text=text)
    show(text="\n" + LEFT_IN_RECOVERY)


if __name__ == "__main__":
    main()
