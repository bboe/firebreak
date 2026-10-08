from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from firebreak import bootrom, plan
from firebreak.android.gpt import Partition
from firebreak.emmc import EmmcArea
from firebreak.mediatek.usbdl import ProtocolMismatchError
from firebreak.plan import Action
from firebreak.plugin import BOOT0, ZeroRpmb
from firebreak.unlocks.amonet_biscuit_v1_1_0 import (
    AMONET_BISCUIT_V1_1_0,
    FLASH_RECOVERY,
)

if TYPE_CHECKING:
    import pathlib

    from firebreak.plugin import Step

BOOT0_BLOCK = b"EMMC_BOOT".ljust(512, b"\0")
EXPECT = b"AMZN"
FILL = b"\x11" * 512
MASTER_BOOT_RECORD = FILL[:510] + b"\x55\xaa"
MISC = Partition(first=2, number=8, sectors=4)
RECOVERY = Partition(first=2, number=12, sectors=8)
RPMB = EXPECT + b"\xaa" * 252


class FakePayload:
    maximum_blocks = 64

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.blocks: dict[tuple[int, int], bytes] = {}
        self.broken = False
        self.lost = 0
        self.partition = 0
        self.rpmb = RPMB
        self.stuck = False

    def _fail(self, *, label: str) -> None:
        if self.broken:
            message = f"the payload did not answer the {label}"
            raise ProtocolMismatchError(message)

    def _held(self, *, index: int) -> bytes:
        held = self.blocks.get((self.partition, index))
        if held is not None:
            return held
        if index:
            return FILL
        return BOOT0_BLOCK if self.partition == EmmcArea.BOOT0 else MASTER_BOOT_RECORD

    def read_block(self, *, index: int) -> bytes:
        self.asked.append(f"read {self.partition}:{index}")
        self._fail(label=f"read of block {index}")
        return self._held(index=index)

    def read_blocks(self, *, count: int, index: int) -> bytes:
        assert 1 <= count <= self.maximum_blocks
        self.asked.append(f"read {self.partition}:{index}+{count}")
        self._fail(label=f"read of {count} blocks at {index}")
        return b"".join(self._held(index=index + offset) for offset in range(count))

    def read_rpmb(self) -> bytes:
        self.asked.append("read rpmb")
        return self.rpmb

    def reboot(self) -> None:
        self.asked.append("reboot")

    def switch_partition(self, *, partition: int) -> None:
        self.asked.append(f"switch {partition}")
        if not self.stuck:
            self.partition = partition

    def write_blocks(self, *, data: bytes, index: int) -> None:
        count, remainder = divmod(len(data), 512)
        assert remainder == 0
        assert 1 <= count <= self.maximum_blocks
        self.asked.append(f"write {self.partition}:{index}+{count}")
        self._fail(label=f"write of {count} blocks at {index}")
        if self.lost:
            self.lost -= 1
            return
        for offset in range(count):
            self.blocks[self.partition, index + offset] = data[
                offset * 512 : (offset + 1) * 512
            ]

    def write_rpmb(self, *, data: bytes) -> None:
        self.asked.append(f"write rpmb {len(data)}")
        if not self.lost:
            self.rpmb = data


@pytest.fixture
def payload() -> FakePayload:
    return FakePayload()


def reads(payload: FakePayload) -> list[str]:
    return [asked for asked in payload.asked if asked.startswith("read")]


def resolved(*, source: pathlib.Path, step: Step) -> Action:
    image = source / "bin" / "twrp.img"
    image.parent.mkdir(exist_ok=True, parents=True)
    image.write_bytes(b"T" * 1024)
    return plan.action(
        partitions={"recovery": RECOVERY},
        source=source,
        step=step,
        unlock=AMONET_BISCUIT_V1_1_0,
    )


def switches(payload: FakePayload) -> list[str]:
    return [asked for asked in payload.asked if asked.startswith("switch")]


def test_a_boot0_write_switches_areas_and_back(*, payload: FakePayload) -> None:
    bootrom.execute(
        actions=(
            Action(
                data=b"E" * 512,
                kind="Write",
                label="preloader",
                length=512,
                offset=512,
                target=BOOT0,
            ),
            Action(
                data=b"L" * 512,
                kind="Write",
                label="lk",
                length=512,
                offset=0,
                target="lk",
            ),
        ),
        payload=payload,
    )
    assert payload.blocks[1, 1] == b"E" * 512
    assert payload.blocks[0, 0] == b"L" * 512
    assert switches(payload) == ["switch 1", "switch 0"]


