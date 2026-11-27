from __future__ import annotations

import contextlib
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
from firebreak.cache import unpack
from firebreak.devices import (
    BOOTROM_UNLOCKS,
    DEFAULTS,
    FASTBRICKS,
    FIREOS5_CHAINS,
    KAMAKIRI_UNLOCKS,
)
from firebreak.host import run
from firebreak.identify import POLL, identify
from firebreak.kamakiri_step import kamakiri_step
from firebreak.mediatek.usbdl import UsbdlError
from firebreak.probe import state
from firebreak.route import TWRPS, password_first
from firebreak.states import State, shown
from firebreak.twrp import ask_fastboot, clear_boot0, reboot, restart_into_twrp
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
    this_command,
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
    stage_kamakiri_recovery,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from firebreak.amonet.biscuit_v2_0_0 import Client
    from firebreak.mediatek.usbdl import Bootrom
    from firebreak.plugin import Device

BOOTROM = "bootrom"
FASTBOOT = "fastboot"
FASTBOOTS = frozenset({
    State.UNLOCKED_FASTBOOT,
    State.AMONET_FIREOS5_FASTBOOT,
    State.STOCK_FASTBOOT,
    State.STOCK_FIREOS5_FASTBOOT,
})
HARDWARE_CODES = {
    unlock.device.hardware_code: unlock.device
    for unlock in KAMAKIRI_UNLOCKS.values()
    if unlock.device.hardware_code is not None
}
LOCKED_FASTBOOTS = frozenset({State.STOCK_FASTBOOT, State.STOCK_FIREOS5_FASTBOOT})
LOCKED = frozenset({State.STOCK_BOOTED, *LOCKED_FASTBOOTS})
NAMELESS = frozenset({State.BOOTROM, State.NONE, State.PRELOADER})
ONLY_THE_PAYLOAD = (
    "Only amonet's payload can write one back from there, and an eMMC that payload"
    " cannot reach keeps the Echo in its bootrom for good"
)
QUIET = 120
REBOOT = "reboot"
RECOVERY_WAIT = 90
RUNNING = frozenset({
    State.UNLOCKED_BOOTED,
    State.AMONET_FIREOS5_BBOE_BOOTED,
    State.BOOTED,
    State.EMOS,
    State.ROOTED,
    State.STOCK_BOOTED,
})
SHORT = "short"
STUCK = 600
TO_FASTBOOT = (
    frozenset({
        State.UNLOCKED_BOOTED,
        State.AMONET_FIREOS5_BBOE_BOOTED,
        State.BOOTED,
        State.NO_SYSTEM,
        State.ROOTED,
    })
    | TWRPS
)
TO_TWRP = frozenset({
    State.UNLOCKED_BOOTED,
    State.AMONET_FIREOS5_BBOE_BOOTED,
    State.NO_SYSTEM,
    State.ROOTED,
})
TRIES = 5
TWRP = "twrp"
WAITS = frozenset({State.NONE, State.PRELOADER, State.STARTING})
WAYS_OUT = {
    State.NO_SYSTEM: " Its system partition holds no Fire OS:"
    " `firebreak unlock` or `firebreak stock` installs one.",
    State.NONE: " An Echo that shows no light never comes back on its own:"
    " `firebreak short` reaches that one through its test point.",
    State.BOOTROM: " A chain written through the payload there is the way out:"
    " run `firebreak unlock` or `firebreak stock`.",
    State.PRELOADER: " A preloader that never starts a bootloader leaves the"
    " test point as the only way in: run `firebreak short`.",
}


class NotAmonetError(FatalError):
    def __init__(self, *, device: Device) -> None:
        self.device = device
        target = DEFAULTS.get(device)
        way = (
            f" `firebreak unlock {target}` is the way into this one." if target else ""
        )
        super().__init__(
            message=f"this is an {device.title}, which amonet does not unlock,"
            f" so its bootrom was left alone.{way}"
        )


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
                message=f"the {known()} has read as {shown(current=current)} for"
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
        try:
            live = reached(erase=None)
        except NotAmonetError as error:
            PROGRESS.end()
            SESSION.device = error.device
            return error.device
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
        refuse_kamakiri()
        if already_held():
            return
        parked(live=reached(erase=None))
        return
    if SESSION.device is not None:
        chainable()
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
            " from its bootrom alone, until something writes a preloader back. "
            + ONLY_THE_PAYLOAD,
        )
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
            " bootrom alone, until something writes a preloader back. "
            + ONLY_THE_PAYLOAD,
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
            message=f"the {known()} reads as {shown(current=current)},"
            f" which nothing here can reach a {BOOTROM} from. Start its"
            f" fastboot or its TWRP first, with `firebreak {FASTBOOT}` or"
            f" `firebreak {TWRP}`, or"
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
            f" bootrom. {unwritten()} Power cycle it and run {this_command()} again:"
            " a read of the name can be cut. " + asked_for()
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


def deferred(*, erase: Callable[[], str] | None) -> bool:
    return erase is None and not SESSION.short and SESSION.device not in FASTBRICKS


