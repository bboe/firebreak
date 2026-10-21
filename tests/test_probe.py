from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from typing import TYPE_CHECKING

import pytest

from firebreak import host, probe
from firebreak.devices import LK, UNLOCK_BUILDS, State
from firebreak.ui import FatalError

NO_FASTBRICK = next(iter(UNLOCK_BUILDS))

if TYPE_CHECKING:
    import pathlib

    from conftest import FakeAdb

FASTBOOT = "G000\tfastboot"
ON_USB = "List of devices attached\nG000  {state} usb:1-1 product:biscuit"
TABLE = "  1  1024  2047  512.0 KiB  0700  {boot}\n 12  65536  131071  userdata"
TWRP_3_2_3 = b"3" * 4096
TWRP_BBOE = b"B" * 8192


@pytest.fixture
def dot(*, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch) -> FakeAdb:
    monkeypatch.setattr(name="USER_SERIAL", target=host, value=None)
    monkeypatch.delenv(name="ANDROID_SERIAL", raising=False)
    monkeypatch.setattr(name="emos", target=probe, value=lambda **_: "0")
    return adb


@pytest.fixture
def recoveries(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    (tmp_path / "v1" / "bin").mkdir(parents=True)
    (tmp_path / "v1" / "bin" / "twrp.img").write_bytes(TWRP_3_2_3)
    monkeypatch.setattr(
        name="RECOVERY",
        target=probe.amonet_biscuit_v1_1_0_bboe,
        value=dataclasses.replace(
            probe.amonet_biscuit_v1_1_0_bboe.RECOVERY,
            sha256=hashlib.sha256(TWRP_BBOE).hexdigest(),
            size=len(TWRP_BBOE),
        ),
    )
    monkeypatch.setattr(name="unpack", target=probe, value=lambda **_: tmp_path / "v1")


def booted(*, dot: FakeAdb, name: str, root: str = "uid=0(root)") -> None:
    dot.answers["-l"] = [ON_USB.format(state="device")]
    dot.answers["get-state"] = ["device"]
    dot.answers["sys.boot_completed"] = ["1"]
    dot.answers["ro.build.version.name"] = [name]
    dot.answers["id; su -c id"] = ["uid=2000(shell) " + root]
    dot.answers["su -c id"] = [root]


def fastboot(*, dot: FakeAdb, little_kernel: str, unlock: str) -> None:
    dot.answers["devices"] = [FASTBOOT]
    dot.answers["unlock_status"] = [f"unlock_status: {unlock}"]
    dot.answers["lk_build_desc"] = [f"lk_build_desc: {little_kernel}"]


def recovery(
    *, dot: FakeAdb, little_kernel: str, table: str = "boot_a", version: str
) -> None:
    dot.answers["-l"] = [ON_USB.format(state="recovery")]
    dot.answers["get-state"] = ["recovery"]
    dot.answers["ro.twrp.version"] = [version]
    dot.answers["ro.boot.lk_build_desc"] = [little_kernel]
    dot.answers["sys.usb.config"] = ["mtp,adb"]
    dot.answers["sgdisk"] = [TABLE.format(boot=table) + "\ntable-ok"]


@pytest.mark.parametrize(
    ("name", "root", "found"),
    [
        ("Fire OS 6.5.7.4", "uid=0(root)", State.AMONET_V2_0_0_BOOTED),
        ("Fire OS 6.5.7.4", "Permission denied", State.STOCK_BOOTED),
        ("Fire OS 5.5.5.4", "Permission denied", State.BOOTED),
    ],
)
def test_a_booted_dot_is_read_from_its_os_and_root(
    *, dot: FakeAdb, found: State, name: str, root: str
) -> None:
    booted(dot=dot, name=name, root=root)
    assert probe.probe() == found


def test_a_booting_fire_os_5_is_not_yet_rooted(*, dot: FakeAdb) -> None:
    booted(dot=dot, name="Fire OS 5.5.5.4")
    dot.answers["sys.boot_completed"] = [""]
    assert probe.probe() == State.BOOTED
    assert dot.commands(holding="exec-out") == []


@pytest.mark.parametrize(("found", "state"), [("1", State.EMOS), ("0", State.NONE)])
def test_a_dot_on_no_adb_is_emos_or_nothing(
    *, dot: FakeAdb, found: str, monkeypatch: pytest.MonkeyPatch, state: State
) -> None:
    monkeypatch.setattr(name="emos", target=probe, value=lambda **_: found)
    assert probe.probe() == state
    assert dot.commands(holding="get-state") == []


def test_a_fire_os_with_no_system_has_no_shell(*, dot: FakeAdb) -> None:
    booted(dot=dot, name="Fire OS 5.5.5.4")
    dot.answers["sys.boot_completed"] = [
        "- exec '/system/bin/sh' failed: No such file or directory (2) -"
    ]
    assert probe.probe() == State.NO_SYSTEM


@pytest.mark.parametrize(
    ("held", "found"),
    [
        (TWRP_BBOE, State.AMONET_V1_1_0_BBOE_BOOTED),
        (TWRP_3_2_3 + b"tail", State.AMONET_V1_1_0_BOOTED),
        (b"other" * 2000, State.ROOTED),
    ],
)
@pytest.mark.usefixtures("recoveries")
def test_a_rooted_fire_os_5_is_named_by_its_recovery(
    *, dot: FakeAdb, found: State, held: bytes
) -> None:
    booted(dot=dot, name="Fire OS 5.5.5.4")
    dot.raw = held
    assert probe.probe() == found
    read = [words for words in dot.asked if words[1] == "exec-out"]
    assert read[0][-1].endswith(f"count={len(TWRP_BBOE) // 512} 2>/dev/null'")


def test_a_twrp_that_has_not_started_its_usb_is_starting(*, dot: FakeAdb) -> None:
    recovery(dot=dot, little_kernel=LK.FIREOS5.value, version="3.2.3-0")
    dot.answers["sys.usb.config"] = ["adb"]
    assert probe.probe() == State.STARTING


def test_an_unauthorized_dot_is_stock(*, dot: FakeAdb) -> None:
    dot.answers["-l"] = [ON_USB.format(state="unauthorized")]
    dot.answers["get-state"] = ["error: device unauthorized."]
    assert probe.probe() == State.STOCK_BOOTED


@pytest.mark.parametrize(
    ("unlock", "little_kernel", "found"),
    [
        ("false", LK.FIREOS5.value, State.STOCK_FIREOS5_FASTBOOT),
        ("false", LK.FIREOS6.value, State.STOCK_FASTBOOT),
        ("false", NO_FASTBRICK, State.STOCK_NO_FASTBRICK_FASTBOOT),
        ("", LK.FIREOS5.value, State.STARTING),
        ("true", "", State.STARTING),
        ("true", LK.FIREOS5.value, State.AMONET_V1_1_0_FASTBOOT),
        ("TRUE", LK.FIREOS6.value, State.AMONET_V2_0_0_FASTBOOT),
    ],
)
def test_fastboot_is_read_from_its_unlock_and_bootloader(
    *, dot: FakeAdb, found: State, little_kernel: str, unlock: str
) -> None:
    fastboot(dot=dot, little_kernel=little_kernel, unlock=unlock)
    assert probe.probe() == found


def test_probed_prints_an_unreadable_state_plain_and_masked(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    message = (
        "sgdisk did not print the Dot's table:\n"
        "Disk identifier (GUID): 0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    )

    def state() -> State:
        raise FatalError(message=message)

    monkeypatch.setattr(name="state", target=probe, value=state)
    assert probe.probed() == (
        "<unreadable: ERROR: sgdisk did not print the Dot's table:>"
    )
    monkeypatch.setattr(name="state", target=probe, value=lambda: State.NONE)
    assert probe.probed() == State.NONE.value


def test_state_marks_the_probe_quiet_while_it_runs(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []

    def quiet() -> State:
        seen.append(probe.SESSION.probing)
        return State.NONE

    monkeypatch.setattr(name="probe", target=probe, value=quiet)
    assert probe.state() == State.NONE
    assert seen == [True]
    assert not probe.SESSION.probing


def test_state_reads_a_probe_that_times_out_as_starting(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def slow() -> State:
        raise subprocess.TimeoutExpired(cmd="adb", timeout=30)

    monkeypatch.setattr(name="probe", target=probe, value=slow)
    assert probe.state() == State.STARTING
    assert not probe.SESSION.probing


def test_the_recovery_read_names_the_partition_by_name(*, dot: FakeAdb) -> None:
    dot.raw = b"R" * 1024
    assert probe.read_recovery(size=1024) == dot.raw
    assert dot.asked[-1][-1] == (
        f"su -c 'dd if={probe.BY_NAME}/recovery bs=512 count=2 2>/dev/null'"
    )


@pytest.mark.parametrize(
    ("version", "little_kernel", "table", "found"),
    [
        ("3.2.3-0", LK.FIREOS5.value, "boot_a", State.AMONET_V1_1_0_TWRP),
        (
            probe.amonet_biscuit_v1_1_0_bboe.TWRP_VERSION,
            LK.FIREOS5.value,
            "boot_a",
            State.AMONET_V1_1_0_BBOE_TWRP,
        ),
        ("3.7.0_9-0", LK.FIREOS6.value, "boot_a", State.AMONET_V2_0_0_TWRP),
        (
            "3.7.0_9-0",
            LK.FIREOS6.value,
            "boot_a_x",
            State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
        ),
        ("", LK.FIREOS5.value, "boot_a", State.STARTING),
        ("3.2.3-0", "", "boot_a", State.STARTING),
    ],
)
def test_twrp_is_read_from_its_version_bootloader_and_table(
    *, dot: FakeAdb, found: State, little_kernel: str, table: str, version: str
) -> None:
    recovery(dot=dot, little_kernel=little_kernel, table=table, version=version)
    assert probe.probe() == found
