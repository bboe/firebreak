from __future__ import annotations

import contextlib
import re
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from firebreak import bootrom
from firebreak.amonet.biscuit_v2_0_0 import Client
from firebreak.amonet.payload import NotReadyError, Payload, start_payload
from firebreak.android.gpt import ENTRIES_SIZE, SECTOR_SIZE, gpt_intact, partition_map
from firebreak.cache import ERASED
from firebreak.devices import biscuit
from firebreak.emmc import EmmcArea
from firebreak.host import getvar, in_fastboot, no_port_help
from firebreak.mediatek import range_check
from firebreak.mediatek.usbdl import (
    BAUD_RATE,
    PORT_POLL_INTERVAL,
    READ_TIMEOUT,
    Bootrom,
    HandshakeTimeoutError,
    ProductId,
    UsbdlError,
    mediatek_ports,
)
from firebreak.plan import TABLE_SECTORS, Action, resolve
from firebreak.plugin import BOOT0, Write
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    PROGRESS,
    SESSION,
    ANSIColor,
    FatalError,
    Kind,
    again,
    asked_for,
    paint,
    show,
    status,
    title,
    warn,
)

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    import serial

    from firebreak.emmc import Emmc


BOOTROM_STEP_TIMEOUT = 30 * MINUTE
BOOTROM_WRITE_TIMEOUT = 30
LK_PRODUCT = re.compile(pattern=rb"\0product\0([A-Z0-9_]+)\0")
LK_PRODUCT_SECTORS = 1024
LK_SLOTS = ("lk_a", "lk_b")
OPEN_GRACE = 1
POKE_GONE_WAIT = 5
POKE_WRITE_TIMEOUT = 1
REPLUG_WAIT = 600
SHORT_WAIT = 5


def ask_for_short() -> None:
    warn(
        text=f"Short the {title()}'s test point and plug it in. The run waits for"
        " its bootrom, then says when the short may come off.",
    )
    status(text="Waiting for the bootrom.")


def await_amonet_fastboot() -> None:
    for _ in range(30):
        try:
            if (
                in_fastboot()
                and getvar(name="lk_build_desc") == biscuit.AMONET_V1_1_0_LK
            ):
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    raise FatalError(message=f"the {title()} did not come back in v1.1.0's fastboot")


def await_bootrom_port(
    *, deadline: float, erase: Callable[[], str] | None, preloaders: set[str]
) -> serial.Serial | None:
    failures: dict[str, float] = {}
    missed = 0
    while True:
        found = mediatek_ports()
        failures = {name: when for name, when in failures.items() if name in found}
        preloaders &= set(found)
        for name in sorted(found):
            if found[name] != ProductId.BOOTROM:
                continue
            port = open_bootrom(failures=failures, name=name)
            if port is not None:
                return port
        for name in sorted(found):
            if found[name] != ProductId.PRELOADER or name in preloaders:
                continue
            preloaders.add(name)
            if not erase and not SESSION.short:
                return None
            if SESSION.short:
                missed += 1
                say_missed_short(count=missed)
        if time.monotonic() >= deadline:
            raise FatalError(
                message=f"the {title()}'s bootrom did not show up as a serial port.\n"
                + no_port_help()
            )
        time.sleep(PORT_POLL_INTERVAL)


def await_port_gone(*, deadline: float, name: str) -> None:
    while name in mediatek_ports() and time.monotonic() < deadline:
        time.sleep(PORT_POLL_INTERVAL)


def bootloader_plan(*, amonet: pathlib.Path, live: Emmc) -> tuple[Action, ...]:
    check_emmc(live=live)
    unlock = biscuit.UNLOCK_FROM_BOOTROM
    try:
        raw = bootrom.read(count=TABLE_SECTORS, first=0, payload=live)
    except (OSError, UsbdlError) as error:
        raise FatalError(
            message=f"the {title()}'s partition table could not be read: {error}."
            f" {unwritten()} Unplug the {title()}. " + again()
        ) from error
    entries = raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE]
    if gpt_intact(entries=entries, header=raw[SECTOR_SIZE : 2 * SECTOR_SIZE]):
        check_bootloaders(entries=entries, live=live, want=unlock.device.product)
    try:
        resolved = resolve(raw=raw, source=amonet, unlock=unlock)
    except (FileNotFoundError, KeyError, ValueError) as error:
        raise FatalError(
            message=f"{unlock.name} does not fit this {title()}: {error.args[0]}."
            f" {unwritten()} " + again()
        ) from error
    kinds = [action.kind for action in resolved]
    if bootrom.REBOOT not in kinds:
        return resolved
    return resolved[: kinds.index(bootrom.REBOOT) + 1]


