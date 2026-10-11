from __future__ import annotations

import dataclasses
import struct
import uuid
from typing import TYPE_CHECKING

from firebreak.android.gpt import (
    ENTRIES_SIZE,
    SECTOR_SIZE,
    entry_name,
    gpt_intact,
    partition_map,
    rebuilt_gpt,
    used_entries,
)
from firebreak.plan import Action
from firebreak.plugin import Repartition

if TYPE_CHECKING:
    from firebreak.android.gpt import Table

KIND = Repartition.__name__
USERDATA = "userdata"
WIPE_SECTORS = 10


@dataclasses.dataclass(frozen=True)
class BootMovedLayout:
    align: int
    sectors: int
    targets: tuple[str, ...]

    def apply(self, *, raw: bytes) -> tuple[bytes, tuple[Action, ...]]:
        table = shuffled_gpt(
            align=self.align,
            identifiers={
                target: uuid.uuid5(
                    name=target,
                    namespace=uuid.UUID(
                        bytes_le=raw[SECTOR_SIZE + 56 : SECTOR_SIZE + 72]
                    ),
                ).bytes_le
                for target in self.targets
            },
            raw=raw,
            sectors=self.sectors,
        )
        userdata = table.partitions[USERDATA]
        return table.primary, (
            *table_writes(label="make room in the partition table", table=table),
            Action(
                data=bytes(WIPE_SECTORS * SECTOR_SIZE),
                kind=KIND,
                label=f"wipe {USERDATA}'s first blocks",
                length=WIPE_SECTORS * SECTOR_SIZE,
                offset=userdata.first * SECTOR_SIZE,
                partition=userdata,
                source="zeros",
                target=USERDATA,
            ),
        )

    def describes(self, *, raw: bytes) -> bool:
        partitions = partition_map(entries=raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE])
        moved = [target for target in self.targets if f"{target}_x" in partitions]
        missing = [target for target in self.targets if target not in moved]
        if moved and missing:
            message = (
                f"the partition table has {', '.join(f'{name}_x' for name in moved)}"
                f" but not {', '.join(f'{name}_x' for name in missing)}"
            )
            raise ValueError(message)
        return bool(moved)

    def revert(self, *, raw: bytes) -> tuple[bytes, tuple[Action, ...]]:
        table = unshuffled_gpt(raw=raw, targets=self.targets)
        return table.primary, table_writes(
            label="restore the stock partition table", table=table
        )


@dataclasses.dataclass(frozen=True)
class StockLayout:
    partitions: int

    @staticmethod
    def apply(*, raw: bytes) -> tuple[bytes, tuple[Action, ...]]:
        return raw, ()

    @staticmethod
    def revert(*, raw: bytes) -> tuple[bytes, tuple[Action, ...]]:
        return raw, ()

    def describes(self, *, raw: bytes) -> bool:
        entries = raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE]
        return len(used_entries(entries=entries)) == self.partitions


def renamed(*, entry: bytes, name: str) -> bytes:
    return entry[:56] + name.encode(encoding="utf-16le").ljust(72, b"\0")


def shuffled_gpt(
    *, align: int, identifiers: dict[str, bytes], raw: bytes, sectors: int
) -> Table:
    template = raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    entries = raw[2 * SECTOR_SIZE : 2 * SECTOR_SIZE + ENTRIES_SIZE]
    if not gpt_intact(entries=entries, header=template):
        message = "the Dot's primary partition table is not intact"
        raise ValueError(message)
    used = used_entries(entries=entries)
    names = [entry_name(entry=entry) for entry in used]
    if names[-1] != USERDATA:
        message = f"the last partition is {names[-1]}, not {USERDATA}"
        raise ValueError(message)
    for name in identifiers:
        if name not in names:
            message = f"the partition table has no {name}"
            raise ValueError(message)
        if f"{name}_x" in names:
            message = f"the partition table already has {name}_x"
            raise ValueError(message)
    userdata = bytearray(used[-1])
    first, last = struct.unpack("<QQ", userdata[32:48])
    shrunk = last // align * align - sectors * len(identifiers) - 1
    if shrunk <= first:
        message = f"{USERDATA} cannot give up room for {', '.join(identifiers)}"
        raise ValueError(message)
    userdata[40:48] = struct.pack("<Q", shrunk)
    shuffled = [
        renamed(entry=entry, name=f"{name}_x") if name in identifiers else entry
        for entry, name in zip(used[:-1], names)
    ]
    shuffled.append(bytes(userdata))
    start = shrunk + 1
    for name, identifier in identifiers.items():
        added = bytearray(userdata)
        added[16:48] = identifier + struct.pack("<QQ", start, start + sectors - 1)
        shuffled.append(renamed(entry=added, name=name))
        start += sectors
    return rebuilt_gpt(entries=b"".join(shuffled).ljust(ENTRIES_SIZE, b"\0"), raw=raw)


def table_writes(*, label: str, table: Table) -> tuple[Action, Action]:
    return (
        Action(
            data=table.primary,
            kind=KIND,
            label=label,
            length=len(table.primary),
            offset=0,
            source="the primary partition table",
            target="disk",
        ),
        Action(
            data=table.backup,
            kind=KIND,
            label=label,
            length=len(table.backup),
            offset=table.backup_sector * SECTOR_SIZE,
            source="the backup partition table",
            target="disk",
        ),
    )


def unshuffled_gpt(*, raw: bytes, targets: tuple[str, ...]) -> Table:
    template = raw[SECTOR_SIZE : 2 * SECTOR_SIZE]
    entries = raw[2 * SECTOR_SIZE : 2 * SECTOR_SIZE + ENTRIES_SIZE]
    if not gpt_intact(entries=entries, header=template):
        message = "the Dot's primary partition table is not intact"
        raise ValueError(message)
    used = used_entries(entries=entries)
    names = [entry_name(entry=entry) for entry in used]
    kept = len(used) - len(targets) - 1
    if names[kept:] != [USERDATA, *targets]:
        message = (
            f"the last partitions are {', '.join(names[max(kept, 0) :])},"
            f" not {', '.join((USERDATA, *targets))}"
        )
        raise ValueError(message)
    for target in targets:
        if f"{target}_x" not in names:
            message = f"the partition table has no {target}_x"
            raise ValueError(message)
    userdata = bytearray(used[kept])
    userdata[40:48] = template[48:56]
    restored = [
        renamed(entry=entry, name=name[: -len("_x")])
        if name in {f"{target}_x" for target in targets}
        else entry
        for entry, name in zip(used[:kept], names)
    ]
    restored.append(bytes(userdata))
    return rebuilt_gpt(entries=b"".join(restored).ljust(ENTRIES_SIZE, b"\0"), raw=raw)
