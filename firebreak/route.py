from __future__ import annotations

import contextlib
import dataclasses
import functools
import threading
import time
from typing import TYPE_CHECKING

from firebreak import recovery, updates
from firebreak.bootrom_step import bootrom_step
from firebreak.cache import (
    ERASED,
    MAGISK,
    Download,
    cache_note,
    fetch,
    hold,
    lock_for,
    unpack,
)
from firebreak.devices import BUILDS, FASTBRICKS, biscuit
from firebreak.emos import stage_emos
from firebreak.fireos import (
    BOOT_ROOT,
    TWRP,
    UPDATER,
    hide_updater,
    stage_install_fireos,
    stage_install_fireos6,
    stage_replace_twrp,
    stage_swap_twrp,
    system_image,
)
from firebreak.host import adb_shell, pyserial_wheel, run
from firebreak.identify import check_target, fastboot_driver_missing
from firebreak.plugin import FireOs6
from firebreak.probe import state
from firebreak.states import State
from firebreak.stock import STOCK_STEPS, stage_restore
from firebreak.twrp import reboot
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    PROGRESS,
    SESSION,
    WAIT,
    FatalError,
    again,
    clock,
    passed,
    say,
    show,
    title,
    warn,
)
from firebreak.unlock import (
    amonet_chain,
    amonet_sources,
    amonet_v2_payload,
    stage_amonet_v1_1_0_recovery,
    stage_amonet_v2_recovery,
    stage_downgrade,
    stage_fastbrick,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    Need = Download | Callable[[], object]


AHEAD = {State.STOCK_BOOTED: State.STOCK_FASTBOOT}
DOWNLOADS: list[Need] = []
DRIVER_CHECK = 10
DRIVER_MISSES = 2
FIREOS5_ROOTED = {
    State.ROOTED,
    State.AMONET_V1_1_0_BBOE_BOOTED,
    State.AMONET_V1_1_0_BOOTED,
}
NO_FASTBOOT_DRIVER = (
    "Windows sees an Echo in fastboot mode, but fastboot does not, so its driver"
    " is missing. Install the drivers from"
    " https://github.com/bboe/firebreak#windows in an administrator PowerShell."
    " The run goes on when fastboot sees the Echo."
)
RESTARTS = 5
TWRPS = frozenset({
    State.AMONET_V1_1_0_TWRP,
    State.AMONET_V2_TWRP,
    State.AMONET_V2_TWRP_V1_1_0_TABLE,
    State.AMONET_V1_1_0_BBOE_TWRP,
})


@dataclasses.dataclass(frozen=True)
class Stage:
    run: Callable[[], bool | None]
    steps: int
    then: State | None
    needs: tuple[Need, ...] = ()
    passes: frozenset[State] = frozenset()


def bootrom_needs() -> tuple[Need, ...]:
    return (
        biscuit.V1_1_0_SOURCE,
        pyserial_wheel,
        biscuit.V2_0_1_SOURCE,
    )


def fireos5_stages() -> dict[State, Stage]:
    downgrades = frozenset({
        State.AMONET_V2_TWRP,
        State.AMONET_V2_TWRP_V1_1_0_TABLE,
        State.AMONET_V1_1_0_FASTBOOT,
        State.AMONET_V2_FASTBOOT,
    })
    goal = ARGUMENTS.target.goal
    unlock = ARGUMENTS.target.unlock
    fireos = (ARGUMENTS.target.installs.package, MAGISK, start_prebuild)
    chained = (
        biscuit.V2_0_1_SOURCE,
        biscuit.V1_1_0_SOURCE,
        unlock.source,
        *unlock.files.values(),
        *fireos,
    )
    chain = functools.partial(
        recovery.carry_out,
        after=functools.partial(
            reboot,
            estimate="345 s",
            into="",
            label="waiting for rooted Fire OS 5 to boot",
        ),
        before_preloader=functools.partial(
            stage_install_fireos, reboot=False, slot="_a"
        ),
        guard=amonet_chain,
        unlock=unlock,
    )
    return {
        State.AMONET_V1_1_0_TWRP: Stage(
            needs=(TWRP,),
            run=stage_replace_twrp,
            steps=1,
            then=State.AMONET_V1_1_0_BBOE_TWRP,
        ),
        State.AMONET_V2_TWRP: Stage(
            needs=chained,
            run=chain,
            steps=2,
            then=State.AMONET_V2_TWRP_V1_1_0_TABLE,
        ),
        State.AMONET_V2_TWRP_V1_1_0_TABLE: Stage(
            needs=chained, run=chain, steps=7, then=goal
        ),
        State.AMONET_V1_1_0_BBOE_TWRP: Stage(
            needs=fireos,
            run=stage_install_fireos,
            steps=4,
            then=State.AMONET_V1_1_0_BBOE_BOOTED,
        ),
        State.AMONET_V2_BOOTED: reboot_stages()[State.AMONET_V2_BOOTED],
        State.AMONET_V2_FASTBOOT: Stage(
            needs=(*bootrom_needs(), TWRP),
            passes=downgrades,
            run=stage_downgrade,
            steps=2,
            then=State.AMONET_V1_1_0_BBOE_TWRP,
        ),
    } | {
        rooted: Stage(needs=(TWRP,), run=stage_swap_twrp, steps=1, then=goal)
        for rooted in FIREOS5_ROOTED - {goal}
    }


def fireos6_stages() -> dict[State, Stage]:
    unlock = ARGUMENTS.target.unlock
    installed = (unlock.source, *unlock.files.values())
    install = functools.partial(
        recovery.carry_out,
        after=functools.partial(reboot, label="waiting for TWRP to start"),
        guard=amonet_chain,
        unlock=unlock,
        zero=("misc",),
    )
    return {
        State.AMONET_V1_1_0_TWRP: Stage(
            needs=(*installed, *amonet_sources()),
            run=install,
            steps=4,
            then=State.AMONET_V2_TWRP,
        ),
        State.AMONET_V2_TWRP: Stage(
            needs=(unlock.source, ota_build, BOOT_ROOT),
            run=stage_install_fireos6,
            steps=5,
            then=State.AMONET_V2_BOOTED,
        ),
        State.AMONET_V2_TWRP_V1_1_0_TABLE: Stage(
            needs=installed, run=install, steps=4, then=State.AMONET_V2_TWRP
        ),
        State.AMONET_V1_1_0_BBOE_TWRP: Stage(
            needs=(*installed, *amonet_sources()),
            run=install,
            steps=4,
            then=State.AMONET_V2_TWRP,
        ),
    } | {
        state: stage
        for state, stage in reboot_stages().items()
        if state in FIREOS5_ROOTED
    }


def in_browser(*, need: Need) -> bool:
    return isinstance(need, Download) and need.browser


def keeps_restarting() -> str:
    return (
        f"This {title()} keeps restarting rather than reaching TWRP: a blue"
        " ring, about a second of turning cyan, and little or no white. A USB"
        " port that cannot power TWRP does that, and TWRP is the step where it"
        f" has shown up.\n\nTo tell, plug this {title()} into a USB wall"
        " charger and hold the + button while it powers up. A ring that reaches"
        " white there means TWRP runs and the port is the problem. Use a port"
        " on the computer itself, and unplug whatever else is on it."
    )


def needed(*, start: State, table: dict[State, Stage]) -> list[Need]:
    found: list[Need] = []
    for _ in range(len(table) + 1):
        stage = table.get(start)
        if start == ARGUMENTS.target.goal or stage is None:
            break
        found.extend(stage.needs)
        if stage.then is None:
            break
        start = stage.then
    return list(dict.fromkeys(found))


def ota_build() -> None:
    build = ARGUMENTS.build or ARGUMENTS.target.installs.build
    with hold(lock=lock_for(key=build)):
        updates.download(build=build, builds=BUILDS[ARGUMENTS.target.device])


def prebuild() -> None:
    with contextlib.suppress(Exception):
        system_image(package=ARGUMENTS.target.installs.package)


PREBUILDER = threading.Thread(daemon=True, target=prebuild)


def predownload() -> None:
    with contextlib.suppress(Exception):
        prefetch(needs=DOWNLOADS)


DOWNLOADER = threading.Thread(daemon=True, target=predownload)


def prefetch(*, needs: Iterable[Need]) -> None:
    if DOWNLOADER.is_alive() and threading.current_thread() is threading.main_thread():
        show(text="Finishing the downloads.")
    for need in sorted(needs, key=lambda need: not in_browser(need=need)):
        if not isinstance(need, Download):
            need()
        elif need.directory:
            unpack(download=need)
        else:
            fetch(download=need)


def reboot_stages() -> dict[State, Stage]:
    to_recovery = functools.partial(reboot, label="waiting for recovery")
    to_twrp = functools.partial(reboot, label="waiting for TWRP to start")
    return {
        State.AMONET_V2_BOOTED: Stage(run=to_twrp, steps=1, then=State.AMONET_V2_TWRP),
        State.BOOTED: Stage(run=to_recovery, steps=1, then=None),
        State.ROOTED: Stage(run=to_recovery, steps=1, then=State.AMONET_V1_1_0_TWRP),
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


def restore_stages() -> dict[State, Stage]:
    bootrom = ARGUMENTS.build in biscuit.BOOTROM_BUILDS
    return {
        twrp: Stage(
            needs=(
                (ota_build, biscuit.V2_0_1_SOURCE, pyserial_wheel)
                if bootrom
                else (ota_build,)
            ),
            passes=TWRPS,
            run=stage_restore,
            steps=STOCK_STEPS + 3 if bootrom else STOCK_STEPS,
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
    awaiting = None
    deadline = None
    driver_check = 0.0
    driver_misses = 0
    restarts = 0
    while True:
        current = state()
        installed = (
            target.goal == State.AMONET_V2_BOOTED and State.AMONET_V2_TWRP in done
        )
        restored = target.unlock is None and bool(done & TWRPS)
        ahead = AHEAD.get(current)
        if (
            DOWNLOADER.ident is None
            and not done
            and current not in table
            and ahead in table
            and not (target.unlock is None and current == State.STOCK_BOOTED)
        ):
            check_target(target=target)
            DOWNLOADS[:] = [
                need
                for need in needed(start=ahead, table=table)
                if not in_browser(need=need)
            ]
            DOWNLOADER.start()
        if current not in {State.NONE, State.STARTING, *TWRPS}:
            ERASED.unlink(missing_ok=True)
        SESSION.boot0_marker = ERASED
        if current != State.NONE:
            SESSION.short = False
        if current == State.NONE and (ERASED.exists() or SESSION.short) and not resumed:
            bootrom_device = biscuit.UNLOCK_FROM_BOOTROM.device
            if target.device != bootrom_device:
                why = (
                    "has an erased boot0, which only its bootrom can start it from"
                    if ERASED.exists()
                    else "was asked for with --short, which waits for its bootrom"
                )
                raise FatalError(
                    message=f"this {target.device.title} {why}, and firebreak's"
                    f" bootrom step supports only the {bootrom_device.title}, so"
                    " nothing was done."
                )
            prefetch(
                needs=dict.fromkeys((
                    *bootrom_needs(),
                    *needed(start=State.AMONET_V1_1_0_FASTBOOT, table=table),
                ))
            )
            if not SESSION.short:
                warn(
                    text=(
                        "This run erased boot0"
                        if done
                        else "The last run stopped after it erased boot0"
                    )
                    + f", so the {title()} cannot start until amonet v1.1.0 is written"
                    " through its bootrom. This run does that, then goes on"
                    " from v1.1.0's TWRP. If nothing happens within a minute,"
                    f" unplug the {title()} and plug it back in.",
                )
            resumed = True
            done.difference_update(TWRPS)
            done.add(State.AMONET_V1_1_0_FASTBOOT)
            left = remaining(start=State.AMONET_V1_1_0_BBOE_TWRP, table=table)
            if left is not None:
                PROGRESS.steps = PROGRESS.step + (2 if SESSION.short else 3) + left
            if bootrom_step(
                amonet=unpack(download=biscuit.V1_1_0_SOURCE),
                erase=None,
                payload=amonet_v2_payload(),
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
            restarts = (
                restarts + (current == State.NONE)
                if current in {State.NONE, State.STARTING}
                else 0
            )
            if restarts == RESTARTS and current == State.NONE and awaiting in TWRPS:
                PROGRESS.note(message=keeps_restarting())
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
                show(
                    text=f"The {title()} is starting Fire OS. Waiting for it to finish."
                )
            elif current == State.STOCK_BOOTED and installed:
                deadline = time.monotonic() + MINUTE
            elif current == State.STOCK_BOOTED and target.unlock is not None:
                guided = True
                say(
                    text=f"This {title()} appears to be unmodified. To unlock and"
                    " root it, start it in fastboot mode.\n\n"
                    + target.device.fastboot_mode
                    + f"\n\nAn {title()} already unlocked with amonet v2 has no"
                    " fastboot: hold the + button instead while you plug it back"
                    " in, which starts its TWRP."
                )
            elif current == State.EMOS and current not in done:
                say(
                    text=f"This {title()} runs EchoMuse's emOS. Rebooting it into"
                    " recovery through its serial console."
                )
            elif current == State.NO_SYSTEM and current not in done:
                say(
                    text=f"This {title()}'s /system is damaged, so Fire OS cannot"
                    " start. Rebooting it into recovery."
                )
            elif (
                current == State.AMONET_V2_BOOTED
                and current not in done
                and current != target.goal
            ):
                say(
                    text=f"This {title()} runs rooted Fire OS 6 on amonet v2."
                    " Rebooting it into TWRP."
                )
            elif current == State.NONE and not done and not PROGRESS.open and guided:
                say(
                    text=f"\n\nWaiting for the {title()} in fastboot mode, with a"
                    " green ring."
                )
            elif current == State.NONE and not done and not PROGRESS.open:
                guided = True
                say(
                    text=f"Waiting for the {title()} on USB. Connect it with a USB"
                    " cable. One that runs Amazon's own software needs fastboot"
                    " mode.\n\n"
                    + target.device.fastboot_mode
                    + "\n\nCtrl-C stops the script."
                )
        if current == State.AMONET_V2_BOOTED == target.goal:
            version = adb_shell(command="getprop ro.build.version.name")
            warn(text=f"The {title()} is rooted: {version}, with root adb.")
            cache_note()
            return
        if target.unlock is None and (
            current in {State.STOCK_BOOTED, State.STOCK_FASTBOOT}
            or (
                restored
                and ARGUMENTS.build in biscuit.FIREOS5_BUILDS
                and current not in TWRPS
            )
        ):
            if done:
                PROGRESS.end()
                if SESSION.fastboot:
                    passed(
                        message=f"Stock {ARGUMENTS.build} is written, and the"
                        f" {title()} waits in fastboot."
                    )
                elif ARGUMENTS.build in biscuit.FIREOS5_BUILDS:
                    passed(
                        message=f"Stock {ARGUMENTS.build} is written, and the {title()}"
                        " is rebooting into it."
                    )
                    say(
                        text="Stock Fire OS 5 shows nothing on USB once it starts,"
                        f" so firebreak does not wait for it. Keep the {title()}"
                        " plugged in until the orange ring circles or it speaks"
                        ' "Hello, your device is now ready".'
                    )
                else:
                    passed(message=f"The {title()} runs stock {ARGUMENTS.build}.")
                warn(
                    text=f"If you plan to unlock this {title()} again, do not connect"
                    " it to Wi-Fi. Amazon can update it to a build firebreak"
                    " does not support."
                )
            else:
                say(
                    text=f"This {title()} appears to run stock Fire OS 6, so there is"
                    " nothing to restore. However, if you unlocked it with amonet"
                    " v2, hold its + button while you plug it in. That starts"
                    " its TWRP. Then run this again."
                )
            cache_note()
            return
        if current == target.goal:
            hide_updater()
            version = adb_shell(command="getprop ro.build.version.name")
            selinux = adb_shell(command="getenforce")
            warn(
                text=f"The {title()} is rooted: {version}, SELinux {selinux},"
                f" {UPDATER} hidden."
            )
            cache_note()
            return
        if (
            current in done
            or current in {State.NONE, State.STOCK_BOOTED, State.STARTING}
            or (current == State.BOOTED and target.unlock is not None)
        ):
            waits = {State.NONE} if installed else {State.NONE, State.STOCK_BOOTED}
            if restored:
                waits = set()
            if current not in waits and time.monotonic() > deadline:
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
                    message=f"the {title()} has been {current.value} for"
                    f" {WAIT // 60} minutes. " + again()
                )
            if (
                current == State.NONE
                and driver_misses < DRIVER_MISSES
                and time.monotonic() >= driver_check
            ):
                driver_check = time.monotonic() + DRIVER_CHECK
                driver_misses = driver_misses + 1 if fastboot_driver_missing() else 0
                if driver_misses == DRIVER_MISSES:
                    warn(text=NO_FASTBOOT_DRIVER)
            time.sleep(2)
            continue
        if not done:
            check_target(target=target)
        prefetch(needs=needed(start=current, table=table))
        if not done:
            warn(text=f"Keep the {title()} plugged in until firebreak finishes.")
        done.add(current)
        stage = table.get(current)
        if stage:
            awaiting = stage.then
            left = remaining(start=current, table=table)
            PROGRESS.steps = 0 if left is None else PROGRESS.step + left
            if stage.run() is not False:
                done.update(stage.passes)
        seen = None


def stages() -> dict[State, Stage]:
    table = {
        State.EMOS: Stage(needs=(pyserial_wheel,), run=stage_emos, steps=1, then=None),
        State.NO_SYSTEM: reboot_stages()[State.BOOTED],
        State.AMONET_V1_1_0_FASTBOOT: Stage(
            needs=(biscuit.V1_1_0_SOURCE, TWRP),
            run=stage_amonet_v1_1_0_recovery,
            steps=1,
            then=State.AMONET_V1_1_0_BBOE_TWRP,
        ),
        State.AMONET_V2_FASTBOOT: Stage(
            run=stage_amonet_v2_recovery, steps=1, then=State.AMONET_V2_TWRP
        ),
    } | dict.fromkeys(
        (State.STOCK_FASTBOOT, State.STOCK_FIREOS5_FASTBOOT),
        Stage(
            needs=(FASTBRICKS[ARGUMENTS.target.device].source,),
            run=stage_fastbrick,
            steps=2,
            then=State.AMONET_V2_TWRP,
        ),
    )
    if ARGUMENTS.target.unlock is None:
        return table | restore_stages()
    if isinstance(ARGUMENTS.target.installs, FireOs6):
        return table | fireos6_stages()
    return table | fireos5_stages()


def start_prebuild() -> None:
    with contextlib.suppress(RuntimeError):
        PREBUILDER.start()