def bootrom_client(
    *, deadline: float, erase: Callable[[], str] | None
) -> Bootrom | None:
    overall = time.monotonic() + BOOTROM_STEP_TIMEOUT
    preloaders = {
        name
        for name, product in mediatek_ports().items()
        if product == ProductId.PRELOADER
    }
    while True:
        port = await_bootrom_port(deadline=deadline, erase=erase, preloaders=preloaders)
        if port is None:
            return None
        client = Bootrom(port=port)
        try:
            client.handshake()
        except (HandshakeTimeoutError, OSError) as error:
            with contextlib.suppress(OSError):
                client.port.close()
            if SESSION.short:
                raise FatalError(
                    message=f"the {title()}'s bootrom did not answer ({error})."
                    f" {unwritten()} Unplug the {title()}. " + again()
                ) from error
            PROGRESS.note(
                message=f"The {title()}'s bootrom did not answer ({error}). Unplug"
                f" the {title()} and plug it back in; the run goes on when its"
                " bootrom returns."
            )
            await_port_gone(deadline=overall, name=port.name)
            if time.monotonic() >= overall:
                raise FatalError(
                    message=f"the {title()}'s bootrom never answered a handshake."
                    f" {unwritten()} Unplug the {title()}. " + again()
                ) from error
            deadline = min(overall, time.monotonic() + REPLUG_WAIT)
        except UsbdlError as error:
            with contextlib.suppress(OSError):
                client.port.close()
            raise FatalError(
                message=f"the {title()}'s bootrom did not answer as one: {error}."
                f" {unwritten()} Unplug the {title()}. " + again()
            ) from error
        else:
            return client


def bootrom_step(
    *,
    amonet: pathlib.Path,
    erase: Callable[[], str] | None,
    payload: pathlib.Path,
    wheel: pathlib.Path | None,
) -> bool:
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
    if erase:
        ERASED.write_text(ARGUMENTS.target.device.name)
        failure = erase()
        if failure:
            raise FatalError(message=failure)
    elif SESSION.short:
        ask_for_short()
    else:
        poke_live_payload()
        PROGRESS.begin(estimate="40 s", label=f"waiting for the {title()} to restart")
    client = bootrom_client(
        deadline=time.monotonic() + (60 if erase else 600), erase=erase
    )
    if client is None:
        ERASED.unlink(missing_ok=True)
        PROGRESS.note(
            message=f"The {title()} started its preloader, so boot0 is intact and it"
            " needs no bootrom step."
        )
        return False
    live = exploit(client=client, payload=payload)
    actions = bootrom.check(actions=bootloader_plan(amonet=amonet, live=live))
    if PROGRESS.steps:
        PROGRESS.steps += len(actions) - 1
    ERASED.write_text(ARGUMENTS.target.device.name)
    bootrom.execute(actions=actions, payload=live)
    with contextlib.suppress(OSError):
        client.port.close()
    ERASED.unlink(missing_ok=True)
    await_amonet_fastboot()
    return True


def check_bootloaders(*, entries: bytes, live: Emmc, want: str) -> None:
    parts = partition_map(entries=entries)
    named: set[str] = set()
    for slot in LK_SLOTS:
        part = parts.get(slot)
        if part is None:
            raise FatalError(
                message=f"the {title()}'s partition table has no {slot}."
                f" {unwritten()} Unplug the {title()}. " + asked_for()
            )
        try:
            held = bootrom.read(
                count=min(part.sectors, LK_PRODUCT_SECTORS),
                first=part.first,
                payload=live,
            )
        except (OSError, UsbdlError) as error:
            raise FatalError(
                message=f"the {title()}'s {slot} could not be read: {error}."
                f" {unwritten()} Unplug the {title()}. " + again()
            ) from error
        named.update(found.decode() for found in LK_PRODUCT.findall(held))
    other = sorted(named - {want})
    if other:
        raise FatalError(
            message=f"the {title()}'s bootloader names its product {', '.join(other)},"
            f" not {want}, so it is not an Echo Dot (2nd Generation)."
            f" {unwritten()} Unplug it: firebreak's bootrom step supports only the"
            " Echo Dot (2nd Generation)."
        )
    if want not in named:
        raise FatalError(
            message="neither lk_a nor lk_b holds a bootloader that names its"
            " product, so this run cannot tell that this is an Echo Dot (2nd"
            f" Generation). {unwritten()} Unplug the {title()}. " + asked_for()
        )