def entries() -> tuple[str, ...]:
    return (REBOOT, FASTBOOT, TWRP, BOOTROM, SHORT)


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


def firmware_from_fastboot() -> None:
    run(arguments=["fastboot", "reboot"], check=True, timeout=60)
    PROGRESS.begin(estimate=60, label="starting its firmware")


def firmware_from_twrp() -> None:
    reboot(estimate=60, into="", label="starting its firmware")


def gesture() -> None:
    device = known_device()
    say(text=f"Start the {device.title}'s fastboot.\n\n" + device.fastboot_mode)


def held_payload(*, client: Bootrom) -> pathlib.Path:
    try:
        client.disable_watchdog()
        PROGRESS.end()
        return amonet_payload()
    except (FatalError, OSError, UsbdlError) as error:
        with contextlib.suppress(OSError):
            client.port.close()
        why = error.message if isinstance(error, FatalError) else str(error)
        raise FatalError(
            message=f"the {known()} waits in its bootrom for amonet's payload,"
            f" which this run could not ready: {why.rstrip('.')}. {unwritten()} Unplug"
            f" the {known()} and run {this_command()} again."
        ) from error


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


def power_cycle() -> None:
    raise FatalError(
        message=f"the {known()} waits in its bootrom, and nothing here restarts"
        " it from there. Unplug it and plug it back in, which starts the"
        " firmware boot0 holds. Nothing was written. An Echo whose boot0 a run"
        " erased starts its bootrom again, and `firebreak unlock` or"
        " `firebreak stock` writes a chain through it."
    )


def quiet() -> str:
    return (
        f"the {known()} has shown nothing on USB for {QUIET // 60} minutes."
        " Stock Fire OS turns adb off once an Echo is registered, so one that"
        " runs its firmware can show nothing: if its light ring says it has"
        " started, it is running. An Echo that shows no light never comes back"
        f" on its own: `firebreak {SHORT}` reaches that one."
    )


def reached(*, erase: Callable[[], str] | None) -> Client:
    payload = None if deferred(erase=erase) else amonet_payload()
    if SESSION.short:
        ask_for_short()
    if erase is not None:
        SESSION.boot0_erased = True
        failure = erase()
        if failure:
            raise FatalError(message=failure)
    if not SESSION.short:
        PROGRESS.begin(estimate=40, label="waiting for the bootrom")
    client, live = bootrom_client(
        deadline=time.monotonic() + waiting(erase=erase), erase=erase
    )
    if live is not None:
        return live
    if client is None:
        raise FatalError(message=f"the {known()} did not reach its bootrom.")
    named = HARDWARE_CODES.get(SESSION.hardware_code)
    if named is not None:
        with contextlib.suppress(OSError):
            client.port.close()
        raise NotAmonetError(device=named)
    if payload is None:
        payload = held_payload(client=client)
    if not SESSION.short:
        PROGRESS.begin(estimate=15, label="starting amonet's payload")
    return exploit(client=client, payload=payload)


def reboot_entry() -> None:
    walk(
        acts={
            **dict.fromkeys(FASTBOOTS, firmware_from_fastboot),
            **dict.fromkeys(TWRPS, firmware_from_twrp),
            State.BOOTROM: power_cycle,
        },
        goal=RUNNING,
        patient=frozenset(),
        silent=quiet,
        what="firmware",
    )


def refuse_kamakiri() -> None:
    if SESSION.device in KAMAKIRI_UNLOCKS:
        raise NotAmonetError(device=SESSION.device)


def registered(*, holding: dict[Device, object], what: str) -> Device:
    device = known_device()
    if device not in holding:
        raise FatalError(
            message=f"firebreak has no {what} for the {device.title}, so it"
            " cannot write a recovery to one, and nothing was written."
        )
    return device


def restarted() -> None:
    PROGRESS.begin(estimate=40, label="restarting into TWRP")
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


def rooted_to_twrp() -> None:
    restart_into_twrp(device=known_device())


def short_entry() -> None:
    PROGRESS.steps = None
    SESSION.short = True
    noticed()
    refuse_kamakiri()
    if already_held():
        return
    parked(live=reached(erase=None))


def to_fastboot() -> None:
    command = known_device().fastboot_command
    if not command:
        reboot(into="bootloader", label="restarting into fastboot")
        return
    ask_fastboot(command=command)
    reboot(into="", label="restarting into fastboot")


def to_twrp() -> None:
    reboot(label="restarting into TWRP")


