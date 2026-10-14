from __future__ import annotations

import subprocess
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import identify, support
from firebreak.devices import RADAR
from firebreak.identify import Identity, UsbDevice

if TYPE_CHECKING:
    from collections.abc import Callable

    from conftest import FakeAdb

LISTING = (
    "lrwxrwxrwx root root 2026-10-11 00:00 cache -> /dev/block/mmcblk0p3\n"
    f"{support.LISTING_OK}"
)
PARTITIONS = (
    f"major minor  #blocks  name\n 179  3  65536 mmcblk0p3\n{support.PARTITIONS_OK}"
)
USB = (
    UsbDevice(
        manufacturer="MediaTek",
        product="AEORD",
        product_id=0x201C,
        serial="G0X1ABCDEF",
        vendor_id=0x0E8D,
    ),
    UsbDevice(
        manufacturer="Apple",
        product="Keyboard",
        product_id=1,
        serial="",
        vendor_id=0x05AC,
    ),
)


class Dot:
    @property
    def place(self) -> str:
        return self.places[0]

    def __init__(self, *, places: list[str]) -> None:
        self.places = places
        self.ran: list[list[str]] = []
        self.said: dict[str, str] = {
            "getprop ro.twrp.version": "3.7.0_9-0",
            "getprop sys.usb.config": "mtp,adb",
            "id; su -c id": "uid=0(root)",
        }
        self.variables = {
            "antirback_lk_version": "0x0001",
            "antirback_pl_version": "0x0005",
            "antirback_tee_version": "0x0102",
            "lk_build_desc": "f379dba-20170906_000423",
            "product": "BISCUIT",
            "unlock_status": "true",
        }

    def adb_shell(self, *, command: str, timeout: float) -> str:
        del timeout
        if command == "getprop sys.usb.config" and len(self.places) > 1:
            self.places.pop(0)
            return ""
        return self.said.get(command, "")

    def getvar(self, *, name: str) -> str:
        return self.variables[name]

    def in_fastboot(self) -> bool:
        return self.place == "fastboot"

    def run(self, *, arguments: list[str], timeout: float) -> types.SimpleNamespace:
        del timeout
        self.ran.append(arguments)
        if arguments[-1] == "wait-for-recovery":
            if "lost" in self.places:
                raise subprocess.TimeoutExpired(cmd=arguments, timeout=180)
            self.places.pop(0)
        if arguments[-1] == "get-state":
            return types.SimpleNamespace(stdout=self.place + "\n")
        return types.SimpleNamespace(stdout="")

    def usb_serial(self) -> str | None:
        if self.place != "nothing":
            return "G000"
        if len(self.places) > 1:
            self.places.pop(0)
        return None


