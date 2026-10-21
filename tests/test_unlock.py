from __future__ import annotations

import hashlib
import subprocess
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import unlock
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

    from conftest import FakeAdb

LK = {"stock": b"S" * 241664, "v1.1.0": b"1" * 372368, "v2.0.0": b"2" * 359744}


def brick(
    *,
    adb: FakeAdb,
    little_kernel: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    adb.answers["product"] = ["product: BISCUIT"]
    adb.answers["lk_build_desc"] = [f"lk_build_desc: {little_kernel}"]
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)


def guard(
    *, monkeypatch: pytest.MonkeyPatch, slots: dict[str, bytes], tmp_path: pathlib.Path
) -> list[str]:
    read: list[str] = []
    numbers = {"lk_a": 3, "lk_b": 5}
    held = {f"{unlock.DISK}p{numbers[slot]}": data for slot, data in slots.items()}
    releases = {
        unlock.amonet_biscuit_v1_1_0.SOURCE.name: LK["v1.1.0"],
        unlock.amonet_biscuit_v2_0_0.SOURCE.name: LK["v2.0.0"],
    }

    def unpacked(*, download: object) -> pathlib.Path:
        root = tmp_path / download.name
        (root / "bin").mkdir(exist_ok=True, parents=True)
        (root / "bin" / "lk.bin").write_bytes(releases[download.name])
        return root

    def shell(*, command: str, timeout: float) -> str:
        del timeout
        node = command.split(sep=" ")[2]
        size = int(command.split(sep="bs=")[1].split(maxsplit=1, sep=" ")[0])
        read.append(node)
        data = held[node][:size]
        return f"{hashlib.md5(data, usedforsecurity=False).hexdigest()}  -"

    monkeypatch.setattr(name="adb_shell", target=unlock, value=shell)
    monkeypatch.setattr(
        name="partitions",
        target=unlock,
        value=lambda: {slot: (numbers[slot], 0, 0) for slot in slots},
    )
    monkeypatch.setattr(name="unpack", target=unlock, value=unpacked)
    unlock.amonet_chain()
    return read


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"unlock_status": "false"}, "not in amonet's fastboot"),
        (
            {
                "lk_build_desc": "63cb91b-20221007_073612",
                "product": "RADAR",
                "unlock_status": "true",
            },
            "reports 'RADAR', not BISCUIT, so nothing was written. firebreak supports",
        ),
        (
            {
                "lk_build_desc": "63cb91b-20221007_072309",
                "product": "",
                "unlock_status": "true",
            },
            "reports no product, so nothing was written. Run",
        ),
        (
            {"lk_build_desc": "", "product": "BISCUIT", "unlock_status": "true"},
            "did not report its bootloader version; boot0 was not erased",
        ),
        (
            {
                "lk_build_desc": unlock.LK.FIREOS5.value,
                "product": "BISCUIT",
                "unlock_status": "true",
            },
            "already runs amonet v1.1.0's bootloader",
        ),
    ],
)
def test_a_downgrade_checks_the_dot_before_it_erases_boot0(
    *,
    answers: dict[str, str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="pyserial_wheel", target=unlock, value=lambda: None)
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **o: answers.get(o["name"], "")
    )
    monkeypatch.setattr(
        name="bootrom_step", target=unlock, value=lambda **_: pytest.fail("erased")
    )
    with pytest.raises(FatalError, match=message):
        unlock.stage_downgrade()


def test_a_downgrade_erases_boot0_through_fastboot(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    stepped: list[dict[str, object]] = []
    answers = {
        "lk_build_desc": unlock.LK.FIREOS6.value,
        "product": "BISCUIT",
        "unlock_status": "true",
    }
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="pyserial_wheel", target=unlock, value=lambda: None)
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **o: answers[o["name"]]
    )
    monkeypatch.setattr(
        name="bootrom_step", target=unlock, value=lambda **o: stepped.append(o)
    )
    monkeypatch.setattr(
        name="stage_amonet_v1_1_0_recovery", target=unlock, value=lambda: True
    )
    assert unlock.stage_downgrade() is True
    assert stepped[0]["erase"] is unlock.erase_by_fastboot
    assert stepped[0]["payload"] == tmp_path / "brom-payload" / "build" / "payload.bin"


