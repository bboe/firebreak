from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from firebreak.emmc import RPMB_SIZE, EmmcArea
from firebreak.mediatek.usbdl import UsbdlError
from firebreak.plan import BOOT0_HEADER, SECTOR_SIZE, whole_sectors
from firebreak.plugin import BOOT0, FastbootFlash, Reboot, ZeroRpmb
from firebreak.ui import PROGRESS, _die, again

if TYPE_CHECKING:
    from firebreak.emmc import Emmc
    from firebreak.plan import Action

REBOOT = Reboot.__name__
UNSUPPORTED_KINDS = frozenset({FastbootFlash.__name__})
USER_AREA_SIGNATURE = b"\x55\xaa"
ZERO_RPMB = ZeroRpmb.__name__


def check(*, actions: tuple[Action, ...]) -> tuple[Action, ...]:
    refused = sorted({
        action.kind for action in actions if action.kind in UNSUPPORTED_KINDS
    })
    if refused:
        _die(
            message=f"the bootrom cannot carry out {', '.join(refused)}. Nothing was"
            " written. " + again()
        )
    if any(action.kind == ZERO_RPMB and not action.expect for action in actions):
        _die(
            message=f"a {ZERO_RPMB} step that expects nothing would wipe the RPMB"
            " unchecked, and the wipe cannot be undone. Nothing was written. " + again()
        )
    return tuple(action for action in actions if action.length != 0)


def execute(*, actions: tuple[Action, ...], payload: Emmc) -> None:
    writes = check(actions=actions)
    for action in writes:
        PROGRESS.begin(label=action.label)
        try:
            PROGRESS.end(skipped=execute_one(action=action, payload=payload))
        except (OSError, UsbdlError) as error:
            _die(
                message=f"{action.kind} ({action.label}) did not go through the"
                f" bootrom: {error}. Do not unplug the Dot. " + again()
            )


def execute_one(*, action: Action, payload: Emmc) -> bool:
    if action.kind == ZERO_RPMB:
        zero_rpmb(action=action, payload=payload)
        return False
    if action.kind == REBOOT:
        payload.reboot()
        return False
    partition, offset = place(action=action)
    switch(partition=partition, payload=payload)
    first, data = whole_sectors(
        action=action, offset=offset, read=functools.partial(read, payload=payload)
    )
    if read(count=len(data) // SECTOR_SIZE, first=first, payload=payload) == data:
        return True
    write(data=data, first=first, partition=partition, payload=payload)
    return False


def place(*, action: Action) -> tuple[int, int]:
    partition = EmmcArea.BOOT0 if action.target == BOOT0 else EmmcArea.USER
    return partition, action.offset


def read(*, count: int, first: int, payload: Emmc) -> bytes:
    return b"".join(
        payload.read_blocks(
            count=min(payload.maximum_blocks, count - index), index=first + index
        )
        for index in range(0, count, payload.maximum_blocks)
    )


def switch(*, partition: int, payload: Emmc) -> None:
    payload.switch_partition(partition=partition)
    block = payload.read_block(index=0)
    if not switched(block=block, partition=partition):
        _die(
            message=f"area {partition} does not read as itself after the switch: its"
            f" block 0 starts {block[: len(BOOT0_HEADER)]!r} and ends"
            f" {block[-len(USER_AREA_SIGNATURE) :]!r}. Do not unplug the Dot. "
            + again()
        )


def switched(*, block: bytes, partition: int) -> bool:
    if partition == EmmcArea.BOOT0:
        return block.startswith(BOOT0_HEADER) or not any(block)
    return block.endswith(USER_AREA_SIGNATURE)


def write(*, data: bytes, first: int, partition: int, payload: Emmc) -> None:
    count = len(data) // SECTOR_SIZE
    for index in range(0, count, payload.maximum_blocks):
        payload.write_blocks(
            data=data[
                index * SECTOR_SIZE : (index + payload.maximum_blocks) * SECTOR_SIZE
            ],
            index=first + index,
        )
    if read(count=count, first=first, payload=payload) != data:
        _die(
            message=f"{len(data)} bytes at block {first} of area {partition} did"
            " not read back. Do not unplug the Dot. " + again()
        )


def zero_rpmb(*, action: Action, payload: Emmc) -> None:
    found = payload.read_rpmb()
    if not found.startswith(action.expect):
        reading = (
            " It is already zeroed, which is what a second run of an interrupted"
            " plan sees."
            if not any(found)
            else ""
        )
        PROGRESS.note(
            message=f"the RPMB starts {found[: len(action.expect)]!r}, not"
            f" {action.expect!r}. Zeroing it anyway.{reading}"
        )
    payload.write_rpmb(data=bytes(RPMB_SIZE))
    found = payload.read_rpmb()
    if found != bytes(RPMB_SIZE):
        _die(
            message=f"the RPMB still holds {found!r} after being zeroed. Do not"
            " unplug the Dot. " + again()
        )
