from __future__ import annotations

import contextlib
import enum
import sys
import time
from typing import TYPE_CHECKING

from firebreak import bootrom
from firebreak.amonet.payload import ACKNOWLEDGEMENT
from firebreak.android.gpt import (
    ENTRIES_SIZE,
    SECTOR_SIZE,
    gpt_intact,
    partition_map,
)
from firebreak.bootrom_step import (
    REPLUG_WAIT,
    answering_payload,
    bootrom_client,
    check_emmc,
    exploit,
)
from firebreak.mediatek.usbdl import UsbdlError
from firebreak.plan import TABLE_SECTORS
from firebreak.ui import FatalError, again, show, status, title
from firebreak.write_test import EMMC_TARGET, PATTERN

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from firebreak.amonet.biscuit_v2_0_0 import Client

KEPT = (
    "The payload still holds the Echo's bootrom, so the next run joins it rather"
    " than reaching the bootrom again."
)
LEFT = (
    "The Echo restarts. With a preloader in boot0 it starts as before; without"
    " one it waits in its bootrom, where `firebreak short` reaches it."
)
READS = 3
REGION_BLOCKS = 64
WRITE_SIZES = (1, TABLE_SECTORS, REGION_BLOCKS)


class Outcome(enum.Enum):
    FAILED = "failed"
    LOST = "lost"
    WRITTEN = "written"


def blocks(*, count: int) -> str:
    return f"{count} block" if count == 1 else f"{count} blocks"


def bootrom_write_test(
    *,
    line: Callable[[str, object], None],
    payload: pathlib.Path,
    wheel: pathlib.Path | None,
) -> None:
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
    live = answering_payload()
    joined = live is not None
    if live is None:
        status(text="Waiting for the bootrom, where a run left this Echo.")
        client, late = bootrom_client(
            deadline=time.monotonic() + REPLUG_WAIT, erase=None
        )
        if late is not None:
            live, joined = late, True
        elif client is None:
            raise FatalError(message=f"the {title()} started its preloader. " + again())
        else:
            live = exploit(client=client, payload=payload)
    check_emmc(live=live)
    try:
        synced = legs(line=line, live=live)
    except (OSError, UsbdlError) as error:
        raise FatalError(
            message=f"the test did not go through the bootrom: {error}. " + again()
        ) from error
    finally:
        if not joined:
            with contextlib.suppress(OSError, UsbdlError):
                live.reboot()
        with contextlib.suppress(OSError):
            live.port.close()
    if synced:
        show(text="\n" + (KEPT if joined else LEFT))


def legs(*, line: Callable[[str, object], None], live: Client) -> bool:
    first = region(line=line, live=live)
    if first is None:
        return True
    line("writing over", f"the last {blocks(count=REGION_BLOCKS)} of {EMMC_TARGET}")
    held = [
        bootrom.read(count=REGION_BLOCKS, first=first, payload=live)
        for _ in range(READS)
    ]
    if any(read != held[0] for read in held):
        line(
            "verdict",
            f"THE SAME {blocks(count=REGION_BLOCKS).upper()} READ BACK DIFFERENTLY"
            " over USB, so the cable, the port or this computer is at fault."
            " Nothing was written",
        )
        return True
    line("read over USB", f"{READS} reads of {blocks(count=REGION_BLOCKS)} agree")
    for count in WRITE_SIZES:
        data = pattern(count=count)
        outcome = wrote(count=count, data=data, first=first, line=line, live=live)
        if outcome == Outcome.LOST:
            return False
        if outcome == Outcome.FAILED:
            restore(first=first, held=held[0], line=line, live=live)
            return True
        if bootrom.read(count=count, first=first, payload=live) != data:
            line(
                "verdict",
                f"THE eMMC DID NOT GIVE BACK A WRITE OF"
                f" {blocks(count=count).upper()}. The payload took the write, so"
                " the card is at fault",
            )
            restore(first=first, held=held[0], line=line, live=live)
            return True
        line(f"write of {blocks(count=count)}", "read back unchanged")
    restore(first=first, held=held[0], line=line, live=live)
    sizes = ", ".join(map(str, WRITE_SIZES[:-1])) + f" and {WRITE_SIZES[-1]}"
    line(
        "verdict",
        f"the eMMC took writes of {sizes} blocks over USB and gave them back"
        " unchanged, so neither the card nor the cable is at fault",
    )
    return True


def pattern(*, count: int) -> bytes:
    size = count * SECTOR_SIZE
    return (bytes([count]) + PATTERN * (size // len(PATTERN) + 1))[:size]


def region(*, line: Callable[[str, object], None], live: Client) -> int | None:
    raw = bootrom.read(count=TABLE_SECTORS, first=0, payload=live)
    entries = raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE]
    if not gpt_intact(entries=entries, header=raw[SECTOR_SIZE : 2 * SECTOR_SIZE]):
        line("over the bootrom", "skipped: the partition table is not intact")
        return None
    part = partition_map(entries=entries).get(EMMC_TARGET)
    if part is None:
        line(
            "over the bootrom",
            f"skipped: this {title()} has no {EMMC_TARGET} partition",
        )
        return None
    if part.sectors < REGION_BLOCKS:
        line(
            "over the bootrom",
            f"skipped: {EMMC_TARGET} holds under {blocks(count=REGION_BLOCKS)}",
        )
        return None
    return part.first + part.sectors - REGION_BLOCKS


def restore(
    *, first: int, held: bytes, line: Callable[[str, object], None], live: Client
) -> None:
    try:
        live.write_blocks(data=held, index=first)
        back = bootrom.read(count=REGION_BLOCKS, first=first, payload=live)
    except UsbdlError as error:
        said = f"NO: {error}"
    else:
        said = "yes" if back == held else "NO: they did not read back as they were"
    line(f"{EMMC_TARGET}'s blocks put back", said)


def wrote(
    *,
    count: int,
    data: bytes,
    first: int,
    line: Callable[[str, object], None],
    live: Client,
) -> Outcome:
    try:
        live.write_blocks(data=data, index=first)
    except UsbdlError as error:
        line(f"write of {blocks(count=count)}", str(error))
    else:
        return Outcome.WRITTEN
    try:
        answer = live.ping()
    except UsbdlError:
        line(
            "verdict",
            f"THE PAYLOAD STOPPED ANSWERING after a write of {blocks(count=count)}."
            " Either the bytes did not all cross USB, or the card never finished"
            f" the write. Unplug the {title()}, then try another cable, port or"
            " computer: if this repeats, the card is at fault",
        )
        return Outcome.LOST
    if answer != ACKNOWLEDGEMENT:
        line(
            "verdict",
            f"THE eMMC REFUSED A WRITE OF {blocks(count=count).upper()}. The"
            " payload took the bytes and answered the next command, so they"
            " crossed USB and the card is at fault",
        )
        return Outcome.FAILED
    try:
        live.read_exactly(label="ping", length=len(ACKNOWLEDGEMENT))
    except UsbdlError:
        line(
            "verdict",
            f"BYTES OF A WRITE OF {blocks(count=count).upper()} DID NOT CROSS"
            " USB: the payload took the next command as the rest of the write, so"
            f" the cable, the port or this computer is at fault. Unplug the {title()}",
        )
        return Outcome.LOST
    line(
        "verdict",
        f"the eMMC took a write of {blocks(count=count)}, but answered after the"
        f" {live.timeout} second timeout. A slow card is failing",
    )
    return Outcome.FAILED
