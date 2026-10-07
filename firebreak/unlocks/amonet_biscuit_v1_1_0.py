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
from firebreak.cache import Download
from firebreak.devices import BISCUIT
from firebreak.plan import Action
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    FastbootFlash,
    Feature,
    ForceFastboot,
    Reboot,
    ResetBcb,
    Unlock,
    Write,
    ZeroRpmb,
)

if TYPE_CHECKING:
    from firebreak.android.gpt import Table

BOOT_SECTORS = 0x37000
FLASH_RECOVERY = FastbootFlash(
    image="bin/twrp.img", label="write TWRP", target="recovery"
)
PAYLOAD_SEEK = 223207
SHUFFLE_ALIGN = 0x400
SOURCE = Download(
    directory="v1",
    name="amonet-biscuit-v1.1.0.zip",
    sha256="bd4d3a18b6b6e9ff6e49a4739159a81020673202795cb3959f7c9ff24351b663",
    url="https://github.com/hkfuertes/amazon_device_biscuit/releases/download/none"
    "/amonet-biscuit-v1.1.0.zip",
)
USERDATA = "userdata"
WIPE_SECTORS = 10


@dataclasses.dataclass(frozen=True)
class ShuffleGpt:
    align: int
    sectors: int
    targets: tuple[str, ...]
    label: str = "make room in the partition table"

    def resolved(self, *, raw: bytes) -> tuple[bytes, tuple[Action, ...]]:
        kind = type(self).__name__
        partitions = partition_map(entries=raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE])
        if all(f"{target}_x" in partitions for target in self.targets):
            return raw, (
                Action(
                    kind=kind, label="the partition table already has room", length=0
                ),
            )
        table = shuffled_gpt(
            align=self.align,
            identifiers={target: uuid.uuid4().bytes_le for target in self.targets},
            raw=raw,
            sectors=self.sectors,
        )
        userdata = table.partitions[USERDATA]
        return table.primary, (
            Action(
                data=table.primary,
                kind=kind,
                label=self.label,
                length=len(table.primary),
                offset=0,
                source="the primary partition table",
                target="disk",
            ),
            Action(
                data=table.backup,
                kind=kind,
                label=self.label,
                length=len(table.backup),
                offset=table.backup_sector * SECTOR_SIZE,
                source="the backup partition table",
                target="disk",
            ),
            Action(
                data=bytes(WIPE_SECTORS * SECTOR_SIZE),
                kind=kind,
                label=f"wipe {USERDATA}'s first blocks",
                length=WIPE_SECTORS * SECTOR_SIZE,
                offset=userdata.first * SECTOR_SIZE,
                partition=userdata,
                source="zeros",
                target=USERDATA,
            ),
        )


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


AMONET_BISCUIT_V1_1_0 = Unlock(
    device=BISCUIT,
    family="amonet",
    plan=(
        ClearBoot0Header(),
        ShuffleGpt(
            align=SHUFFLE_ALIGN, sectors=BOOT_SECTORS, targets=("boot_a", "boot_b")
        ),
        ZeroRpmb(expect=b"AMZN"),
        Write(image="bin/boot.hdr", label="inject boot_a", target="boot_a"),
        Write(
            image="bin/boot.payload",
            label="inject boot_a",
            sector_offset=PAYLOAD_SEEK,
            target="boot_a",
        ),
        Write(image="bin/boot.hdr", label="inject boot_b", target="boot_b"),
        Write(
            image="bin/boot.payload",
            label="inject boot_b",
            sector_offset=PAYLOAD_SEEK,
            target="boot_b",
        ),
        Write(image="bin/tz.img", label="write the TEE", target="tee1"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_a"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_b"),
        ForceFastboot(target="expdb"),
        ResetBcb(target="misc"),
        Write(
            image="bin/preloader.img",
            label="write the preloader",
            target=BOOT0,
            unrecoverable=True,
        ),
        Reboot(),
        FastbootFlash(image="bin/tz.img", label="write the TEE", target="tee2"),
        FLASH_RECOVERY,
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=SOURCE,
    version="1.1.0",
)