def test_a_downgrade_that_meets_a_locked_fastboot_returns_false(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    answers = {
        "lk_build_desc": unlock.LK.FIREOS6.value,
        "product": "BISCUIT",
        "unlock_status": "true",
    }
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="pyserial_wheel", target=unlock, value=lambda: None)
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **o: answers[o["name"]]
    )
    monkeypatch.setattr(name="bootrom_step", target=unlock, value=lambda **_: True)
    monkeypatch.setattr(
        name="amonet_v2_0_0_payload", target=unlock, value=lambda: tmp_path
    )
    monkeypatch.setattr(
        name="stage_amonet_v1_1_0_recovery", target=unlock, value=lambda: False
    )
    assert unlock.stage_downgrade() is False


def test_a_fastboot_that_never_says_whether_it_is_unlocked_stops_cleanly(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **o: asked.append(o["name"]) or ""
    )
    monkeypatch.setattr(name="sleep", target=unlock.time, value=lambda _: None)
    monkeypatch.setattr(
        name="run", target=unlock, value=lambda **_: pytest.fail("flashed")
    )
    with pytest.raises(FatalError, match="did not say whether it is unlocked"):
        unlock.stage_amonet_v1_1_0_recovery()
    assert asked == ["unlock_status"] * unlock.PUSH_TRIES


@pytest.mark.parametrize(
    ("product", "little_kernel", "message"),
    [
        ("product: crown", "x", "reports 'crown', not BISCUIT"),
        ("product: BISCUIT", "", "did not report the bootloader version"),
    ],
)
def test_a_fastbrick_checks_the_dot_before_it_flashes(  # ruff: ignore[too-many-arguments]
    *,
    adb: FakeAdb,
    little_kernel: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    product: str,
    tmp_path: pathlib.Path,
) -> None:
    brick(
        adb=adb, little_kernel=little_kernel, monkeypatch=monkeypatch, tmp_path=tmp_path
    )
    adb.answers["product"] = [product]
    with pytest.raises(FatalError, match=message):
        unlock.stage_fastbrick()
    assert adb.commands(holding="brick") == []


@pytest.mark.parametrize(
    ("said", "message"),
    [
        ("FAILED (remote: 'eMMC-RO')", "eMMC is read-only"),
        ("FAILED (remote: 'Device mismatch')", "rejected this device"),
        ("FAILED (remote: 'unknown')", "did not start after 10 attempts"),
    ],
)
def test_a_fastbrick_that_fails_leaves_the_dot_unmodified(
    *,
    adb: FakeAdb,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    tmp_path: pathlib.Path,
) -> None:
    brick(
        adb=adb,
        little_kernel=unlock.LK.FIREOS5.value,
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )
    adb.answers["fastbrick.img"] = [said]
    with pytest.raises(FatalError, match=message) as stopped:
        unlock.stage_fastbrick()
    assert "not modified" in stopped.value.message