def check_emmc(*, live: Emmc) -> None:
    try:
        live.switch_partition(partition=EmmcArea.USER)
        block = live.read_block(index=0)
    except (OSError, UsbdlError) as error:
        said = str(error)
    else:
        if bootrom.switched(block=block, partition=EmmcArea.USER):
            return
        wanted = bootrom.USER_AREA_SIGNATURE
        said = (
            f"block 0 of its user area ends {block[-len(wanted) :]!r}, not {wanted!r}"
        )
    raise FatalError(
        message=f"the {title()}'s eMMC did not answer{short_hint()}: {said}."
        f" {unwritten()} Unplug the {title()}. " + again()
    )


def countdown() -> None:
    text = "The bootrom answered. The short may come off now; continuing{}."
    if not sys.stdout.isatty():
        warn(text=text.format(f" in {SHORT_WAIT} s"))
        time.sleep(SHORT_WAIT)
        return
    for left in range(SHORT_WAIT, 0, -1):
        status(text=text.format(f" in {left} s"))
        time.sleep(1)
    status(text=text.format(""))
    print()


def exploit(*, client: Bootrom, payload: pathlib.Path) -> Client:
    data = payload.read_bytes()
    try:
        client.disable_watchdog()
        if SESSION.short:
            countdown()
        range_check.defeat(bootrom=client)
        live = start_payload(bootrom=client, client=Client, payload=data)
    except NotReadyError as error:
        raise FatalError(
            message=f"the payload did not start{short_hint()}: {error}."
            f" {unwritten()} Unplug the {title()}. " + again()
        ) from error
    except (OSError, UsbdlError) as error:
        raise FatalError(
            message=f"the exploit did not go through the {title()}'s bootrom: {error}."
            f" {unwritten()} Unplug the {title()}. " + again()
        ) from error
    return live


def keep_trying(*, message: str) -> None:
    said = message + ". The run keeps trying."
    if not SESSION.short:
        PROGRESS.note(message=said)
        return
    if sys.stdout.isatty():
        print()
    warn(text=said)
    status(text="Waiting for the bootrom.")


def open_bootrom(*, failures: dict[str, float], name: str) -> serial.Serial | None:
    try:
        return open_serial_port(name=name, write_timeout=BOOTROM_WRITE_TIMEOUT)
    except OSError as error:
        first = failures.setdefault(name, time.monotonic())
        if first and time.monotonic() - first >= OPEN_GRACE:
            failures[name] = 0
            keep_trying(message=f"Cannot open {name}: {error}")
        return None


def open_serial_port(*, name: str, write_timeout: float) -> serial.Serial:
    import serial  # ruff: ignore[import-outside-top-level]

    return serial.Serial(
        baudrate=BAUD_RATE,
        port=name,
        timeout=READ_TIMEOUT,
        write_timeout=write_timeout,
    )


def poke_live_payload() -> None:
    poked = []
    for name in sorted(mediatek_ports()):
        with (
            contextlib.suppress(OSError),
            open_serial_port(name=name, write_timeout=POKE_WRITE_TIMEOUT) as connection,
        ):
            Payload(port=connection).reboot()
            poked.append(name)
    deadline = time.monotonic() + POKE_GONE_WAIT
    for name in poked:
        await_port_gone(deadline=deadline, name=name)


def say_missed_short(*, count: int) -> None:
    if sys.stdout.isatty():
        print()
    show(
        kind=Kind.WARN,
        text=paint(
            code=ANSIColor.RED,
            text=f"Short {count} missed: the {title()} started normally. Unplug, short,"
            " and plug it in again.",
        ),
    )
    status(text="Waiting for the bootrom.")


def short_hint() -> str:
    return ", most likely because the short was still on" if SESSION.short else ""


def stock_preloader(
    *, build: str, payload: pathlib.Path, preloader: bytes, wheel: pathlib.Path | None
) -> None:
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
    PROGRESS.begin(estimate="10 s", label="waiting for the bootrom")
    client = bootrom_client(deadline=time.monotonic() + MINUTE, erase=None)
    if client is None:
        raise FatalError(
            message=f"the {title()} started a preloader, so boot0 was not clear and the"
            " RPMB was not zeroed. " + again()
        )
    live = exploit(client=client, payload=payload)
    check_emmc(live=live)
    PROGRESS.end()
    bootrom.execute(
        actions=(
            Action(expect=b"AMZN", kind=bootrom.ZERO_RPMB, label="zero the RPMB"),
            Action(
                data=preloader,
                kind=Write.__name__,
                label=f"write the {build} preloader to boot0",
                length=len(preloader),
                offset=0,
                target=BOOT0,
            ),
            Action(kind=bootrom.REBOOT, label=f"rebooting into stock {build}"),
        ),
        payload=live,
    )
    with contextlib.suppress(OSError):
        client.port.close()
    ERASED.unlink(missing_ok=True)


def unwritten() -> str:
    return "Only boot0 was erased." if ERASED.exists() else "Nothing was written."
