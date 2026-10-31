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
    payload_device,
    unwritten,
)
from firebreak.devices import BOOTROM_UNLOCKS, FASTBRICKS, FIREOS5_CHAINS
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
    WAIT,
    FatalError,
    asked_for,
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
NAMELESS = frozenset({State.BOOTROM, State.NONE, State.PRELOADER})
RECOVERY_WAIT = 90
SHORT = "short"
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
TRIES = 5
TWRP = "twrp"
WAITS = frozenset({State.NONE, State.PRELOADER, State.STARTING})
WAYS_OUT = {
    State.NONE: " An Echo that shows no light never comes back on its own:"
    " `firebreak short` reaches that one through its test point.",
    State.BOOTROM: " A chain written through the payload there is the way out:"
    " run `firebreak unlock` or `firebreak stock`.",
    State.PRELOADER: " A preloader that never starts a bootloader leaves the"
    " test point as the only way in: run `firebreak short`.",
}


def already_held() -> bool:
    live = answering()
    if live is None:
        return False
    checked_device(live=live)
    with contextlib.suppress(OSError):
        live.port.close()
    passed(message=f"The {known()} already waits in its bootrom.")
    return True


def answering() -> Client | None:
    with_pyserial()
    return answering_payload()


def awaited() -> State:
    said = False
    since = time.monotonic()
    while True:
        current = state()
        if current not in NAMELESS:
            noticed()
        if current not in WAITS:
            return current
        if not said:
            said = True
            say(text=awaiting())
        if time.monotonic() - since > STUCK:
            raise FatalError(
                message=f"the {known()} has read as {current.value} for"
                f" {STUCK // 60} minutes, so this run stops."
                + WAYS_OUT.get(current, "")
            )
        time.sleep(POLL)


def awaiting() -> str:
    if SESSION.boot0_erased:
        return (
            f"boot0 is erased, so this {known()} starts nothing but its bootrom."
            " Power it on: its bootrom answers for about 40 seconds, and this"
            " run takes it from there."
        )
    return (
        f"Waiting for the {known()} on USB. A reboot reads this way until it"
        " comes back."
    )


def bootrom_device() -> Device | None:
    if SESSION.read_flash or state() != State.BOOTROM:
        return None
    SESSION.read_flash = True
    live = answering()
    if live is None:
        live = reached(erase=None)
    PROGRESS.end()
    device = payload_device(live=live)
    with contextlib.suppress(OSError):
        live.port.close()
    SESSION.device = device or SESSION.device
    return device


def bootrom_entry(*, force: bool) -> None:
    PROGRESS.steps = None
    noticed()
    current = awaited()
    if current == State.BOOTROM:
        if already_held():
            return
        parked(live=reached(erase=None))
        return
    if current in TO_TWRP:
        current = walk(
            acts=dict.fromkeys(TO_TWRP, to_twrp),
            goal=TWRPS,
            patient=frozenset(),
            what=TWRP,
        )
    if current in TWRPS:
        device = chainable()
        confirm(
            force=force,
            what=f"clearing boot0's header leaves the {device.title} able to start"
            " from its bootrom alone, until something writes a preloader back",
        )
        with_pyserial()
        amonet_payload()
        SESSION.boot0_erased = True
        clear_boot0()
        run(arguments=["adb", "reboot"], timeout=60)
        parked(live=reached(erase=None))
    elif current in FASTBOOTS - LOCKED_FASTBOOTS:
        device = chainable()
        confirm(
            force=force,
            what=f"erasing boot0 leaves the {device.title} able to start from its"
            " bootrom alone, until something writes a preloader back",
        )
        parked(live=reached(erase=erase_by_fastboot))
    elif current in LOCKED_FASTBOOTS:
        raise FatalError(
            message=f"this {known()} is locked, and a locked bootloader"
            " refuses to erase boot0. Unlock it first, or run"
            f" `firebreak {SHORT}` on an Echo that shows no light."
        )
    else:
        raise FatalError(
            message=f"the {known()} reads as {current.value}, which nothing"
            f" here can reach a {BOOTROM} from. Start its fastboot or its TWRP"
            f" first, with `firebreak {FASTBOOT}` or `firebreak {TWRP}`, or"
            f" short its test point with `firebreak {SHORT}`."
        )


def chainable() -> Device:
    noticed()
    device = SESSION.device
    if device is None:
        raise FatalError(
            message="this Echo is in a state that names which device it is, a"
            " fastboot or a recovery, and it named none, so this run cannot"
            " tell whether a chain exists to write a preloader back through its"
            f" bootrom. {unwritten()} Power cycle it and run this again: a read"
            " of the name can be cut. " + asked_for()
        )
    if device not in BOOTROM_UNLOCKS:
        raise FatalError(
            message=f"firebreak has no bootrom chain for the {device.title}, so"
            " clearing boot0 would leave it starting nothing but a bootrom that"
            f" nothing here can write a preloader through. {unwritten()}"
        )
    return device