def test_a_fastbrick_whose_timeout_says_nothing_still_started(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    brick(
        adb=adb,
        little_kernel=unlock.LK.FIREOS5.value,
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
    )
    adb.answers["fastbrick.img"] = [
        subprocess.TimeoutExpired(cmd="fastboot", timeout=8)
    ]
    unlock.stage_fastbrick()


def test_a_locked_fastboot_is_left_for_its_own_stage(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[list[object]] = []
    monkeypatch.setattr(name="getvar", target=unlock, value=lambda **_: "false")
    monkeypatch.setattr(
        name="run",
        target=unlock,
        value=lambda **options: ran.append(options["arguments"]),
    )
    assert unlock.stage_amonet_v1_1_0_recovery() is False
    assert ran == []
    assert "locked fastboot" in capsys.readouterr().out


def test_an_lk_read_answered_after_a_reconnect_is_used(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "lk.bin").write_bytes(LK["v2.0.0"])
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="reconnect", target=unlock, value=lambda **_: None)
    want = hashlib.md5(LK["v2.0.0"], usedforsecurity=False).hexdigest()
    adb.answers["md5sum"] = ["", f"{want}  -"]
    assert unlock.amonet_lk(node=f"{unlock.DISK}p3") is True


@pytest.mark.parametrize(
    ("said", "message"),
    [
        ("", "did not answer with an md5 of its first"),
        ("1234  -", "did not answer with an md5 of its first"),
    ],
)
def test_an_lk_read_that_never_answers_stops_before_anything_is_written(
    *,
    adb: FakeAdb,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "lk.bin").write_bytes(LK["v2.0.0"])
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    reconnected: list[str] = []
    monkeypatch.setattr(
        name="reconnect", target=unlock, value=lambda **o: reconnected.append(o)
    )
    adb.answers["md5sum"] = [said]
    with pytest.raises(FatalError, match=message):
        unlock.amonet_lk(node=f"{unlock.DISK}p3")
    assert len(reconnected) == unlock.PUSH_TRIES - 1
    assert len(adb.commands(holding="md5sum")) == unlock.PUSH_TRIES


def test_an_unlock_flashes_its_payload_then_erases_boot0(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    order: list[str] = []
    flashed: list[list[str]] = []
    erased = tmp_path / "boot0-erased"
    monkeypatch.setattr(name="CACHE", target=unlock, value=tmp_path)
    monkeypatch.setattr(name="ERASED", target=unlock, value=erased)
    monkeypatch.setattr(name="check_product", target=unlock, value=lambda: None)
    monkeypatch.setattr(name="extract", target=unlock, value=lambda **_: None)
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **_: next(iter(unlock.UNLOCK_BUILDS))
    )
    monkeypatch.setattr(
        name="download", target=unlock.updates, value=lambda **_: tmp_path / "ota.bin"
    )
    monkeypatch.setattr(
        name="write", target=unlock.lk_unlock, value=lambda **o: o["path"]
    )

    def flash(**options: object) -> None:
        order.append("flash")
        flashed.append(options["arguments"])  # type: ignore[arg-type]

    monkeypatch.setattr(name="run", target=unlock, value=flash)
    monkeypatch.setattr(
        name="erase_by_fastboot", target=unlock, value=lambda: order.append("erase")
    )
    assert unlock.stage_unlock() is True
    assert flashed[0][:5] == ["fastboot", "-S", "256M", "flash", unlock.UNLOCK_TARGET]
    assert order == ["flash", "erase"]
    assert erased.exists()


def test_an_unlock_refuses_a_bootloader_it_cannot_patch(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="check_product", target=unlock, value=lambda: None)
    monkeypatch.setattr(name="getvar", target=unlock, value=lambda **_: "")
    with pytest.raises(FatalError, match="which this cannot unlock"):
        unlock.stage_unlock()


def test_an_unlock_that_cannot_erase_boot0_keeps_the_marker_it_was_left(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    erased = tmp_path / "boot0-erased"
    monkeypatch.setattr(name="CACHE", target=unlock, value=tmp_path)
    monkeypatch.setattr(name="ERASED", target=unlock, value=erased)
    monkeypatch.setattr(name="check_product", target=unlock, value=lambda: None)
    monkeypatch.setattr(name="extract", target=unlock, value=lambda **_: None)
    monkeypatch.setattr(
        name="getvar", target=unlock, value=lambda **_: next(iter(unlock.UNLOCK_BUILDS))
    )
    monkeypatch.setattr(
        name="download", target=unlock.updates, value=lambda **_: tmp_path / "ota.bin"
    )
    monkeypatch.setattr(
        name="write", target=unlock.lk_unlock, value=lambda **o: o["path"]
    )
    monkeypatch.setattr(name="run", target=unlock, value=lambda **_: None)
    monkeypatch.setattr(
        name="erase_by_fastboot", target=unlock, value=lambda: "fastboot reboot failed"
    )
    with pytest.raises(FatalError, match="fastboot reboot failed"):
        unlock.stage_unlock()
    assert erased.exists()


def test_an_unlocked_fastboot_takes_v1_1_0_to_its_recovery(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    ran: list[list[object]] = []
    monkeypatch.setattr(name="getvar", target=unlock, value=lambda **_: "true")
    monkeypatch.setattr(name="unpack", target=unlock, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="fetch", target=unlock, value=lambda **_: tmp_path / "twrp"
    )
    monkeypatch.setattr(
        name="run",
        target=unlock,
        value=lambda **options: ran.append(options["arguments"]),
    )
    assert unlock.stage_amonet_v1_1_0_recovery() is True
    assert [words[1:4] for words in ran] == [
        ["-S", "256M", "flash"],
        ["-S", "256M", "flash"],
        ["oem", "reboot-recovery"],
    ]


def test_erasing_boot0_reboots_the_dot(*, adb: FakeAdb) -> None:
    assert unlock.erase_by_fastboot() == ""
    assert [words[1:] for words in adb.asked] == [["erase", "boot0"], ["reboot"]]


def test_erasing_boot0_that_fails_leaves_no_marker(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    unlock.ERASED.touch()
    answers = iter([1, 0, 1])
    monkeypatch.setattr(
        name="run",
        target=unlock,
        value=lambda **_: types.SimpleNamespace(returncode=next(answers), stdout="no"),
    )
    assert unlock.erase_by_fastboot().startswith("fastboot erase boot0 failed")
    assert not unlock.ERASED.exists()
    unlock.ERASED.touch()
    assert unlock.erase_by_fastboot().startswith("fastboot reboot failed")
    assert unlock.ERASED.exists()


@pytest.mark.parametrize(
    ("little_kernel", "image"),
    [
        (unlock.LK.FIREOS5.value, "bin/fastbrick.img"),
        (unlock.LK.FIREOS6.value, "bin/fastbrick-20221007.img"),
        (unlock.LK.FIREOS6_4315.value, "bin/fastbrick-20221007.img"),
    ],
)
def test_the_fastbrick_picks_the_image_for_the_bootloader(
    *,
    adb: FakeAdb,
    image: str,
    little_kernel: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    brick(
        adb=adb, little_kernel=little_kernel, monkeypatch=monkeypatch, tmp_path=tmp_path
    )
    adb.answers[image] = [
        "Sending 'brick'",
        subprocess.TimeoutExpired(cmd="fastboot", output=b"Writing 'brick'", timeout=8),
    ]
    unlock.stage_fastbrick()
    assert len(adb.commands(holding=image)) == 2
    assert unlock.PROGRESS.open


def test_the_guard_needs_both_slots(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    with pytest.raises(FatalError, match="has no lk_b"):
        guard(monkeypatch=monkeypatch, slots={"lk_a": LK["v2.0.0"]}, tmp_path=tmp_path)


@pytest.mark.parametrize(
    argnames=("slots", "nodes"),
    argvalues=[
        ({"lk_a": LK["v2.0.0"], "lk_b": LK["stock"]}, ["p3"]),
        ({"lk_a": LK["v1.1.0"], "lk_b": LK["stock"]}, ["p3", "p3"]),
        (
            {"lk_a": LK["v1.1.0"][:4096] + LK["v2.0.0"][4096:], "lk_b": LK["v2.0.0"]},
            ["p3", "p3", "p5"],
        ),
        (
            {"lk_a": LK["v2.0.0"][:4096] + LK["stock"][4096:], "lk_b": LK["v1.1.0"]},
            ["p3", "p3", "p5", "p5"],
        ),
    ],
    ids=["v2.0.0", "v1.1.0", "lk_a-torn", "lk_a-torn-over-stock"],
)
def test_the_guard_passes_an_amonet_lk_in_either_slot(
    *,
    monkeypatch: pytest.MonkeyPatch,
    nodes: list[str],
    slots: dict[str, bytes],
    tmp_path: pathlib.Path,
) -> None:
    read = guard(monkeypatch=monkeypatch, slots=slots, tmp_path=tmp_path)
    assert [node[len(unlock.DISK) :] for node in read] == nodes


def test_the_guard_refuses_a_stock_lk_in_both_slots(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    with pytest.raises(FatalError, match="neither lk_a nor lk_b"):
        guard(
            monkeypatch=monkeypatch,
            slots={"lk_a": LK["stock"], "lk_b": LK["stock"]},
            tmp_path=tmp_path,
        )
