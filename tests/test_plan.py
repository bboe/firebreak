from __future__ import annotations

import struct
import uuid
from typing import TYPE_CHECKING

import pytest

from firebreak import plan
from firebreak.android import gpt
from firebreak.devices import BISCUIT
from firebreak.plugin import BOOT0, Device, ResetBcb, Unlock, Write
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import AMONET_BISCUIT_V1_1_0_BBOE

if TYPE_CHECKING:
    import pathlib

BACKUP_ADDRESS = 7651327
BISCUIT_SHUFFLED = (
    ("kb", 2048, 4095),
    ("dkb", 4096, 6143),
    ("lk_a", 32768, 34815),
    ("tee1", 49152, 59391),
    ("lk_b", 65536, 67583),
    ("tee2", 81920, 92159),
    ("expdb", 98304, 118783),
    ("misc", 118784, 119808),
    ("persist", 131072, 163839),
    ("boot_a_x", 163840, 196607),
    ("boot_b_x", 196608, 229375),
    ("recovery", 229376, 262143),
    ("system_a", 294912, 1867775),
    ("system_b", 1867776, 3440639),
    ("cache", 3440640, 5046271),
    ("userdata", 5046272, 7199743),
    ("boot_a", 7199744, 7425023),
    ("boot_b", 7425024, 7650303),
)
BISCUIT_STOCK = (
    ("kb", 2048, 4095),
    ("dkb", 4096, 6143),
    ("lk_a", 32768, 34815),
    ("tee1", 49152, 59391),
    ("lk_b", 65536, 67583),
    ("tee2", 81920, 92159),
    ("expdb", 98304, 118783),
    ("misc", 118784, 119808),
    ("persist", 131072, 163839),
    ("boot_a", 163840, 196607),
    ("boot_b", 196608, 229375),
    ("recovery", 229376, 262143),
    ("system_a", 294912, 1867775),
    ("system_b", 1867776, 3440639),
    ("cache", 3440640, 5046271),
    ("userdata", 5046272, 7651294),
)
IMAGES = {
    "boot.hdr": 96,
    "boot.payload": 13888,
    "lk.bin": 372736,
    "preloader.img": 1048576,
    "twrp.img": 9000000,
    "tz.img": 2641920,
}
SECTOR = 512
TWRP_SIZE = 13953024