def checked_device(*, live: Client) -> None:
    found = payload_device(live=live)
    if found is not None and SESSION.device not in {None, found}:
        SESSION.held = True
        with contextlib.suppress(OSError):
            live.port.close()
        raise FatalError(
            message=f"this Echo's bootloader names it an {found.title}, not the"
            f" {known()} this run expected. Its bootrom is held, and a run"
            " that cleared or erased boot0 to get here has"
            " already done that: `firebreak unlock` reads the name from that"
            " flash and writes a chain for the Echo this actually is."
        )
    SESSION.device = found or SESSION.device


def entries() -> tuple[str, ...]:
    return (FASTBOOT, TWRP, BOOTROM, SHORT)


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


def noticed() -> None:
    if SESSION.device is None:
        SESSION.device = identify().device


def parked(*, live: Client) -> None:
    PROGRESS.end()
    checked_device(live=live)
    with contextlib.suppress(OSError):
        live.port.close()
    SESSION.held = True
    passed(message=f"The {known()} waits in its bootrom.")
    say(
        text="boot0 is erased, so a power cycle brings its bootrom back, and the"
        " run after that writes a chain through it."
        if SESSION.boot0_erased
        else f"Leave the {known()} plugged in: a power cycle loses the hold, and"
        " starts the firmware boot0 still holds."
    )


def reached(*, erase: Callable[[], str] | None) -> Client:
    with_pyserial()
    payload = amonet_payload()
    if SESSION.short:
        ask_for_short()
    if erase is not None:
        SESSION.boot0_erased = True
        failure = erase()
        if failure:
            raise FatalError(message=failure)
    if not SESSION.short:
        PROGRESS.begin(estimate="40 s", label="waiting for the bootrom")
    client, live = bootrom_client(
        deadline=time.monotonic() + waiting(erase=erase), erase=erase
    )
    if live is not None:
        return live
    if client is None:
        raise FatalError(message=f"the {known()} did not reach its bootrom.")
    if not SESSION.short:
        PROGRESS.begin(estimate="15 s", label="starting amonet's payload")
    return exploit(client=client, payload=payload)


def registered(*, holding: dict[Device, object], what: str) -> Device:
    device = known_device()
    if device not in holding:
        raise FatalError(
            message=f"firebreak has no {what} for the {device.title}, so it"
            " cannot write a recovery to one, and nothing was written."
        )
    return device


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


def revisited(
    *, acted: set[State], current: State, since: float, tries: dict[State, int]
) -> float:
    tries[current] = tries.get(current, 0) + 1
    if tries[current] > TRIES:
        return since
    acted.discard(current)
    return time.monotonic()


def short_entry() -> None:
    PROGRESS.steps = None
    SESSION.short = True
    noticed()
    if already_held():
        return
    parked(live=reached(erase=None))


def to_fastboot() -> None:
    reboot(into="bootloader", label="restarting into fastboot")


def to_twrp() -> None:
    reboot(label="restarting into TWRP")


def twrp_entry(*, force: bool) -> None:
    def amonet_recovery() -> None:
        registered(holding=FASTBRICKS, what="fastbrick")
        stage_amonet_recovery()

    def fireos5_recovery() -> None:
        registered(holding=FIREOS5_CHAINS, what="Fire OS 5 chain")
        stage_fireos5_recovery()

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
            State.BOOTED: to_fastboot,
            State.AMONET_FASTBOOT: amonet_recovery if force else restarted,
            State.AMONET_FIREOS5_FASTBOOT: fireos5_recovery if force else restarted,
            State.STOCK_BOOTED: gesture,
        },
        goal=TWRPS,
        patient=frozenset({State.STOCK_BOOTED}),
        what=TWRP,
    )


def waiting(*, erase: Callable[[], str] | None) -> float:
    if erase is not None:
        return MINUTE
    return BOOTROM_STEP_TIMEOUT if SESSION.short else WAIT


def walk(
    *,
    acts: dict[State, Callable[[], None]],
    goal: frozenset[State],
    patient: frozenset[State],
    what: str,
) -> State:
    acted: set[State] = set()
    said = False
    seen = None
    since = time.monotonic()
    tries: dict[State, int] = {}
    PROGRESS.steps = None
    while True:
        current = state()
        if current != seen:
            seen = current
            since = revisited(acted=acted, current=current, since=since, tries=tries)
        if current not in NAMELESS:
            noticed()
        if current in goal:
            PROGRESS.end()
            passed(message=f"The {known()} is in {current.value}.")
            return current
        act = acts.get(current)
        if act is None and current not in WAITS:
            raise FatalError(
                message=f"the {known()} reads as {current.value}, which nothing"
                f" here can reach a {what} from." + WAYS_OUT.get(current, "")
            )
        if current == State.NONE and SESSION.boot0_erased:
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
                f" `firebreak {SHORT}` reaches that one."
            )
        if act is not None and current not in acted:
            acted.add(current)
            act()
            SESSION.usb_read = None
            since = time.monotonic()
        elif current not in patient and time.monotonic() - since > STUCK:
            raise FatalError(
                message=f"the {known()} has read as {current.value} for"
                f" {STUCK // 60} minutes, so this run stops."
                + WAYS_OUT.get(current, "")
            )
        time.sleep(POLL)


def with_pyserial() -> None:
    wheel = pyserial_wheel()
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