def test_a_byte_patch_lands_inside_its_sector(*, payload: FakePayload) -> None:
    action = Action(
        data=b"ABB",
        kind="ResetBcb",
        label="bcb",
        length=3,
        offset=(2 + 1) * 512 + 5,
        partition=MISC,
        target="misc",
    )
    bootrom.execute(actions=(action,), payload=payload)
    assert payload.blocks[0, 3] == FILL[:5] + b"ABB" + FILL[8:]
    assert writes(payload) == ["write 0:3+1"]


def test_a_failure_from_the_payload_names_the_action(*, payload: FakePayload) -> None:
    payload.broken = True
    action = Action(
        data=b"x" * 512, kind="Write", label="lk", length=512, offset=0, target="lk"
    )
    with pytest.raises(
        SystemExit, match=r"(?s)Write \(lk\) did not go through.*Do not\s+unplug"
    ):
        bootrom.execute(actions=(action,), payload=payload)


def test_a_lost_switch_to_boot0_stops_before_the_write(*, payload: FakePayload) -> None:
    payload.stuck = True
    action = Action(
        data=b"P" * 512,
        kind="Write",
        label="preloader",
        length=512,
        offset=0,
        target=BOOT0,
    )
    with pytest.raises(SystemExit, match="area 1 does not read as itself"):
        bootrom.execute(actions=(action,), payload=payload)
    assert writes(payload) == []


def test_a_reboot_is_asked_of_the_payload(*, payload: FakePayload) -> None:
    bootrom.execute(actions=(Action(kind="Reboot", label="reboot"),), payload=payload)
    assert payload.asked == ["reboot"]


def test_a_serial_error_partway_through_says_not_to_unplug(
    *, monkeypatch: pytest.MonkeyPatch, payload: FakePayload
) -> None:
    def unplugged(**_: object) -> None:
        message = "device not configured"
        raise OSError(message)

    monkeypatch.setattr(name="write_blocks", target=payload, value=unplugged)
    action = Action(
        data=b"x" * 512, kind="Write", label="lk", length=512, offset=0, target="lk"
    )
    with pytest.raises(
        SystemExit, match=r"(?s)device not configured.*Do not\s+unplug the Dot"
    ):
        bootrom.execute(actions=(action,), payload=payload)


def test_a_user_area_without_a_boot_record_stops_the_write(
    *, payload: FakePayload
) -> None:
    payload.blocks[0, 0] = FILL
    action = Action(
        data=b"x" * 512, kind="Write", label="lk", length=512, offset=512, target="lk"
    )
    with pytest.raises(SystemExit, match=r"area 0 does not read as itself"):
        bootrom.execute(actions=(action,), payload=payload)
    assert writes(payload) == []


def test_a_write_larger_than_a_chunk_goes_in_whole_chunks(
    *, payload: FakePayload
) -> None:
    action = Action(
        data=b"Z" * (70 * 512),
        kind="Write",
        label="tz",
        length=70 * 512,
        offset=4 * 512,
        target="tee1",
    )
    bootrom.execute(actions=(action,), payload=payload)
    assert writes(payload) == ["write 0:4+64", "write 0:68+6"]
    assert reads(payload) == [
        "read 0:0",
        "read 0:4+64",
        "read 0:68+6",
        "read 0:4+64",
        "read 0:68+6",
    ]
    assert payload.blocks[0, 73] == b"Z" * 512


def test_a_write_that_does_not_land_stops_it(*, payload: FakePayload) -> None:
    payload.lost = 1
    action = Action(
        data=b"x" * 512, kind="Write", label="lk", length=512, offset=0, target="lk"
    )
    with pytest.raises(SystemExit, match="did not read back"):
        bootrom.execute(actions=(action,), payload=payload)
    assert (0, 0) not in payload.blocks


def test_a_zero_rpmb_that_expects_nothing_is_refused(
    *, payload: FakePayload, tmp_path: pathlib.Path
) -> None:
    nothing = resolved(source=tmp_path, step=ZeroRpmb(expect=None))
    assert nothing.kind == bootrom.ZERO_RPMB
    with pytest.raises(SystemExit, match="would wipe the RPMB unchecked"):
        bootrom.execute(actions=(nothing,), payload=payload)
    assert payload.asked == []


def test_a_zeroed_boot0_passes_the_area_check(*, payload: FakePayload) -> None:
    payload.blocks[1, 0] = bytes(512)
    action = Action(
        data=b"P" * 512,
        kind="Write",
        label="preloader",
        length=512,
        offset=512,
        target=BOOT0,
    )
    bootrom.execute(actions=(action,), payload=payload)
    assert payload.blocks[1, 1] == b"P" * 512


