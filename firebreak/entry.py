from __future__ import annotations

import contextlib
import sys
import time
from typing import TYPE_CHECKING

from firebreak.bootrom_step import (
    BOOTROM_STEP_TIMEOUT,
    answering_payload,
    ask_for_short,
    bootrom_client,
    exploit,
)
from firebreak.cache import ERASED, HELD
from firebreak.devices import BOOTROM_UNLOCKS, DEVICES, FASTBRICKS
from firebreak.host import pyserial_wheel, run
from firebreak.identify import POLL, identify
from firebreak.probe import state
from firebreak.route import TWRPS
from firebreak.states import State
from firebreak.twrp import clear_boot0, reboot
from firebreak.ui import (
    MINUTE,
    PROGRESS,
    SESSION,
    FatalError,
    confirm,
    passed,
    say,
    title,
)
from firebreak.unlock import (
    amonet_payload,
    current_device,
    erase_by_fastboot,
    restart_refusals,
    stage_amonet_recovery,
    stage_fastbrick,
    stage_fireos5_recovery,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from firebreak.amonet.biscuit_v2_0_0 import Client
    from firebreak.bootrom import Bootrom
    from firebreak.plugin import Device

BOOTROM = "bootrom"
FASTBOOT = "fastboot"
FASTBOOTS = frozenset({
    State.AMONET_FASTBOOT,
    State.AMONET_FIREOS5_FASTBOOT,
    State.STOCK_FASTBOOT,
    State.STOCK_FIREOS5_FASTBOOT,
})
LOCKED_FASTBOOTS = frozenset({State.STOCK_FASTBOOT, State.STOCK_FIREOS5_FASTBOOT})
RECOVERY_WAIT = 90
STUCK = 600
TO_FASTBOOT = (
    frozenset({
        State.AMONET_BOOTED,
        State.AMONET_FIREOS5_BBOE_BOOTED,
        State.BOOTED,
        State.NO_SYSTEM,
        State.ROOTED,
    })
    | TWRPS
)
TO_TWRP = frozenset({
    State.AMONET_BOOTED,
    State.AMONET_FIREOS5_BBOE_BOOTED,
    State.NO_SYSTEM,
    State.ROOTED,
})
TWRP = "twrp"
WAITS = frozenset({State.NONE, State.STARTING})
WAYS_OUT = {
    State.BOOTROM: " A chain written through the payload there is the way out:"
    " run `firebreak unlock` or `firebreak stock`.",
    State.PRELOADER: " Its boot0 holds a preloader that never starts a"
    " bootloader, so the test point is the only way in:"
    " run `firebreak bootrom --short`.",
}


def answering() -> Client | None:
    if not HELD.exists():
        return None
    with_pyserial()
    live = answering_payload()
    if live is None:
        HELD.unlink(missing_ok=True)
    return live


def bootrom_entry(*, force: bool, short: bool) -> None:
    PROGRESS.steps = None
    noticed()
    device = known_device()
    if short:
        SESSION.short = True
        parked(payload=reached(erase=None))
        return
    current = state()
    if current == State.BOOTROM:
        live = answering()
        if live is not None:
            with contextlib.suppress(OSError):
                live.port.close()
            passed(message=f"The {device.title} already waits in its bootrom.")
            return
        parked(payload=reached(erase=None))
        return
    if current == State.NONE and (ERASED.exists() or HELD.exists()):
        raise FatalError(
            message=f"nothing is on USB, and {ERASED.name} says this"
            f" {device.title} starts only from its bootrom. Power it on and run"
            " this again within about 40 seconds, which is how long its bootrom"
            " answers before its own watchdog takes it."
        )
    if current in TWRPS:
        device = chainable()
        confirm(
            force=force,
            what=f"clearing boot0's header leaves the {device.title} able to start"
            " from its bootrom alone, until something writes a preloader back",
        )
        ERASED.write_text(device.name)
        clear_boot0()
        run(arguments=["adb", "reboot"], timeout=60)
        parked(payload=reached(erase=None))
    elif current in FASTBOOTS - LOCKED_FASTBOOTS:
        device = chainable()
        confirm(
            force=force,
            what=f"erasing boot0 leaves the {device.title} able to start from its"
            " bootrom alone, until something writes a preloader back",
        )
        ERASED.write_text(device.name)
        parked(payload=reached(erase=erase_by_fastboot))
    elif current in LOCKED_FASTBOOTS:
        raise FatalError(
            message=f"this {device.title} is locked, and a locked bootloader"
            " refuses to erase boot0. Unlock it first, or run"
            f" `firebreak {BOOTROM} --short` on an Echo that shows no light."
        )
    else:
        raise FatalError(
            message=f"the {known()} reads as {current.value}, which nothing"
            f" here can reach a {BOOTROM} from. Start its fastboot or its TWRP"
            f" first, with `firebreak {FASTBOOT}` or `firebreak {TWRP}`, or"
            f" short its test point with `firebreak {BOOTROM} --short`."
        )


def chainable() -> Device:
    device = known_device()
    if device not in BOOTROM_UNLOCKS:
        raise FatalError(
            message=f"firebreak has no bootrom chain for the {device.title}, so"
            " clearing boot0 would leave it starting nothing but a bootrom that"
            " nothing here can write a preloader through. Nothing was done."
        )
    return device


def entries() -> tuple[str, ...]:
    return (FASTBOOT, TWRP, BOOTROM)


def fastboot_entry() -> None:
    walk(
        acts={
            **dict.fromkeys(TO_FASTBOOT, to_fastboot),
            State.STOCK_BOOTED: gesture,
        },
        goal=FASTBOOTS,
        patient=frozenset({State.STOCK_BOOTED}),
        what=FASTBOOT,
    )


def gesture() -> None:
    device = known_device()
    say(text=f"Start the {device.title}'s fastboot.\n\n" + device.fastboot_mode)


def known() -> str:
    device = SESSION.device
    return device.title if device is not None else title()


def known_device() -> Device:
    noticed()
    return current_device()


def marked() -> Device | None:
    for marker in (ERASED, HELD):
        if marker.exists():
            name = marker.read_text(encoding="utf-8").strip()
            return next((each for each in DEVICES if each.name == name), None)
    return None


def noticed() -> None:
    if SESSION.device is None:
        SESSION.device = identify().device or marked()


def parked(*, payload: tuple[Bootrom, Client]) -> None:
    PROGRESS.end()
    client, _ = payload
    with contextlib.suppress(OSError):
        client.port.close()
    device = known_device()
    HELD.write_text(device.name)
    SESSION.held = True
    passed(message=f"The {device.title} waits in its bootrom.")
    say(
        text="amonet's payload holds it, so the next run joins that payload"
        " rather than handshaking at it. "
        + (
            "boot0 is erased, so a power cycle brings its bootrom back, and the"
            " run after that writes a chain through it."
            if ERASED.exists()
            else f"Leave the {device.title} plugged in: a power cycle loses the"
            " hold, and starts the firmware boot0 still holds."
        )
    )


def reached(*, erase: Callable[[], str] | None) -> tuple[Bootrom, Client]:
    with_pyserial()
    payload = amonet_payload()
    if SESSION.short:
        ask_for_short()
    if erase is not None:
        failure = erase()
        if failure:
            raise FatalError(message=failure)
    PROGRESS.begin(estimate="15 s", label="starting amonet's payload")
    client = bootrom_client(
        deadline=time.monotonic() + (MINUTE if erase else BOOTROM_STEP_TIMEOUT),
        erase=erase,
    )
    if client is None:
        raise FatalError(
            message=f"the {known_device().title} did not reach its bootrom."
        )
    return client, exploit(client=client, payload=payload)


def restarted() -> None:
    PROGRESS.begin(estimate="40 s", label="restarting into the recovery it holds")
    if restart_refusals():
        PROGRESS.end(skipped=True)
        raise FatalError(
            message=f"this {known()}'s fastboot took neither command that starts"
            " its recovery, so nothing was written. Unplug it, and hold the +"
            " button while you plug it back in, which starts its TWRP itself."
        )
    deadline = time.monotonic() + RECOVERY_WAIT
    while time.monotonic() < deadline:
        if state() in TWRPS:
            return
        time.sleep(POLL)
    PROGRESS.end(skipped=True)
    raise FatalError(
        message=f"the {known()} restarted, and no TWRP answered in"
        f" {RECOVERY_WAIT} s, so what its recovery holds is not one. Nothing"
        " was written. Power it off and on to leave that recovery, then run"
        f" `firebreak {FASTBOOT}` and `firebreak {TWRP} --force`, which writes"
        " a TWRP there."
    )


def to_fastboot() -> None:
    reboot(into="bootloader", label="waiting for fastboot")


def to_twrp() -> None:
    reboot(label="waiting for TWRP to start")


def twrp_entry(*, force: bool) -> None:
    def writing(
        *, run: Callable[[], object], what: Callable[[], str]
    ) -> Callable[[], None]:
        def act() -> None:
            confirm(force=force, what=what())
            run()

        return act

    def unlocking() -> None:
        device = known_device()
        if device not in FASTBRICKS:
            raise FatalError(
                message=f"firebreak has no fastbrick for the {device.title}, so"
                " it cannot unlock one, and a locked bootloader starts no TWRP."
                " Nothing was written."
            )
        confirm(
            force=force,
            what=f"the {device.title} is locked, so reaching a TWRP unlocks it"
            " first, which erases everything on it",
        )
        stage_fastbrick()

    walk(
        acts={
            **dict.fromkeys(TO_TWRP, to_twrp),
            **dict.fromkeys(LOCKED_FASTBOOTS, unlocking),
            State.AMONET_FASTBOOT: writing(
                run=stage_amonet_recovery,
                what=lambda: (
                    f"starting a TWRP on the {known()} writes one to its"
                    " recovery partition"
                ),
            )
            if force
            else restarted,
            State.AMONET_FIREOS5_FASTBOOT: writing(
                run=stage_fireos5_recovery,
                what=lambda: (
                    f"starting a TWRP on the {known()} writes one to its"
                    " recovery partition, and its TEE beside it"
                ),
            )
            if force
            else restarted,
            State.STOCK_BOOTED: gesture,
        },
        goal=TWRPS,
        patient=frozenset({State.STOCK_BOOTED}),
        what=TWRP,
    )


def walk(
    *,
    acts: dict[State, Callable[[], None]],
    goal: frozenset[State],
    patient: frozenset[State],
    what: str,
) -> None:
    acted: set[State] = set()
    said = False
    since = time.monotonic()
    PROGRESS.steps = None
    while True:
        current = state()
        noticed()
        if current in goal:
            PROGRESS.end()
            passed(message=f"The {known()} is in {current.value}.")
            return
        act = acts.get(current)
        if act is None and current not in WAITS:
            raise FatalError(
                message=f"the {known()} reads as {current.value}, which nothing"
                f" here can reach a {what} from." + WAYS_OUT.get(current, "")
            )
        if current == State.NONE and ERASED.exists():
            raise FatalError(
                message=f"boot0 is erased, so this {known()} starts nothing but"
                f" its bootrom and reaches no {what} until a chain is written"
                " through it: run `firebreak unlock` or `firebreak stock`."
                " Waiting here would wait for a state it cannot reach."
            )
        if current == State.NONE and not (said or PROGRESS.open):
            said = True
            say(
                text=f"Waiting for the {known()} on USB. A reboot reads this way"
                " until it comes back. An Echo that shows no light never does:"
                f" `firebreak {BOOTROM} --short` reaches that one."
            )
        if act is not None and current not in acted:
            acted.add(current)
            act()
            since = time.monotonic()
        elif current not in patient | WAITS and time.monotonic() - since > STUCK:
            raise FatalError(
                message=f"the {known()} has read as {current.value} for"
                f" {STUCK // 60} minutes, so this run stops."
            )
        time.sleep(POLL)


def with_pyserial() -> None:
    wheel = pyserial_wheel()
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