@pytest.fixture
def legs(*, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    ran: list[dict[str, object]] = []
    monkeypatch.setattr(name="probed", target=support, value=lambda: "none")
    monkeypatch.setattr(name="into_recovery", target=support, value=lambda **_: True)
    monkeypatch.setattr(name="usb_leg", target=support, value=lambda **_: 4)
    monkeypatch.setattr(
        name="emmc_leg", target=support, value=lambda **o: ran.append(o)
    )
    monkeypatch.setattr(name="mmc_said", target=support, value=lambda **_: ["mmc"])
    return ran


@pytest.fixture
def lines() -> list[tuple[str, object]]:
    return []


@pytest.fixture
def shown(*, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    texts: list[str] = []
    monkeypatch.setattr(
        name="show", target=support, value=lambda **said: texts.append(said["text"])
    )
    monkeypatch.setattr(
        name="run",
        target=support,
        value=lambda **_: types.SimpleNamespace(stdout="Android Debug Bridge 1.0.41\n"),
    )
    monkeypatch.setattr(name="probed", target=support, value=lambda: "none")
    monkeypatch.setattr(name="dot_details", target=support, value=lambda **_: ["dot"])
    monkeypatch.setattr(name="mmc_said", target=support, value=lambda **_: ["mmc"])
    monkeypatch.setattr(
        name="identify",
        target=identify,
        value=lambda **_: Identity(device=RADAR, how="USB product 'AEORD'"),
    )
    monkeypatch.setattr(name="usb_devices", target=identify, value=lambda: [*USB])
    return texts


def dot(*, monkeypatch: pytest.MonkeyPatch, places: list[str]) -> Dot:
    fake = Dot(places=places)
    for name in ("adb_shell", "getvar", "in_fastboot", "run", "usb_serial"):
        monkeypatch.setattr(name=name, target=support, value=getattr(fake, name))
    monkeypatch.setattr(name="sleep", target=support.time, value=lambda _: None)
    return fake


def recorder(*, lines: list[tuple[str, object]]) -> Callable[[str, object], None]:
    return lambda label, value: lines.append((label, value))


def test_a_report_answers_nothing_for_a_silent_read(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, shown: list[str]
) -> None:
    del adb
    said: list[str] = []

    def details(*, asked: Callable[..., str]) -> list[str]:
        said.append(asked(command="getprop ro.serialno"))
        return []

    monkeypatch.setattr(name="into_recovery", target=support, value=lambda **_: True)
    monkeypatch.setattr(name="dot_details", target=support, value=details)
    support.report()
    assert said == ["<nothing>"]
    assert shown


def test_a_report_names_the_firebreak_version(
    *, monkeypatch: pytest.MonkeyPatch, shown: list[str]
) -> None:
    monkeypatch.setattr(name="into_recovery", target=support, value=lambda **_: False)
    support.report()
    assert support.labelled(label="firebreak version", value=support.__version__) in (
        shown
    )
    device = "Echo (2nd Generation), by its USB product 'AEORD'"
    assert (
        support.labelled(label="device", value=device)
        + "\n"
        + support.labelled(label="usb", value=USB[0])
    ) in shown
    assert not any("Keyboard" in text for text in shown)
    assert shown[-1] == "\nThe report stops with what is above."


@pytest.mark.parametrize("built", [False, True])
def test_a_report_reads_the_dot_s_recovery(
    *,
    adb: FakeAdb,
    built: bool,
    monkeypatch: pytest.MonkeyPatch,
    shown: list[str],
) -> None:
    if built:
        held = support.CACHE / f"system-{support.BUILDS['5.5.5.4'].sha256[:12]}" / "md5"
        held.parent.mkdir(parents=True)
        held.write_text("abc 2 1\n")
    monkeypatch.setattr(name="into_recovery", target=support, value=lambda **_: True)
    adb.answers["ls -l"] = [LISTING]
    adb.answers["cat /proc/partitions"] = [PARTITIONS]
    support.report()
    text = "\n".join(shown)
    assert "dot" in shown
    assert "mmc" in shown
    if built:
        assert "8192 bytes, md5 abc" in text
    else:
        assert "not built yet" in text
    assert shown[-1] == "\n" + support.LEFT_IN_RECOVERY


def test_into_recovery_gives_up_after_its_wait(
    *, lines: list[tuple[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    dot(monkeypatch=monkeypatch, places=["nothing"])
    clock = iter(range(0, 10 * support.WAIT, support.WAIT // 2))
    monkeypatch.setattr(
        name="monotonic", target=support.time, value=lambda: next(clock)
    )
    assert support.into_recovery(line=recorder(lines=lines)) is False


@pytest.mark.parametrize(
    "places",
    [
        ["recovery"],
        ["fastboot", "recovery"],
        ["device", "recovery"],
        ["recovery", "recovery"],
        ["nothing", "nothing", "fastboot", "recovery"],
    ],
)
def test_into_recovery_reaches_twrp_from_where_the_dot_is(
    *,
    capsys: pytest.CaptureFixture[str],
    lines: list[tuple[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    places: list[str],
) -> None:
    start = places[0]
    fake = dot(monkeypatch=monkeypatch, places=places)
    assert support.into_recovery(line=recorder(lines=lines)) is True
    out = capsys.readouterr().out
    if start == "fastboot":
        assert ("fastboot product", "BISCUIT") in lines
        assert ("fastboot antirback_pl_version", "0x0005") in lines
        assert ["fastboot", "oem", "reboot-recovery"] in fake.ran
    if start == "device":
        assert ["adb", "reboot", "recovery"] in fake.ran
    if start == "nothing":
        assert out.count("comes from the Dot's recovery") == 1


@pytest.mark.parametrize(
    ("places", "change", "said"),
    [
        (["fastboot"], ("variables", "unlock_status", ""), "did not say whether"),
        (["fastboot"], ("variables", "unlock_status", "false"), "is locked"),
        (["recovery"], ("said", "getprop ro.twrp.version", ""), "not TWRP"),
        (["device"], ("said", "id; su -c id", "uid=2000(shell)"), "without root"),
        (["fastboot", "lost"], ("said", "", ""), "within 3 minutes"),
    ],
)
def test_into_recovery_says_why_it_stops(  # ruff: ignore[too-many-arguments]
    *,
    capsys: pytest.CaptureFixture[str],
    change: tuple[str, str, str],
    lines: list[tuple[str, object]],
    monkeypatch: pytest.MonkeyPatch,
    places: list[str],
    said: str,
) -> None:
    fake = dot(monkeypatch=monkeypatch, places=places)
    table, key, value = change
    getattr(fake, table)[key] = value
    assert support.into_recovery(line=recorder(lines=lines)) is False
    assert said in " ".join(capsys.readouterr().out.split())


def test_the_write_test_cleans_up_after_a_failed_leg(
    *, adb: FakeAdb, legs: list[dict[str, object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del legs

    def fail(**_: object) -> int:
        message = "leg"
        raise RuntimeError(message)

    monkeypatch.setattr(name="usb_leg", target=support, value=fail)
    with pytest.raises(RuntimeError, match="leg"):
        support.write_test()
    assert adb.commands(holding="rm -f")


def test_the_write_test_needs_a_recovery(
    *,
    capsys: pytest.CaptureFixture[str],
    legs: list[dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(name="into_recovery", target=support, value=lambda **_: False)
    support.write_test()
    assert legs == []
    assert "needs a recovery" in capsys.readouterr().out


def test_the_write_test_runs_both_legs_and_cleans_up(
    *, adb: FakeAdb, capsys: pytest.CaptureFixture[str], legs: list[dict[str, object]]
) -> None:
    adb.answers["toybox dd --help"] = ["yes"]
    adb.answers["ls -l"] = [LISTING]
    adb.answers["cat /proc/partitions"] = [PARTITIONS]
    support.write_test()
    assert legs[0]["node"] == "/dev/block/mmcblk0p3"
    assert legs[0]["blocks"] == 64
    assert legs[0]["chunk"] == 4
    assert support.SESSION.dd == "toybox dd"
    assert adb.commands(holding="rm -f") == [f"rm -f {support.USB_TEST}"]
    assert capsys.readouterr().out.endswith(support.LEFT_IN_RECOVERY + "\n")


def test_the_write_test_skips_the_emmc_leg_without_whole_lists(
    *,
    adb: FakeAdb,
    capsys: pytest.CaptureFixture[str],
    legs: list[dict[str, object]],
) -> None:
    adb.answers["ls -l"] = [subprocess.TimeoutExpired(cmd="adb", timeout=60)]
    support.write_test()
    assert legs == []
    assert "did not arrive whole" in capsys.readouterr().out