def test_an_image_is_padded_to_whole_sectors(
    *, payload: FakePayload, tmp_path: pathlib.Path
) -> None:
    image = tmp_path / "lk.bin"
    image.write_bytes(b"L" * 600)
    action = Action(
        image=image,
        kind="Write",
        label="lk",
        length=1024,
        offset=2 * 512,
        target="lk",
    )
    bootrom.execute(actions=(action,), payload=payload)
    assert payload.blocks[0, 2] == b"L" * 512
    assert payload.blocks[0, 3] == b"L" * 88 + bytes(424)


def test_an_rpmb_that_does_not_zero_stops_it(*, payload: FakePayload) -> None:
    payload.lost = 1
    action = Action(expect=EXPECT, kind="ZeroRpmb", label="rpmb", source=repr(EXPECT))
    with pytest.raises(SystemExit, match="still holds"):
        bootrom.execute(actions=(action,), payload=payload)


def test_an_rpmb_that_holds_something_else_is_only_a_warning(
    *, capsys: pytest.CaptureFixture[str], payload: FakePayload
) -> None:
    payload.rpmb = b"JUNK" + b"\x5a" * 252
    action = Action(expect=EXPECT, kind="ZeroRpmb", label="rpmb", source=repr(EXPECT))
    bootrom.execute(actions=(action,), payload=payload)
    said = capsys.readouterr().out
    assert "the RPMB starts b'JUNK'" in said
    assert repr(EXPECT) in said
    assert "already zeroed" not in said
    assert payload.rpmb == bytes(256)


def test_an_rpmb_that_holds_what_the_step_expects_says_nothing(
    *, capsys: pytest.CaptureFixture[str], payload: FakePayload
) -> None:
    action = Action(expect=EXPECT, kind="ZeroRpmb", label="rpmb", source=repr(EXPECT))
    bootrom.execute(actions=(action,), payload=payload)
    assert "the RPMB starts" not in capsys.readouterr().out
    assert payload.rpmb == bytes(256)


def test_an_rpmb_that_is_already_zeroed_says_which_reading_that_is(
    *, capsys: pytest.CaptureFixture[str], payload: FakePayload
) -> None:
    payload.rpmb = bytes(256)
    action = Action(expect=EXPECT, kind="ZeroRpmb", label="rpmb", source=repr(EXPECT))
    bootrom.execute(actions=(action,), payload=payload)
    said = capsys.readouterr().out
    assert "the RPMB starts" in said
    assert "already zeroed, which is what a second run" in said
    assert payload.rpmb == bytes(256)


def test_every_action_switches_its_area_even_when_it_has_not_changed(
    *, payload: FakePayload
) -> None:
    write = Action(
        data=b"EMMC_BOOT" + b"P" * 503,
        kind="Write",
        label="w",
        length=512,
        offset=0,
        target=BOOT0,
    )
    bootrom.execute(actions=(write, write), payload=payload)
    assert switches(payload) == ["switch 1", "switch 1"]
    assert payload.blocks[1, 0] == b"EMMC_BOOT" + b"P" * 503


def test_steps_the_bootrom_cannot_run_stop_the_plan_first(
    *, payload: FakePayload, tmp_path: pathlib.Path
) -> None:
    flash = resolved(source=tmp_path, step=FLASH_RECOVERY)
    assert (flash.kind, flash.offset is None, flash.image is None) == (
        "FastbootFlash",
        False,
        False,
    )
    write = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="lk"
    )
    with pytest.raises(SystemExit, match="cannot carry out FastbootFlash"):
        bootrom.execute(actions=(write, flash), payload=payload)
    assert payload.asked == []


def test_the_rpmb_is_zeroed_and_read_back(*, payload: FakePayload) -> None:
    action = Action(expect=EXPECT, kind="ZeroRpmb", label="rpmb", source=repr(EXPECT))
    bootrom.execute(actions=(action,), payload=payload)
    assert payload.asked == ["read rpmb", "write rpmb 256", "read rpmb"]
    assert payload.rpmb == bytes(256)


def test_what_is_already_there_is_not_written(*, payload: FakePayload) -> None:
    action = Action(
        data=MASTER_BOOT_RECORD,
        kind="Write",
        label="same",
        length=512,
        offset=0,
        target="lk",
    )
    nothing = Action(kind="ShuffleGpt", label="room", length=0)
    bootrom.execute(actions=(nothing, action), payload=payload)
    assert writes(payload) == []


def writes(payload: FakePayload) -> list[str]:
    return [asked for asked in payload.asked if asked.startswith("write")]