@pytest.fixture
def source(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "amonet"
    (root / "bin").mkdir(parents=True)
    for name, size in IMAGES.items():
        (root / "bin" / name).write_bytes(name.encode().ljust(size, b"\0"))
    twrp = tmp_path / "twrp.img"
    twrp.write_bytes(b"T" * TWRP_SIZE)
    monkeypatch.setattr(name="fetch", target=plan, value=lambda **_: twrp)
    return root


def amonet_writes(*, recovery: int) -> list[tuple[str, str | None, int, int]]:
    boot_a, boot_b, payload = 7199744, 7425024, 223207
    return [
        ("ClearBoot0Header", BOOT0, 0, 4096),
        ("ShuffleGpt", "disk", 0, 17408),
        ("ShuffleGpt", "disk", (BACKUP_ADDRESS - 32) * SECTOR, 16896),
        ("ShuffleGpt", "userdata", 5046272 * SECTOR, 10 * SECTOR),
        ("ZeroRpmb", None, -1, -1),
        ("Write", "boot_a", boot_a * SECTOR, 512),
        ("Write", "boot_a", (boot_a + payload) * SECTOR, 14336),
        ("Write", "boot_b", boot_b * SECTOR, 512),
        ("Write", "boot_b", (boot_b + payload) * SECTOR, 14336),
        ("Write", "tee1", 49152 * SECTOR, 2641920),
        ("Write", "lk_a", 32768 * SECTOR, 372736),
        ("Write", "lk_b", 65536 * SECTOR, 372736),
        ("ForceFastboot", "expdb", 98304 * SECTOR, 16),
        ("ResetBcb", "misc", 118785 * SECTOR + 0x160, 7),
        ("Write", BOOT0, 0, 1048576),
        ("Reboot", None, -1, -1),
        ("FastbootFlash", "tee2", 81920 * SECTOR, 2641920),
        ("FastbootFlash", "recovery", 229376 * SECTOR, recovery),
        ("Reboot", "recovery", -1, -1),
    ]


def biscuit_table(*, layout: tuple[tuple[str, int, int], ...]) -> bytes:
    entries = b"".join(
        b"T" * 16
        + uuid.uuid5(uuid.NAMESPACE_OID, name).bytes_le
        + struct.pack("<QQ", first, last)
        + bytes(8)
        + name.encode(encoding="utf-16le").ljust(72, b"\0")
        for name, first, last in layout
    ).ljust(gpt.ENTRIES_SIZE, b"\0")
    template = bytearray(92)
    template[:16] = b"EFI PART" + b"\0\0\1\0" + struct.pack("<I", 92)
    template[24:56] = struct.pack("<QQQQ", 1, BACKUP_ADDRESS, 34, 7651294)
    template[56:72] = b"D" * 16
    template[80:88] = struct.pack("<II", 128, 128)
    return gpt.rebuilt_gpt(entries=entries, raw=b"M" * SECTOR + bytes(template)).primary


def described(*, actions: tuple[plan.Action, ...]) -> list[tuple]:
    return [
        (
            action.kind,
            action.target,
            -1 if action.offset is None else action.offset,
            -1 if action.length is None else action.length,
        )
        for action in actions
    ]


def reordered_overlaps(*, actions: tuple[plan.Action, ...]) -> list[tuple[str, str]]:
    def span(action: plan.Action) -> tuple[str, int, int]:
        first = action.offset // SECTOR
        end = -(-(action.offset + action.length) // SECTOR)
        return ("boot0" if action.target == BOOT0 else "disk", first, end)

    found = []
    writes = [action for action in actions if action.length]
    for index, unrecoverable in enumerate(writes):
        if not unrecoverable.unrecoverable:
            continue
        place, first, end = span(unrecoverable)
        for later in writes[index + 1 :]:
            other, later_first, later_end = span(later)
            if (
                not later.unrecoverable
                and other == place
                and later_first < end
                and first < later_end
            ):
                found.append((unrecoverable.label, later.label))
    return found


def test_a_device_without_a_needed_feature_is_refused(*, source: pathlib.Path) -> None:
    unlock = Unlock(
        device=Device(features=frozenset(), name="bare"),
        family="amonet",
        plan=(),
        requires=AMONET_BISCUIT_V1_1_0.requires,
        source=AMONET_BISCUIT_V1_1_0.source,
        version="1",
    )
    with pytest.raises(ValueError, match=r"amonet-bare-v1 needs \['ab-slots'"):
        plan.resolve(raw=b"", source=source, unlock=unlock)


def test_a_half_shuffled_table_is_refused(*, source: pathlib.Path) -> None:
    layout = tuple(
        ("boot_b", first, last) if name == "boot_b_x" else (name, first, last)
        for name, first, last in BISCUIT_SHUFFLED
        if name != "boot_b"
    )
    with pytest.raises(ValueError, match="the last partition is boot_a"):
        plan.resolve(
            raw=biscuit_table(layout=layout),
            source=source,
            unlock=AMONET_BISCUIT_V1_1_0,
        )


@pytest.mark.parametrize(
    argnames=("step", "error", "match"),
    argvalues=[
        (Write(image="bin/lk.bin", target="lk_c"), KeyError, "biscuit has no lk_c"),
        (ResetBcb(target="para"), KeyError, "biscuit has no para"),
        (Write(image="bin/none.img", target="lk_a"), FileNotFoundError, "none.img"),
        (Write(image="bin/tz.img", target="lk_a"), ValueError, "lk_a leaves 1048576"),
        (
            Write(image="bin/boot.payload", sector_offset=2048, target="lk_a"),
            ValueError,
            "after 2048 sectors",
        ),
    ],
)
def test_a_step_that_cannot_resolve(
    *, error: type[Exception], match: str, source: pathlib.Path, step: object
) -> None:
    unlock = Unlock(
        device=BISCUIT,
        family="amonet",
        plan=(step,),
        requires=frozenset(),
        source=AMONET_BISCUIT_V1_1_0.source,
        version="1",
    )
    with pytest.raises(error, match=match):
        plan.resolve(
            raw=biscuit_table(layout=BISCUIT_STOCK), source=source, unlock=unlock
        )


def test_a_table_that_is_not_intact_is_refused(*, source: pathlib.Path) -> None:
    raw = bytearray(biscuit_table(layout=BISCUIT_SHUFFLED))
    raw[2 * SECTOR + 40] ^= 1
    with pytest.raises(ValueError, match=r"^the partition table is not intact$"):
        plan.resolve(raw=bytes(raw), source=source, unlock=AMONET_BISCUIT_V1_1_0)


@pytest.mark.parametrize(
    argnames="unlock",
    argvalues=[AMONET_BISCUIT_V1_1_0, AMONET_BISCUIT_V1_1_0_BBOE],
    ids=lambda unlock: unlock.name,
)
@pytest.mark.parametrize(
    argnames="layout",
    argvalues=[BISCUIT_STOCK, BISCUIT_SHUFFLED],
    ids=["stock", "shuffled"],
)
def test_no_plan_yet_has_a_recoverable_write_over_an_earlier_unrecoverable_one(
    *,
    layout: tuple[tuple[str, int, int], ...],
    source: pathlib.Path,
    unlock: Unlock,
) -> None:
    actions = plan.resolve(
        raw=biscuit_table(layout=layout), source=source, unlock=unlock
    )
    assert reordered_overlaps(actions=actions) == []
    assert reordered_overlaps(
        actions=(
            plan.Action(
                kind="Write",
                label="preloader",
                length=1024,
                offset=0,
                target=BOOT0,
                unrecoverable=True,
            ),
            plan.Action(kind="Write", label="lk", length=512, offset=0, target="lk_a"),
            plan.Action(
                kind="Write", label="patch", length=7, offset=1000, target=BOOT0
            ),
        )
    ) == [("preloader", "patch")]


def test_show(*, source: pathlib.Path) -> None:
    actions = plan.resolve(
        raw=biscuit_table(layout=BISCUIT_STOCK),
        source=source,
        unlock=AMONET_BISCUIT_V1_1_0,
    )
    lines = plan.show(actions=actions).split(sep="\n")
    assert lines[0].startswith("  1. ClearBoot0Header")
    assert lines[1] == "     b'EMMC_BOOT' and zeros"
    assert any(line.endswith("<-- no way back") for line in lines)
    assert "lk_a @ 16,777,216" in plan.show(actions=actions)
    assert plan.show(actions=(plan.Action(kind="Reboot", label="reboot"),)) == (
        f"  1. {'Reboot':<17} {'reboot':<36} {'':<22} {'':>13}"
    )


def test_v1_1_0_bboe_from_stock_matches_amonet(*, source: pathlib.Path) -> None:
    actions = plan.resolve(
        raw=biscuit_table(layout=BISCUIT_STOCK),
        source=source,
        unlock=AMONET_BISCUIT_V1_1_0_BBOE,
    )
    assert described(actions=actions) == amonet_writes(recovery=TWRP_SIZE)
    assert [action.unrecoverable for action in actions].count(True) == 1
    assert actions[14].unrecoverable
    shuffled = gpt.partition_map(entries=actions[1].data[2 * SECTOR :])
    assert (shuffled["boot_a"].first, shuffled["boot_b"].first) == (7199744, 7425024)
    assert shuffled["userdata"].sectors == 7199743 - 5046272 + 1
    assert actions[2].data[16384:].startswith(b"EFI PART")
    assert actions[3].data == bytes(10 * SECTOR)
    assert actions[0].data == b"EMMC_BOOT".ljust(4096, b"\0")
    assert actions[12].data == b"FASTBOOT_PLEASE\0"
    assert actions[13].data == b"\0ABB\x01\x8f\0"
    assert actions[17].image == source.parent / "twrp.img"
    assert actions[5].image == source / "bin" / "boot.hdr"
    assert [action.partition.number for action in actions[5:9]] == [17, 17, 18, 18]
    assert actions[3].partition == gpt.Partition(
        first=5046272, number=16, sectors=7199743 - 5046272 + 1
    )
    assert actions[13].partition.number == 8
    assert actions[0].partition is actions[1].partition is actions[14].partition is None


def test_v1_1_0_from_a_shuffled_table_skips_the_shuffle(
    *, source: pathlib.Path
) -> None:
    stock = biscuit_table(layout=BISCUIT_STOCK)
    shuffled = plan.resolve(raw=stock, source=source, unlock=AMONET_BISCUIT_V1_1_0)[1]
    actions = plan.resolve(
        raw=shuffled.data, source=source, unlock=AMONET_BISCUIT_V1_1_0
    )
    want = amonet_writes(recovery=9000448)
    assert described(actions=actions) == [
        *want[:1],
        ("ShuffleGpt", None, -1, 0),
        *want[4:],
    ]
    assert actions[1].label == "the partition table already has room"
    assert actions[-2].image == source / "bin" / "twrp.img"


def test_v1_1_0_from_stock_matches_amonet(*, source: pathlib.Path) -> None:
    actions = plan.resolve(
        raw=biscuit_table(layout=BISCUIT_STOCK),
        source=source,
        unlock=AMONET_BISCUIT_V1_1_0,
    )
    assert described(actions=actions) == amonet_writes(recovery=9000448)
    assert actions[17].image == source / "bin" / "twrp.img"
