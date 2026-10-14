from __future__ import annotations

import pathlib
import struct
import types

import pytest

from firebreak import bootrom_write_test
from firebreak.amonet.payload import ACKNOWLEDGEMENT
from firebreak.android import gpt
from firebreak.mediatek.usbdl import ProtocolMismatchError
from firebreak.ui import FatalError

CACHE_FIRST = 100
CACHE_SECTORS = 200
FAILING = {"eaten", "late", "refuse", "stuck"}
REGION = CACHE_FIRST + CACHE_SECTORS - bootrom_write_test.REGION_BLOCKS


class Emmc:
    maximum_blocks = 64
    timeout = 5

    def __init__(
        self, *, cache: int = CACHE_SECTORS, mode: str = "", name: str = "cache"
    ) -> None:
        self.blocks: dict[int, bytes] = {}
        self.flaky = False
        self.mode = mode
        self.rebooted = False
        self.writes: list[int] = []
        table = cache_table(name=name, sectors=cache)
        for index in range(len(table) // gpt.SECTOR_SIZE):
            self.blocks[index] = table[
                index * gpt.SECTOR_SIZE : (index + 1) * gpt.SECTOR_SIZE
            ]

    def ping(self) -> bytes:
        if self.mode == "stuck":
            message = "ping: read 0 of 4 bytes"
            raise ProtocolMismatchError(message)
        return ACKNOWLEDGEMENT if self.mode in {"eaten", "late"} else b"\0\0\0\xea"

    def read_blocks(self, *, count: int, index: int) -> bytes:
        held = b"".join(
            self.blocks.get(block, bytes([block % 256]) * gpt.SECTOR_SIZE)
            for block in range(index, index + count)
        )
        if self.flaky and index == REGION:
            self.flaky = False
            return b"x" + held[1:]
        return held

    def read_exactly(self, *, label: str, length: int) -> bytes:
        if self.mode == "eaten":
            message = f"{label}: read 0 of {length} bytes"
            raise ProtocolMismatchError(message)
        return b"\0\0\0\xea"

    def reboot(self) -> None:
        self.rebooted = True

    def write_blocks(self, *, data: bytes, index: int) -> None:
        count = len(data) // gpt.SECTOR_SIZE
        self.writes.append(count)
        if self.mode in FAILING and count == bootrom_write_test.TABLE_SECTORS:
            message = f"write of {count} blocks at {index}: read 0 of 4 bytes"
            raise ProtocolMismatchError(message)
        if self.mode == "lose" and count > 1:
            data = bytes(len(data))
        for offset in range(count):
            self.blocks[index + offset] = data[
                offset * gpt.SECTOR_SIZE : (offset + 1) * gpt.SECTOR_SIZE
            ]


@pytest.fixture
def stubbed(*, monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    rig = types.SimpleNamespace(
        client=types.SimpleNamespace(port=types.SimpleNamespace(close=lambda: None)),
        emmc=Emmc(),
        said={},
        shown=[],
    )
    monkeypatch.setattr(
        name="ask_for_short", target=bootrom_write_test, value=lambda: None
    )
    monkeypatch.setattr(
        name="bootrom_client", target=bootrom_write_test, value=lambda **_: rig.client
    )
    monkeypatch.setattr(
        name="check_emmc", target=bootrom_write_test, value=lambda **_: None
    )
    monkeypatch.setattr(
        name="exploit", target=bootrom_write_test, value=lambda **_: rig.emmc
    )
    monkeypatch.setattr(
        name="show",
        target=bootrom_write_test,
        value=lambda **said: rig.shown.append(said["text"]),
    )
    return rig


def cache_table(*, name: str, sectors: int) -> bytes:
    entries = (
        b"T" * 16
        + b"U" * 16
        + struct.pack("<QQ", CACHE_FIRST, CACHE_FIRST + sectors - 1)
        + bytes(8)
        + name.encode(encoding="utf-16le").ljust(72, b"\0")
    ).ljust(gpt.ENTRIES_SIZE, b"\0")
    header = bytearray(92)
    header[:16] = b"EFI PART" + b"\0\0\1\0" + struct.pack("<I", 92)
    header[24:56] = struct.pack("<QQQQ", 1, 1000033, 34, 1000000)
    header[80:88] = struct.pack("<II", 128, 128)
    return gpt.rebuilt_gpt(entries=entries, raw=b"M" * 512 + bytes(header)).primary


def run_legs(*, emmc: Emmc) -> tuple[bool, dict[str, list[object]]]:
    said: dict[str, list[object]] = {}
    synced = bootrom_write_test.legs(
        line=lambda label, value: said.setdefault(label, []).append(value),
        live=emmc,
    )
    return synced, said


def test_a_cache_under_64_blocks_is_skipped() -> None:
    emmc = Emmc(cache=10)
    assert run_legs(emmc=emmc) == (
        True,
        {"over the bootrom": ["skipped: cache holds under 64 blocks"]},
    )
    assert emmc.writes == []


def test_a_card_that_loses_a_write_is_blamed() -> None:
    emmc = Emmc(mode="lose")
    held = emmc.read_blocks(count=64, index=REGION)
    synced, said = run_legs(emmc=emmc)
    assert synced
    assert said["write of 1 block"] == ["read back unchanged"]
    assert "DID NOT GIVE BACK A WRITE OF 34 BLOCKS" in str(said["verdict"])
    assert said["cache's blocks put back"] == [
        "NO: they did not read back as they were"
    ]
    assert emmc.read_blocks(count=64, index=REGION) != held


def test_a_dot_that_starts_its_preloader_stops_the_test(
    *, monkeypatch: pytest.MonkeyPatch, stubbed: types.SimpleNamespace
) -> None:
    monkeypatch.setattr(
        name="bootrom_client", target=bootrom_write_test, value=lambda **_: None
    )
    with pytest.raises(FatalError, match="started its preloader"):
        write_test(rig=stubbed)


def test_a_dot_with_no_cache_is_skipped() -> None:
    emmc = Emmc(name="userdata")
    assert run_legs(emmc=emmc) == (
        True,
        {"over the bootrom": ["skipped: this Dot has no cache partition"]},
    )
    assert emmc.writes == []


def test_a_failed_read_stops_the_test_and_reboots(
    *, monkeypatch: pytest.MonkeyPatch, stubbed: types.SimpleNamespace
) -> None:
    def broken(**_: object) -> bytes:
        message = "table: read 0 of 512 bytes"
        raise ProtocolMismatchError(message)

    monkeypatch.setattr(name="read_blocks", target=stubbed.emmc, value=broken)
    with pytest.raises(FatalError, match="did not go through the bootrom: table"):
        write_test(rig=stubbed)
    assert stubbed.emmc.rebooted
    assert stubbed.shown == []


def test_a_late_answer_names_a_slow_card_and_puts_cache_back() -> None:
    emmc = Emmc(mode="late")
    held = emmc.read_blocks(count=64, index=REGION)
    synced, said = run_legs(emmc=emmc)
    assert synced
    assert "answered after the 5 second timeout" in str(said["verdict"])
    assert said["cache's blocks put back"] == ["yes"]
    assert emmc.read_blocks(count=64, index=REGION) == held


def test_a_lost_payload_does_not_say_the_dot_restarts(
    *, stubbed: types.SimpleNamespace
) -> None:
    stubbed.emmc.mode = "stuck"
    write_test(rig=stubbed)
    assert stubbed.shown == []


def test_a_ping_taken_as_write_data_blames_usb() -> None:
    synced, said = run_legs(emmc=Emmc(mode="eaten"))
    assert not synced
    assert "BYTES OF A WRITE OF 34 BLOCKS DID NOT CROSS USB" in str(said["verdict"])
    assert "cache's blocks put back" not in said


def test_a_refused_write_blames_the_card_and_puts_cache_back() -> None:
    emmc = Emmc(mode="refuse")
    synced, said = run_legs(emmc=emmc)
    assert synced
    assert said["write of 34 blocks"] == [
        f"write of 34 blocks at {REGION}: read 0 of 4 bytes"
    ]
    assert "REFUSED A WRITE OF 34 BLOCKS" in str(said["verdict"])
    assert said["cache's blocks put back"] == ["yes"]
    assert emmc.writes == [1, 34, 64]


def test_a_restore_with_no_answer_says_so() -> None:
    emmc = Emmc(mode="stuck")
    said: list[object] = []
    bootrom_write_test.restore(
        first=REGION,
        held=bytes(34 * gpt.SECTOR_SIZE),
        line=lambda _, value: said.append(value),
        live=emmc,
    )
    assert said == [f"NO: write of 34 blocks at {REGION}: read 0 of 4 bytes"]


def test_a_silent_payload_says_to_unplug() -> None:
    synced, said = run_legs(emmc=Emmc(mode="stuck"))
    assert not synced
    assert "STOPPED ANSWERING after a write of 34 blocks" in str(said["verdict"])
    assert "Unplug the Dot" in str(said["verdict"])


def test_a_table_that_is_not_intact_is_skipped() -> None:
    emmc = Emmc()
    emmc.blocks[1] = b"X" + emmc.blocks[1][1:]
    assert run_legs(emmc=emmc) == (
        True,
        {"over the bootrom": ["skipped: the partition table is not intact"]},
    )
    assert emmc.writes == []


def test_reads_that_disagree_blame_usb_and_write_nothing() -> None:
    emmc = Emmc()
    emmc.flaky = True
    _, said = run_legs(emmc=emmc)
    assert "READ BACK DIFFERENTLY" in str(said["verdict"])
    assert emmc.writes == []


def test_the_pattern_differs_per_size_and_is_not_zeros() -> None:
    patterns = {
        count: bootrom_write_test.pattern(count=count)
        for count in bootrom_write_test.WRITE_SIZES
    }
    assert {len(data) for data in patterns.values()} == {
        count * gpt.SECTOR_SIZE for count in bootrom_write_test.WRITE_SIZES
    }
    assert len({data[:512] for data in patterns.values()}) == len(patterns)
    assert all(any(data) for data in patterns.values())


def test_the_test_reboots_the_dot_and_says_so(
    *, stubbed: types.SimpleNamespace, tmp_path: pathlib.Path
) -> None:
    write_test(rig=stubbed, wheel=tmp_path)
    assert stubbed.emmc.rebooted
    assert stubbed.shown == ["\n" + bootrom_write_test.LEFT]
    assert "neither the card nor the cable" in str(stubbed.said["verdict"])


def test_writes_that_read_back_pass_and_put_cache_back() -> None:
    emmc = Emmc()
    held = emmc.read_blocks(count=64, index=REGION)
    synced, said = run_legs(emmc=emmc)
    assert synced
    assert emmc.writes == [*bootrom_write_test.WRITE_SIZES, 64]
    assert said["read over USB"] == ["3 reads of 64 blocks agree"]
    assert said["cache's blocks put back"] == ["yes"]
    assert said["verdict"] == [
        (
            "the eMMC took writes of 1, 34 and 64 blocks over USB and gave them"
            " back unchanged, so neither the card nor the cable is at fault"
        )
    ]
    assert emmc.read_blocks(count=64, index=REGION) == held


def write_test(
    *, rig: types.SimpleNamespace, wheel: pathlib.Path | None = None
) -> None:
    bootrom_write_test.bootrom_write_test(
        line=lambda label, value: rig.said.setdefault(label, []).append(value),
        payload=pathlib.Path("payload.bin"),
        wheel=wheel,
    )
