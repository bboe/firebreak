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
    MAGISK,
    Download,
    cache_note,
    fetch,
    hold,
    lock_for,
    unpack,
)
from firebreak.devices import (
    ADB_OFF_BUILDS,
    BOOTROM_UNLOCKS,
    BUILDS,
    FASTBRICKS,
    FIREOS5_BUILDS,
    FIREOS5_CHAINS,
    KAMAKIRI_UNLOCKS,
    biscuit,
)
from firebreak.emos import stage_emos
from firebreak.fireos import (
    BOOT_ROOT,
    TWRP,
    UPDATER,
    adb_key,
    build_number,
    from_fireos5_twrp,
    hide_updater,
    install_steps,
    leave_fireos5,
    outdated,
    stage_install_fireos,
    stage_install_fireos6,
    stage_install_kamakiri,
    stage_replace_twrp,
    stage_swap_twrp,
    system_image,
)
from firebreak.host import adb_shell, run
from firebreak.identify import NO_FASTBOOT_DRIVER, DriverWatch, check_target
from firebreak.kamakiri_step import authorized, kamakiri_step
from firebreak.mediatek.libusb import ELEVATES
from firebreak.plugin import FireOs5, FireOs6
from firebreak.probe import state
from firebreak.states import State, shown
from firebreak.stock import ends_in_fastboot, stage_restore, stock_steps
from firebreak.twrp import reboot, restart_into_twrp
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    MOST_RELIABLE,
    PROGRESS,
    SESSION,
    WAIT,
    FatalError,
    again,
    amonet_has_no_fastboot,
    clock,
    filled,
    invocation,
    passed,
    say,
    show,
    this_command,
    title,
    warn,
)
from firebreak.unlock import (
    amonet_chain,
    amonet_payload,
    amonet_sources,
    stage_amonet_recovery,
    stage_downgrade,
    stage_fastbrick,
    stage_fireos5_recovery,
    stage_kamakiri_recovery,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from firebreak.plugin import Device, Target, Unlock

    Need = Download | Callable[[], object]


AHEAD = {State.STOCK_BOOTED: State.STOCK_FASTBOOT}
BOOTROMS = frozenset({State.BOOTROM, State.NONE})
DOWNLOADS: list[Need] = []
FIREOS5_ROOTED = {
    State.ROOTED,
    State.AMONET_FIREOS5_BBOE_BOOTED,
}
INSTALLED_FROM = {
    State.AMONET_FIREOS5_BBOE_BOOTED: frozenset({
        State.AMONET_FIREOS5_BBOE_TWRP,
        State.AMONET_TWRP_BOOT_MOVED,
    }),
    State.UNLOCKED_BOOTED: frozenset({State.UNLOCKED_TWRP}),
}
KAMAKIRI_REBOOTS = frozenset({State.UNLOCKED_BOOTED, State.BOOTED})
POWER_CYCLE = 60
RESTARTS = 5
STOCK_QUIET = 5 * MINUTE
TWRPS = frozenset({
    State.AMONET_FIREOS5_TWRP,
    State.UNLOCKED_TWRP,
    State.AMONET_TWRP_BOOT_MOVED,
    State.AMONET_FIREOS5_BBOE_TWRP,
})


@dataclasses.dataclass(frozen=True)
class Chain:
    after: Callable[[], bool]
    little_kernel: str
    state: State
    then: State
    unlock: Unlock


@dataclasses.dataclass(frozen=True)
class Stage:
    run: Callable[[], bool | None]
    steps: int | None
    then: State | None
    needs: tuple[Need, ...] = ()
    passes: frozenset[State] = frozenset()


def bootrom_chain() -> Chain:
    chain = FIREOS5_CHAINS.get(ARGUMENTS.target.device)
    if chain is not None and isinstance(ARGUMENTS.target.installs, FireOs5):
        return Chain(
            after=stage_fireos5_recovery,
            little_kernel=chain.little_kernel,
            state=State.AMONET_FIREOS5_FASTBOOT,
            then=State.AMONET_FIREOS5_BBOE_TWRP,
            unlock=chain.unlock,
        )
    return Chain(
        after=functools.partial(stage_amonet_recovery, carries_twrp=False),
        little_kernel="",
        state=State.UNLOCKED_FASTBOOT,
        then=State.UNLOCKED_TWRP,
        unlock=BOOTROM_UNLOCKS[ARGUMENTS.target.device],
    )


def bootrom_needs(*, unlock: Unlock) -> tuple[Need, ...]:
    return (unlock.source, FASTBRICKS[ARGUMENTS.target.device].source)


def credit_note(*, target: Target) -> None:
    unlock = target.unlock
    if unlock is None:
        return
    blocks = []
    if unlock.author:
        blocks.append(
            filled(
                text=f"{unlock.family}, the unlock this run used, is the work of"
                f" {unlock.author.name}: {unlock.author.home}"
            )
        )
        if unlock.author.support:
            blocks.append(
                filled(
                    text="If this tool helped bring new life to an old device,"
                    f" consider supporting {unlock.author.short_name}'s continued"
                    " unlocking work:"
                )
                + "".join(f"\n  - {link}" for link in unlock.author.support)
            )
    if target.device.thread:
        blocks.append(
            filled(text=f"Unlock thread for the {target.device.title}:")
            + f"\n{target.device.thread}"
        )
    if blocks:
        show(text="\n\n".join(blocks) + "\n")


def fireos5_stages() -> dict[State, Stage]:
    downgrades = frozenset({
        State.UNLOCKED_TWRP,
        State.AMONET_TWRP_BOOT_MOVED,
        State.AMONET_FIREOS5_FASTBOOT,
        State.UNLOCKED_FASTBOOT,
    })
    goal = ARGUMENTS.target.goal
    unlock = ARGUMENTS.target.unlock
    fireos = (ARGUMENTS.target.installs.package, MAGISK, start_prebuild)
    chained = (
        FASTBRICKS[ARGUMENTS.target.device].source,
        FIREOS5_CHAINS[ARGUMENTS.target.device].unlock.source,
        unlock.source,
        *unlock.files.values(),
        *fireos,
    )
    chain = functools.partial(
        recovery.carry_out,
        after=functools.partial(
            reboot,
            estimate=345,
            into="",
            label="waiting for rooted Fire OS 5",
        ),
        before_preloader=functools.partial(
            stage_install_fireos, reboot=False, slot="_a"
        ),
        guard=amonet_chain,
        unlock=unlock,
    )
    return {
        State.AMONET_FIREOS5_TWRP: Stage(
            needs=(TWRP,),
            run=stage_replace_twrp,
            steps=1,
            then=State.AMONET_FIREOS5_BBOE_TWRP,
        ),
        State.UNLOCKED_TWRP: Stage(
            needs=chained,
            run=chain,
            steps=2,
            then=State.AMONET_TWRP_BOOT_MOVED,
        ),
        State.AMONET_TWRP_BOOT_MOVED: Stage(
            needs=chained, run=chain, steps=7, then=goal
        ),
        State.AMONET_FIREOS5_BBOE_TWRP: Stage(
            needs=fireos,
            run=stage_install_fireos,
            steps=4,
            then=State.AMONET_FIREOS5_BBOE_BOOTED,
        ),
        State.UNLOCKED_BOOTED: reboot_stages()[State.UNLOCKED_BOOTED],
        State.UNLOCKED_FASTBOOT: Stage(
            needs=(
                *bootrom_needs(unlock=FIREOS5_CHAINS[ARGUMENTS.target.device].unlock),
                TWRP,
            ),
            passes=downgrades,
            run=stage_downgrade,
            steps=2,
            then=State.AMONET_FIREOS5_BBOE_TWRP,
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
        after=functools.partial(reboot, label="restarting into TWRP"),
        guard=amonet_chain,
        unlock=unlock,
        zero=("misc",),
    )
    return {
        State.AMONET_FIREOS5_TWRP: Stage(
            needs=(*installed, *amonet_sources()),
            run=functools.partial(from_fireos5_twrp, install=install),
            steps=4,
            then=State.UNLOCKED_TWRP,
        ),
        State.UNLOCKED_TWRP: Stage(
            needs=(unlock.source, ota_build, BOOT_ROOT),
            run=stage_install_fireos6,
            steps=install_steps() if ARGUMENTS.factory_reset else None,
            then=State.UNLOCKED_BOOTED,
        ),
        State.AMONET_TWRP_BOOT_MOVED: Stage(
            needs=installed, run=install, steps=4, then=State.UNLOCKED_TWRP
        ),
        State.AMONET_FIREOS5_BBOE_TWRP: Stage(
            needs=(*installed, *amonet_sources()),
            run=functools.partial(from_fireos5_twrp, install=install),
            steps=4,
            then=State.UNLOCKED_TWRP,
        ),
    } | {
        state: dataclasses.replace(
            stage, run=functools.partial(leave_fireos5, reboot=stage.run)
        )
        if state in FIREOS5_ROOTED
        else stage
        for state, stage in reboot_stages().items()
        if state in FIREOS5_ROOTED or state == State.UNLOCKED_BOOTED
    }


def in_browser(*, need: Need) -> bool:
    return isinstance(need, Download) and need.browser


def kamakiri_stages() -> dict[State, Stage]:
    unlock = KAMAKIRI_UNLOCKS[ARGUMENTS.target.device]
    table = {
        State.BOOTROM: Stage(
            needs=(unlock.source,),
            run=stage_kamakiri,
            steps=None,
            then=State.UNLOCKED_FASTBOOT,
        ),
        State.UNLOCKED_FASTBOOT: Stage(
            needs=(unlock.source,),
            run=stage_kamakiri_recovery,
            steps=1,
            then=State.UNLOCKED_TWRP,
        ),
    }
    if ARGUMENTS.target.unlock is None:
        return table | restore_stages()
    return (
        table
        | {
            State.UNLOCKED_TWRP: Stage(
                needs=(unlock.source, ota_build, BOOT_ROOT),
                run=stage_install_kamakiri,
                steps=install_steps() if ARGUMENTS.factory_reset else None,
                then=State.UNLOCKED_BOOTED,
            )
        }
        | {
            state: stage
            for state, stage in reboot_stages().items()
            if state in KAMAKIRI_REBOOTS
        }
    )


def keeps_restarting() -> str:
    return (
        f"This {title()} keeps restarting rather than reaching TWRP: a blue"
        " ring, about a second of turning cyan, and little or no white. A USB"
        " port that cannot power TWRP does that, and TWRP is the step where it"
        f" has shown up.\n\nTo tell, plug this {title()} into a USB wall"
        " charger and hold the + button while it powers up. A ring that reaches"
        " white there means TWRP runs and the port is the problem. To retry,"
        f" move this {title()} to another USB port: this run waits for it."
        f" {MOST_RELIABLE}"
    )


def locked() -> str:
    if adb_shell(command="getprop ro.adb.secure") == "1":
        return ", locked to this computer's adb key"
    return ""


def needed(*, start: State, table: dict[State, Stage]) -> list[Need]:
    passing, _ = walked(start=start, table=table)
    return list(dict.fromkeys(need for stage in passing for need in stage.needs))


def nothing_to_restore(*, device: Device) -> str:
    lead = (
        f"This {title()} appears to be on stock Fire OS 6, so there is nothing to"
        " restore."
    )
    if device in KAMAKIRI_UNLOCKS:
        return (
            f"{lead} To unlock it, or to unlock it again after an unlock whose root"
            f" is gone, run {invocation(options=['unlock'])}."
        )
    return (
        f"{lead} However, if you unlocked it with amonet v2, hold its + button"
        " while you plug it in. That starts its TWRP. Then run"
        f" {this_command()} again."
    )


def ota_build() -> None:
    build = ARGUMENTS.build or ARGUMENTS.target.installs.build
    with hold(lock=lock_for(key=build)):
        updates.download(build=build, builds=BUILDS[ARGUMENTS.target.device])


def password_first(*, device: Device) -> None:
    if device not in KAMAKIRI_UNLOCKS or not ELEVATES:
        return
    say(
        text=f"Unlocking this {title()} needs one privileged USB call, the one"
        " that starts its unlock running in its bootrom, so sudo asks for your"
        " password here rather than while the button is held. Nothing is"
        " written yet, and nothing else in the run asks again."
    )
    authorized(explained=True)


def power_cycle() -> str:
    return (
        f"This {title()} has shown nothing on USB since boot-root ran. Unplug"
        " its power cable, then plug it back in. The run continues by itself once"
        " adb comes back."
    )


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
    to_recovery = functools.partial(reboot, label="restarting into recovery")
    to_twrp = functools.partial(reboot, label="restarting into TWRP")
    return {
        State.UNLOCKED_BOOTED: Stage(
            run=functools.partial(restart_into_twrp, device=ARGUMENTS.target.device),
            steps=2 if ARGUMENTS.target.device.recovery_command else 1,
            then=State.UNLOCKED_TWRP,
        ),
        State.BOOTED: Stage(run=to_recovery, steps=1, then=None),
        State.ROOTED: Stage(run=to_recovery, steps=1, then=State.AMONET_FIREOS5_TWRP),
        State.AMONET_FIREOS5_BBOE_BOOTED: Stage(
            run=to_twrp, steps=1, then=State.AMONET_FIREOS5_BBOE_TWRP
        ),
    }


def remaining(*, start: State, table: dict[State, Stage]) -> int | None:
    passing, reached = walked(start=start, table=table)
    if not reached or any(stage.steps is None for stage in passing):
        return None
    return sum(stage.steps or 0 for stage in passing)


def restore_stages() -> dict[State, Stage]:
    bootrom = ARGUMENTS.build in biscuit.BOOTROM_BUILDS
    return {
        twrp: Stage(
            needs=(
                (ota_build, FASTBRICKS[ARGUMENTS.target.device].source)
                if bootrom
                else (ota_build,)
            ),
            passes=TWRPS,
            run=stage_restore,
            steps=stock_steps() + 2 if bootrom else stock_steps(),
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
    printed = None
    awaiting = None
    deadline = None
    watch = DriverWatch()
    prompted = False
    restarts = 0
    since = 0.0
    upgrading = False
    while True:
        current = state()
        stranded = current == State.STOCK_FASTBOOT and current not in table
        installed = bool(done & INSTALLED_FROM.get(target.goal, frozenset()))
        restored = target.unlock is None and bool(done & TWRPS)
        resetting = (ARGUMENTS.factory_reset or upgrading) and not installed
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
        if current not in {
            State.BOOTROM,
            State.NONE,
            State.PRELOADER,
            State.STARTING,
            *TWRPS,
        }:
            SESSION.boot0_erased = False
        parked = SESSION.boot0_erased or current == State.BOOTROM
        if (
            current in BOOTROMS
            and parked
            and not (resumed or SESSION.held)
            and target.device not in KAMAKIRI_UNLOCKS
        ):
            if target.device not in BOOTROM_UNLOCKS:
                why = (
                    "has an erased boot0, which only its bootrom can start"
                    if SESSION.boot0_erased
                    else "answers on its bootrom's own USB id"
                )

                raise FatalError(
                    message=f"this {target.device.title} {why}, and firebreak has"
                    " no bootrom chain for it, so nothing was done."
                )
            chain = bootrom_chain()
            prefetch(
                needs=dict.fromkeys((
                    *bootrom_needs(unlock=chain.unlock),
                    *needed(start=chain.state, table=table),
                ))
            )
            if SESSION.boot0_erased:
                warn(
                    text=f"This run erased boot0, so the {title()} cannot start"
                    f" until {chain.unlock.name} is written through its bootrom."
                    " This run does that, then continues from that TWRP. If"
                    f" nothing happens within a minute, unplug the {title()} and"
                    " plug it back in.",
                )
            resumed = True
            done.difference_update(TWRPS)
            done.add(chain.state)
            if bootrom_step(
                amonet=unpack(download=chain.unlock.source),
                erase=None,
                little_kernel=chain.little_kernel,
                payload=amonet_payload(),
                tail=remaining(start=chain.then, table=table),
                unlock=chain.unlock,
            ):
                chain.after()
            else:
                done.discard(chain.state)
                resumed = False
            seen = None
            continue
        if current != seen:
            seen = current
            deadline = time.monotonic() + WAIT
            prompted = False
            since = time.monotonic()
            restarts = (
                restarts + (current == State.NONE)
                if current in {State.NONE, State.PRELOADER, State.STARTING}
                else 0
            )
            if restarts == RESTARTS and current == State.NONE and awaiting in TWRPS:
                PROGRESS.note(message=keeps_restarting())
            if ARGUMENTS.verbose and current != printed:
                printed = current
                show(text=f"{clock()} state: {current.value}")
            if (
                current not in done
                and current
                not in {State.BOOTED, State.NONE, State.PRELOADER, State.STARTING}
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
                password_first(device=target.device)
                say(text=unlock_ask(device=target.device))
            elif current == State.UNLOCKED_FASTBOOT and not done:
                say(
                    text=f"This {title()} is in its unlocked fastboot."
                    " Starting its recovery."
                )
            elif stranded and target.unlock is not None:
                check_target(target=target)
                if not guided:
                    password_first(device=target.device)
                guided = True
                say(text=stock_fastboot_ask(device=target.device))
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
                current == State.UNLOCKED_BOOTED
                and current not in done
                and (current != target.goal or resetting)
                and not upgrading
            ):
                say(
                    text=f"This {title()} runs rooted Fire OS 6 on an unlocked"
                    " bootloader. Rebooting it into TWRP."
                )
            elif current == State.NONE and not done and not PROGRESS.open and guided:
                line = waiting_line(device=target.device)
                if line:
                    show(text="\n" + filled(text=line))
            elif current == State.NONE and not done and not PROGRESS.open:
                guided = True
                password_first(device=target.device)
                say(text=usb_ask(device=target.device))
        if current == State.UNLOCKED_BOOTED == target.goal and not resetting:
            version = adb_shell(command="getprop ro.build.version.name")
            build = build_number(name=version)
            if (
                not installed
                and build in BUILDS[target.device]
                and outdated(build=build)
            ):
                say(
                    text=f"This {title()} runs rooted Fire OS 6 {build}. Rebooting it"
                    f" into TWRP to install {target.installs.build} over it, keeping"
                    " its setup."
                )
                prefetch(needs=needed(start=State.UNLOCKED_TWRP, table=table))
                upgrading = True
                seen = None
                continue
            warn(text=f"The {title()} is rooted: {version}, with root adb{locked()}.")
            if done:
                credit_note(target=target)
            cache_note()
            return
        if target.unlock is None and (
            current in {State.STOCK_BOOTED, State.STOCK_FASTBOOT}
            or (
                restored
                and ARGUMENTS.build
                in FIREOS5_BUILDS[target.device] | ADB_OFF_BUILDS[target.device]
                and current not in TWRPS
            )
        ):
            if done:
                PROGRESS.end()
                if SESSION.held:
                    passed(
                        message=f"Stock {ARGUMENTS.build} is written, and the"
                        f" {title()} waits in its bootrom."
                    )
                    say(
                        text=f"The {title()} cannot wait in fastboot, so firebreak"
                        " holds it in its bootrom, where the next run picks it up"
                        " with no button held. Power it off and it starts stock"
                        f" {ARGUMENTS.build} instead."
                    )
                elif ends_in_fastboot():
                    passed(
                        message=f"Stock {ARGUMENTS.build} is written, and the"
                        f" {title()} waits in fastboot."
                    )
                elif ARGUMENTS.build in FIREOS5_BUILDS[target.device]:
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
                elif ARGUMENTS.build in ADB_OFF_BUILDS[target.device]:
                    passed(
                        message=f"Stock {ARGUMENTS.build} is written, and the {title()}"
                        " is rebooting into it."
                    )
                    say(
                        text=f"Stock {ARGUMENTS.build} starts with adb off, so"
                        " firebreak cannot see it finish starting and does not"
                        f" wait for it. Keep the {title()} plugged in for a few"
                        " minutes while it starts."
                    )
                else:
                    passed(message=f"The {title()} runs stock {ARGUMENTS.build}.")
                warn(
                    text=f"If you plan to unlock this {title()} again, do not connect"
                    " it to Wi-Fi. Amazon can update it to a build firebreak"
                    " does not support."
                )
            else:
                say(text=nothing_to_restore(device=target.device))
            cache_note()
            return
        if current == target.goal and not resetting:
            hide_updater()
            version = adb_shell(command="getprop ro.build.version.name")
            selinux = adb_shell(command="getenforce")
            warn(
                text=f"The {title()} is rooted: {version}, SELinux {selinux},"
                f" {UPDATER} hidden{locked()}."
            )
            if done:
                credit_note(target=target)
            cache_note()
            return
        if (
            current in done
            or current
            in {State.NONE, State.PRELOADER, State.STOCK_BOOTED, State.STARTING}
            or (current == State.BOOTED and target.unlock is not None)
            or stranded
        ):
            waits = {State.NONE} if installed else {State.NONE, State.STOCK_BOOTED}
            if restored:
                waits = set()
            if stranded:
                waits.add(current)
            if (
                restored
                and current == State.NONE
                and not ends_in_fastboot()
                and time.monotonic() - since > STOCK_QUIET
            ):
                PROGRESS.end()
                passed(
                    message=f"Stock {ARGUMENTS.build} is written and verified, and"
                    f" the {title()} rebooted into it."
                )
                say(
                    text=f"The {title()} has shown nothing on USB for"
                    f" {STOCK_QUIET // MINUTE} minutes since. Stock turns adb off"
                    " during its first boot, so an Echo power-cycled during that boot"
                    " shows nothing on USB from then on, and firebreak stops"
                    " waiting. Keep it plugged in until its ring shows it has"
                    " started."
                )
                cache_note()
                return
            if current not in waits and time.monotonic() > deadline:
                if restored:
                    raise FatalError(
                        message=f"stock {ARGUMENTS.build} has not started"
                        f" {WAIT // 60} minutes after the restore"
                    )
                if (
                    current == State.STOCK_BOOTED
                    and target.goal == State.AMONET_FIREOS5_BBOE_BOOTED
                ):
                    raise FatalError(
                        message="Fire OS 5 started, and its adb refuses this"
                        " computer: adb uses a key other than the one the unlock"
                        " let in. " + again()
                    )
                if current == State.STOCK_BOOTED:
                    raise FatalError(
                        message="Fire OS 6 started without root adb for this"
                        " computer: boot-root.zip did not take, or adb uses a key"
                        " other than the one the unlock let in. " + again()
                    )
                if current == State.BOOTED:
                    raise FatalError(
                        message="Fire OS has not finished booting with root."
                        " Reboot to recovery. " + again()
                    )
                if current == State.PRELOADER:
                    raise FatalError(
                        message=f"the {title()}'s preloader has run for"
                        f" {WAIT // 60} minutes without starting a bootloader,"
                        " so the test point is the only way in: run"
                        " `firebreak short`."
                    )
                raise FatalError(
                    message=f"the {title()} has been"
                    f" {shown(current=current)} for"
                    f" {WAIT // 60} minutes. " + again()
                )
            if current == State.NONE and watch.confirmed():
                warn(text=NO_FASTBOOT_DRIVER)
            if (
                current == State.NONE
                and awaiting == State.UNLOCKED_BOOTED
                and not prompted
                and time.monotonic() - since > POWER_CYCLE
            ):
                prompted = True
                PROGRESS.note(message=power_cycle())
            time.sleep(2)
            continue
        if not done:
            check_target(target=target)
            if target.unlock is not None:
                adb_key()
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


def stage_kamakiri() -> bool:
    unlock = KAMAKIRI_UNLOCKS[ARGUMENTS.target.device]
    return kamakiri_step(source=unpack(download=unlock.source), unlock=unlock)


def stages() -> dict[State, Stage]:
    if ARGUMENTS.target.device in KAMAKIRI_UNLOCKS:
        return kamakiri_stages()
    chain = FIREOS5_CHAINS.get(ARGUMENTS.target.device)
    table = {
        State.EMOS: Stage(needs=(), run=stage_emos, steps=1, then=None),
        State.NO_SYSTEM: reboot_stages()[State.BOOTED],
        State.UNLOCKED_FASTBOOT: Stage(
            needs=(FASTBRICKS[ARGUMENTS.target.device].source,),
            run=stage_amonet_recovery,
            steps=1,
            then=State.UNLOCKED_TWRP,
        ),
    } | dict.fromkeys(
        (State.STOCK_FASTBOOT, State.STOCK_FIREOS5_FASTBOOT),
        Stage(
            needs=(FASTBRICKS[ARGUMENTS.target.device].source,),
            run=stage_fastbrick,
            steps=2,
            then=State.UNLOCKED_TWRP,
        ),
    )
    if chain is not None:
        table[State.AMONET_FIREOS5_FASTBOOT] = Stage(
            needs=(chain.unlock.source, TWRP),
            run=stage_fireos5_recovery,
            steps=1,
            then=State.AMONET_FIREOS5_BBOE_TWRP,
        )
    if ARGUMENTS.target.unlock is None:
        return table | restore_stages()
    if isinstance(ARGUMENTS.target.installs, FireOs6):
        return table | fireos6_stages()
    return table | fireos5_stages()


def start_prebuild() -> None:
    with contextlib.suppress(RuntimeError):
        PREBUILDER.start()


def stock_fastboot_ask(*, device: Device) -> str:
    return (
        f"This {title()} is in its stock fastboot. Its unlock starts only in its"
        " bootrom, so start it in its bootrom. A hold that starts after the cable"
        " goes in reaches fastboot, so start the hold first.\n\n" + device.short_gesture
    )


def unlock_ask(*, device: Device) -> str:
    lead = f"This {title()} appears to be unmodified. To unlock and root it,"
    if device not in KAMAKIRI_UNLOCKS:
        return (
            f"{lead} start it in fastboot mode.\n\n"
            + device.fastboot_mode
            + "\n\n"
            + amonet_has_no_fastboot()
        )
    return f"{lead} start it in its bootrom.\n\n" + device.short_gesture


def usb_ask(*, device: Device) -> str:
    lead = f"Waiting for the {title()} on USB. Connect it with a USB cable."
    tail = "\n\nCtrl-C stops the script."
    if device not in KAMAKIRI_UNLOCKS:
        return (
            f"{lead} One that runs Amazon's own software needs fastboot mode.\n\n"
            + device.fastboot_mode
            + tail
        )
    return (
        f"{lead} One that runs Amazon's own software needs its bootrom.\n\n"
        + device.short_gesture
        + tail
    )


def waiting_line(*, device: Device) -> str:
    if device in KAMAKIRI_UNLOCKS:
        return ""
    return (
        f"Waiting for the {title()} in fastboot mode: a green ring on a stock"
        " Echo, every color turning on amonet's."
    )


def walked(*, start: State, table: dict[State, Stage]) -> tuple[list[Stage], bool]:
    passing: list[Stage] = []
    for _ in range(len(table) + 1):
        if start == ARGUMENTS.target.goal and (passing or not ARGUMENTS.factory_reset):
            return passing, True
        stage = table.get(start)
        if stage is None:
            return passing, False
        passing.append(stage)
        if stage.then is None:
            return passing, False
        start = stage.then
    return passing, False