def twrp_entry(*, force: bool, named: Device | None = None) -> None:  # ruff: ignore[complex-structure]
    unlocked_here: list[bool] = []

    def amonet_recovery() -> None:
        registered(holding=FASTBRICKS, what="fastbrick")
        stage_amonet_recovery()

    def bootrom_unlock() -> None:
        if SESSION.device is None and named in KAMAKIRI_UNLOCKS:
            SESSION.device = named
            confirm(
                force=force,
                what=f"this Echo, in its bootrom, is taken to be the backup's"
                f" {named.title}, and reaching its TWRP unlocks it first, which"
                " rewrites its preloader, its bootloaders, its TEE and its recovery",
            )
        device = known_device()
        if device not in KAMAKIRI_UNLOCKS:
            raise FatalError(
                message=f"the {device.title} reads as"
                f" {shown(current=State.BOOTROM)}, which nothing here can reach a"
                f" {TWRP} from." + WAYS_OUT[State.BOOTROM]
            )
        unlock = KAMAKIRI_UNLOCKS[device]
        kamakiri_step(source=unpack(download=unlock.source), unlock=unlock)
        unlocked_here.append(True)

    def kamakiri_locked() -> None:
        device = known_device()
        confirm(
            force=force,
            what=f"the {device.title} is locked, so reaching a TWRP unlocks it"
            " first through its bootrom, which rewrites its preloader, its"
            " bootloaders, its TEE and its recovery",
        )
        password_first(device=device)
        say(
            text=f"The {device.title} is locked, and only its bootrom can unlock"
            " it, so start it in its bootrom. A hold that starts after the cable"
            " goes in reaches fastboot, so start the hold first.\n\n"
            + device.short_gesture
        )
        while state() in LOCKED:
            time.sleep(POLL)

    def stock_booted() -> None:
        if known_device() in KAMAKIRI_UNLOCKS:
            kamakiri_locked()
            return
        gesture()

    def unlocked_fastboot() -> None:
        if known_device() in KAMAKIRI_UNLOCKS and (force or unlocked_here):
            unlocked_here.clear()
            stage_kamakiri_recovery()
        elif force:
            amonet_recovery()
        else:
            restarted()

    def fireos5_recovery() -> None:
        registered(holding=FIREOS5_CHAINS, what="Fire OS 5 chain")
        stage_fireos5_recovery()

    def unlocking() -> None:
        device = known_device()
        if device in KAMAKIRI_UNLOCKS:
            kamakiri_locked()
            return
        if device not in FASTBRICKS:
            raise FatalError(
                message=f"firebreak has no fastbrick for the {device.title}, so"
                " it cannot unlock one, and a locked bootloader starts no TWRP."
                " Nothing was written."
            )
        confirm(
            force=force,
            what=f"the {device.title} is locked, so reaching a TWRP unlocks it"
            " first, which rewrites its bootloaders, its TEE and its recovery",
        )
        stage_fastbrick()

    walk(
        acts={
            **dict.fromkeys(TO_TWRP, to_twrp),
            State.UNLOCKED_BOOTED: rooted_to_twrp,
            **dict.fromkeys(LOCKED_FASTBOOTS, unlocking),
            State.BOOTED: to_fastboot,
            State.BOOTROM: bootrom_unlock,
            State.UNLOCKED_FASTBOOT: unlocked_fastboot,
            State.AMONET_FIREOS5_FASTBOOT: fireos5_recovery if force else restarted,
            State.STOCK_BOOTED: stock_booted,
        },
        goal=TWRPS,
        patient=frozenset({State.STOCK_BOOTED}),
        what=TWRP,
    )


def unseen(
    *, said: bool, silent: Callable[[], str] | None, since: float, what: str
) -> bool:
    if SESSION.boot0_erased:
        raise FatalError(
            message=f"boot0 is erased, so this {known()} starts nothing but"
            f" its bootrom and reaches no {what} until a chain is written"
            " through it: run `firebreak unlock` or `firebreak stock`."
            " Waiting here would wait for a state it cannot reach."
        )
    if silent is not None and time.monotonic() - since > QUIET:
        raise FatalError(message=silent())
    if said or PROGRESS.open:
        return said
    say(
        text=f"Waiting for the {known()} on USB. A reboot reads this way"
        " until it comes back. An Echo that shows no light never does:"
        f" `firebreak {SHORT}` reaches that one."
    )
    return True


def waiting(*, erase: Callable[[], str] | None) -> float:
    if erase is not None:
        return MINUTE
    return BOOTROM_STEP_TIMEOUT if SESSION.short else WAIT


def walk(
    *,
    acts: dict[State, Callable[[], None]],
    goal: frozenset[State],
    patient: frozenset[State],
    silent: Callable[[], str] | None = None,
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
            arrived = "runs its firmware, read as" if current in RUNNING else "is in"
            passed(message=f"The {known()} {arrived} {shown(current=current)}.")
            return current
        act = acts.get(current)
        if act is None and current not in WAITS:
            raise FatalError(
                message=f"the {known()} reads as {shown(current=current)},"
                f" which nothing here can reach a {what} from."
                + WAYS_OUT.get(current, "")
            )
        if current == State.NONE:
            said = unseen(said=said, silent=silent, since=since, what=what)
        if act is not None and current not in acted:
            acted.add(current)
            act()
            SESSION.usb_read = None
            since = time.monotonic()
        elif current not in patient and time.monotonic() - since > STUCK:
            raise FatalError(
                message=f"the {known()} has read as {shown(current=current)} for"
                f" {STUCK // 60} minutes, so this run stops."
                + WAYS_OUT.get(current, "")
            )
        time.sleep(POLL)
