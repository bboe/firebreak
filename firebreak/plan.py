from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from firebreak.android.gpt import (
    ENTRIES_SIZE,
    gpt_intact,
    partition_map,
)
from firebreak.cache import fetch
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    FastbootFlash,
    ForceFastboot,
    ResetBcb,
    TableStep,
    Write,
    ZeroRpmb,
)

if TYPE_CHECKING:
    import pathlib

    from firebreak.android.gpt import Partition
    from firebreak.plugin import Step, Unlock

BOOT0_HEADER = b"EMMC_BOOT"
BOOT0_HEADER_BLOCKS = 8
BOOTLOADER_CONTROL_BLOCK = b"\0ABB\x01\x8f\0"
BOOTLOADER_CONTROL_BLOCK_OFFSET = 0x360
FASTBOOT_PLEASE = b"FASTBOOT_PLEASE\0"
SECTOR_SIZE = 512
TABLE_SECTORS = 34


@dataclasses.dataclass(frozen=True)
class Action:
    kind: str
    label: str
    data: bytes | None = None
    image: pathlib.Path | None = None
    length: int | None = None
    offset: int | None = None
    partition: Partition | None = None
    source: str | None = None
    target: str | None = None
    unrecoverable: bool = False


def action(
    *,
    partitions: dict[str, Partition],
    source: pathlib.Path,
    step: Step,
    unlock: Unlock,
) -> Action:
    kind = type(step).__name__
    if isinstance(step, Write):
        return written(partitions=partitions, source=source, step=step, unlock=unlock)
    if isinstance(step, FastbootFlash):
        flashed = Write(image=step.image, label=step.label, target=step.target)
        return dataclasses.replace(
            written(partitions=partitions, source=source, step=flashed, unlock=unlock),
            kind=kind,
        )
    if isinstance(step, (ForceFastboot, ResetBcb)):
        return patched(partitions=partitions, step=step, unlock=unlock)
    if isinstance(step, ClearBoot0Header):
        return Action(
            data=BOOT0_HEADER.ljust(BOOT0_HEADER_BLOCKS * SECTOR_SIZE, b"\0"),
            kind=kind,
            label=step.label,
            length=BOOT0_HEADER_BLOCKS * SECTOR_SIZE,
            offset=0,
            source=repr(BOOT0_HEADER) + " and zeros",
            target=BOOT0,
        )
    if isinstance(step, ZeroRpmb):
        return Action(kind=kind, label=step.label, source=repr(step.expect))
    return Action(kind=kind, label=step.label, target=step.into)


def image_of(*, image: str, source: pathlib.Path, unlock: Unlock) -> pathlib.Path:
    pinned = unlock.files.get(image)
    path = fetch(download=pinned) if pinned else source / image
    if not path.is_file():
        message = f"{image} is not in {source.name}"
        raise FileNotFoundError(message)
    return path


def patched(
    *,
    partitions: dict[str, Partition],
    step: ForceFastboot | ResetBcb,
    unlock: Unlock,
) -> Action:
    partition = partitions.get(step.target)
    if partition is None:
        message = f"{unlock.device.name} has no {step.target} partition"
        raise KeyError(message)
    if isinstance(step, ForceFastboot):
        data, offset = FASTBOOT_PLEASE, 0
    else:
        data, offset = BOOTLOADER_CONTROL_BLOCK, BOOTLOADER_CONTROL_BLOCK_OFFSET
    return Action(
        data=data,
        kind=type(step).__name__,
        label=step.label,
        length=len(data),
        offset=partition.first * SECTOR_SIZE + offset,
        partition=partition,
        source=repr(data),
        target=step.target,
    )


def resolve(*, raw: bytes, source: pathlib.Path, unlock: Unlock) -> tuple[Action, ...]:
    unmet = unlock.unmet()
    if unmet:
        message = f"{unlock.name} needs {sorted(feature.value for feature in unmet)}"
        raise ValueError(message)
    if not gpt_intact(
        entries=raw[2 * SECTOR_SIZE :], header=raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    ):
        message = "the partition table is not intact"
        raise ValueError(message)
    actions = []
    for step in unlock.plan:
        if isinstance(step, TableStep):
            raw, made = step.resolved(raw=raw)
            actions.extend(made)
        else:
            partitions = partition_map(entries=raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE])
            actions.append(
                action(partitions=partitions, source=source, step=step, unlock=unlock)
            )
    return tuple(actions)


def sector_padded(*, length: int) -> int:
    return length + -length % SECTOR_SIZE


def show(*, actions: tuple[Action, ...]) -> str:
    lines = []
    for index, action in enumerate(iterable=actions, start=1):
        where = ""
        if action.target is not None:
            where = action.target
            if action.offset is not None:
                where += f" @ {action.offset:,}"
        size = f"{action.length:,} B" if action.length is not None else ""
        mark = "  <-- no way back" if action.unrecoverable else ""
        lines.append(
            f"{index:>3}. {action.kind:<17} {action.label:<36}"
            f" {where:<22} {size:>13}{mark}"
        )
        if action.source and action.kind != "Write":
            lines.append(f"     {action.source}")
    return "\n".join(lines)


def written(
    *,
    partitions: dict[str, Partition],
    source: pathlib.Path,
    step: Write,
    unlock: Unlock,
) -> Action:
    path = image_of(image=step.image, source=source, unlock=unlock)
    length = sector_padded(length=path.stat().st_size)
    if step.target == BOOT0:
        offset, partition, room = step.sector_offset * SECTOR_SIZE, None, None
    else:
        partition = partitions.get(step.target)
        if partition is None:
            message = f"{unlock.device.name} has no {step.target} partition"
            raise KeyError(message)
        offset = (partition.first + step.sector_offset) * SECTOR_SIZE
        room = (partition.sectors - step.sector_offset) * SECTOR_SIZE
    if room is not None and length > room:
        message = (
            f"{step.image} is {length} bytes and {step.target} leaves"
            f" {room} after {step.sector_offset} sectors"
        )
        raise ValueError(message)
    return Action(
        image=path,
        kind=type(step).__name__,
        label=step.label,
        length=length,
        offset=offset,
        partition=partition,
        source=step.image,
        target=step.target,
        unrecoverable=step.unrecoverable,
    )
