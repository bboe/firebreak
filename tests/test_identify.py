from __future__ import annotations

import dataclasses
import plistlib
import re
import subprocess
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import identify
from firebreak.devices import BISCUIT, CROWN, RADAR
from firebreak.ui import FatalError
from firebreak.unlocks.targets import DEFAULTS, TARGETS

if TYPE_CHECKING:
    import pathlib

    from firebreak.plugin import Target

AEOBC = identify.UsbDevice(
    manufacturer="MediaTek",
    product="AEOBC",
    product_id=0x201C,
    serial="G090000000000000",
    vendor_id=0x0E8D,
)
AEORD = identify.UsbDevice(
    manufacturer="Amazon",
    product="Echo (2nd Gen)",
    product_id=0xD001,
    serial="",
    vendor_id=0x18D1,
)
FASTBOOT = identify.UsbDevice(
    manufacturer="",
    product="Android",
    product_id=0x0C01,
    serial="G090000000000000",
    vendor_id=0x0BB4,
)
KEYBOARD = identify.UsbDevice(
    manufacturer="Apple", product="AEORD", product_id=1, serial="", vendor_id=0x05AC
)


def answered(*, monkeypatch: pytest.MonkeyPatch, stdout: str) -> list[list[str]]:
    asked: list[list[str]] = []

    def command(*, arguments: list[str], **_: object) -> types.SimpleNamespace:
        asked.append(arguments)
        return types.SimpleNamespace(stdout=stdout.encode())

    monkeypatch.setattr(name="command", target=identify, value=command)
    return asked


def connected(
    *,
    fastboot: str | None = None,
    monkeypatch: pytest.MonkeyPatch,
    usb: list[identify.UsbDevice] | None = None,
) -> None:
    monkeypatch.setattr(
        name="in_fastboot", target=identify, value=lambda: fastboot is not None
    )
    monkeypatch.setattr(name="getvar", target=identify, value=lambda **_: fastboot)
    monkeypatch.setattr(name="usb_devices", target=identify, value=lambda: usb or [])


def radar_too(*, monkeypatch: pytest.MonkeyPatch) -> dict[str, Target]:
    radar = {
        name: dataclasses.replace(TARGETS[BISCUIT]["stock"], device=RADAR, name=name)
        for name in ("stock", "amonet-radar-v1.0.0")
    }
    monkeypatch.setattr(
        name="TARGETS", target=identify, value={**TARGETS, RADAR: radar}
    )
    monkeypatch.setattr(
        name="DEFAULTS",
        target=identify,
        value={**DEFAULTS, RADAR: "amonet-radar-v1.0.0"},
    )
    return radar


def test_a_booted_dot_is_named_by_its_usb_product(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected(monkeypatch=monkeypatch, usb=[AEOBC, KEYBOARD])
    assert identify.identify() == identify.Identity(
        device=BISCUIT, how="USB product 'AEOBC'"
    )


def test_a_dot_in_fastboot_is_named_by_its_product(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected(fastboot="RADAR", monkeypatch=monkeypatch)
    assert identify.identify() == identify.Identity(
        device=RADAR, how="fastboot product RADAR"
    )


@pytest.mark.parametrize(
    argnames=("platform", "fastboot", "usb", "want"),
    argvalues=[
        ("win32", None, [FASTBOOT], True),
        ("win32", "biscuit", [FASTBOOT], False),
        ("win32", None, [AEOBC], False),
        ("darwin", None, [FASTBOOT], False),
    ],
)
def test_a_fastboot_dot_that_fastboot_cannot_see_lacks_its_driver(
    *,
    fastboot: str | None,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    usb: list[identify.UsbDevice],
    want: bool,
) -> None:
    connected(fastboot=fastboot, monkeypatch=monkeypatch, usb=usb)
    monkeypatch.setattr(name="platform", target=identify.sys, value=platform)
    assert identify.fastboot_driver_missing() is want


def test_a_fastboot_with_an_unknown_product_names_no_device(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected(fastboot="", monkeypatch=monkeypatch)
    assert identify.identify() == identify.Identity(
        device=None, how="fastboot product <none>"
    )


@pytest.mark.parametrize("usb", [[AEOBC], []], ids=["biscuit", "unknown"])
def test_a_matching_or_unknown_device_is_let_through(
    *, monkeypatch: pytest.MonkeyPatch, usb: list[identify.UsbDevice]
) -> None:
    connected(monkeypatch=monkeypatch, usb=usb)
    identify.check_target(target=TARGETS[BISCUIT]["stock"])


@pytest.mark.parametrize("usb", [[AEOBC], []], ids=["biscuit", "unknown"])
def test_a_name_one_device_has_is_checked_against_it(
    *, monkeypatch: pytest.MonkeyPatch, usb: list[identify.UsbDevice]
) -> None:
    connected(monkeypatch=monkeypatch, usb=usb)
    assert (
        identify.choose_target(device=None, name=None)
        == (TARGETS[BISCUIT]["amonet-biscuit-v1.1.0-bboe"])
    )
    connected(monkeypatch=monkeypatch, usb=[AEORD])
    with pytest.raises(FatalError, match="this is an Echo \\(2nd Generation\\)"):
        identify.choose_target(device=None, name="stock")


@pytest.mark.parametrize(
    argnames=("name", "chosen"),
    argvalues=[(None, "amonet-biscuit-v1.1.0-bboe"), ("stock", "stock")],
    ids=["default", "stock"],
)
def test_a_name_two_devices_share_is_chosen_by_the_device(
    *, chosen: str, monkeypatch: pytest.MonkeyPatch, name: str | None
) -> None:
    radar_too(monkeypatch=monkeypatch)
    connected(monkeypatch=monkeypatch, usb=[AEOBC])
    assert identify.choose_target(device=None, name=name) == TARGETS[BISCUIT][chosen]


def test_a_name_two_devices_share_is_radar_s_on_a_radar(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    radar = radar_too(monkeypatch=monkeypatch)
    connected(fastboot="RADAR", monkeypatch=monkeypatch)
    assert identify.choose_target(device=None, name="stock") == radar["stock"]
    assert (
        identify.choose_target(device=None, name=None) == (radar["amonet-radar-v1.0.0"])
    )


def test_a_name_two_devices_share_is_refused_on_an_echo_in_its_bootrom(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    radar_too(monkeypatch=monkeypatch)
    connected(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="ERASED", target=identify, value=tmp_path / "erased")
    monkeypatch.setattr(name="short", target=identify.SESSION, value=True)
    monkeypatch.setattr(name="sleep", target=identify.time, value=pytest.fail)
    with pytest.raises(FatalError) as caught:
        identify.choose_target(device=None, name=None)
    assert caught.value.message == (
        "firebreak cannot tell which Echo this is, by its USB product nothing, so"
        " nothing was done. Run it again with --device: biscuit for the Echo Dot"
        " (2nd Generation) or radar for the Echo (2nd Generation)."
    )
    monkeypatch.setattr(name="short", target=identify.SESSION, value=False)
    (tmp_path / "erased").touch()
    with pytest.raises(FatalError, match="cannot tell which Echo"):
        identify.choose_target(device=None, name=None)


def test_a_name_two_devices_share_waits_for_the_echo_to_name_its_device(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    radar = radar_too(monkeypatch=monkeypatch)
    connected(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="ERASED", target=identify, value=tmp_path / "erased")
    monkeypatch.setattr(name="short", target=identify.SESSION, value=False)
    slept: list[float] = []

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) == 2:
            connected(fastboot="RADAR", monkeypatch=monkeypatch)

    monkeypatch.setattr(name="sleep", target=identify.time, value=sleep)
    assert identify.choose_target(device=None, name="stock") == radar["stock"]
    assert slept == [identify.POLL, identify.POLL]
    assert capsys.readouterr().out.count("Waiting for the Echo") == 1


@pytest.mark.parametrize("name", [None, "stock"], ids=["default", "stock"])
def test_a_name_with_no_target_for_the_device_is_refused(
    *, monkeypatch: pytest.MonkeyPatch, name: str | None
) -> None:
    radar_too(monkeypatch=monkeypatch)
    connected(fastboot="CROWN", monkeypatch=monkeypatch)
    with pytest.raises(FatalError) as caught:
        identify.choose_target(device=None, name=name)
    assert caught.value.message == (
        "this is an Echo Show 8 (1st Generation), by its fastboot product CROWN,"
        f" and firebreak has no {name or 'default'} target for it, so nothing was"
        " done."
    )


@pytest.mark.parametrize("name", [None, "stock"], ids=["default", "stock"])
def test_a_named_device_chooses_its_target_on_an_unknown_echo(
    *, monkeypatch: pytest.MonkeyPatch, name: str | None
) -> None:
    radar = radar_too(monkeypatch=monkeypatch)
    connected(monkeypatch=monkeypatch)
    assert (
        identify.choose_target(device=RADAR, name=name)
        == (radar[name or "amonet-radar-v1.0.0"])
    )


def test_a_named_device_is_refused_on_another_device(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    radar_too(monkeypatch=monkeypatch)
    connected(monkeypatch=monkeypatch, usb=[AEOBC])
    with pytest.raises(FatalError) as caught:
        identify.choose_target(device=RADAR, name="stock")
    assert caught.value.message == (
        "this is an Echo Dot (2nd Generation), by its USB product 'AEOBC', and"
        " stock is for the Echo (2nd Generation), so nothing was done."
    )


@pytest.mark.parametrize(
    "error",
    [OSError("ioreg"), subprocess.TimeoutExpired(cmd="ioreg", timeout=30)],
    ids=["missing", "slow"],
)
def test_a_reader_that_fails_lists_nothing(
    *, error: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed() -> list[identify.UsbDevice]:
        raise error

    monkeypatch.setattr(name="platform", target=identify.sys, value="darwin")
    monkeypatch.setattr(name="darwin_devices", target=identify, value=failed)
    assert identify.usb_devices() == []


def test_a_short_serial_is_not_marked_as_cut() -> None:
    usb = dataclasses.replace(AEOBC, serial="AB12")
    assert str(usb).endswith("serial AB12")


@pytest.mark.parametrize(
    argnames=("usb", "title"),
    argvalues=[
        (AEORD, "Echo (2nd Generation)"),
        (dataclasses.replace(AEORD, product="AEOCW"), "Echo Show 8 (1st Generation)"),
    ],
    ids=["radar", "crown"],
)
def test_a_target_for_another_device_is_refused_before_anything_runs(
    *, monkeypatch: pytest.MonkeyPatch, title: str, usb: identify.UsbDevice
) -> None:
    connected(monkeypatch=monkeypatch, usb=[usb])
    with pytest.raises(FatalError, match=f"this is an {re.escape(title)}") as caught:
        identify.check_target(target=TARGETS[BISCUIT]["stock"])
    assert "stock is for the Echo Dot (2nd Generation)" in str(caught.value)


@pytest.mark.parametrize(
    argnames=("product_id", "device"),
    argvalues=[(0xD001, CROWN), (0x4EE2, None)],
    ids=["twrp", "other"],
)
def test_a_twrp_model_names_its_device_only_in_twrp(
    *, device: object, monkeypatch: pytest.MonkeyPatch, product_id: int
) -> None:
    usb = dataclasses.replace(AEORD, product="Echo Show 8", product_id=product_id)
    connected(monkeypatch=monkeypatch, usb=[usb])
    assert identify.identify() == identify.Identity(
        device=device, how="USB product 'Echo Show 8'"
    )


def test_a_usb_device_prints_only_the_start_of_its_serial() -> None:
    assert str(AEOBC) == "0e8d:201c 'MediaTek' 'AEOBC' serial G090..."
    assert str(AEORD) == "18d1:d001 'Amazon' 'Echo (2nd Gen)' serial <none>"
    assert "<none>" in str(
        identify.UsbDevice(
            manufacturer="", product="", product_id=0, serial="", vendor_id=0
        )
    )


def test_android_serial_matches_whatever_its_case(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="usb_devices", target=identify, value=lambda: [AEOBC])
    monkeypatch.setattr(name="USER_SERIAL", target=identify, value=AEOBC.serial.lower())
    assert identify.echo_devices() == [AEOBC]


def test_another_platform_lists_nothing(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="platform", target=identify.sys, value="freebsd")
    assert identify.usb_devices() == []


@pytest.mark.parametrize(
    ("platform", "reader"),
    [
        ("darwin", "darwin_devices"),
        ("linux", "linux_devices"),
        ("win32", "windows_devices"),
    ],
)
def test_each_platform_uses_its_own_reader(
    *, monkeypatch: pytest.MonkeyPatch, platform: str, reader: str
) -> None:
    monkeypatch.setattr(name="platform", target=identify.sys, value=platform)
    monkeypatch.setattr(name=reader, target=identify, value=lambda: [AEOBC])
    assert identify.usb_devices() == [AEOBC]


def test_linux_reads_sysfs(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    dot = tmp_path / "1-1"
    dot.mkdir()
    for name, text in {
        "idProduct": "201c\n",
        "idVendor": "0e8d\n",
        "manufacturer": "MediaTek\n",
        "product": "AEOBC\n",
        "serial": "G090000000000000\n",
    }.items():
        (dot / name).write_text(text)
    (tmp_path / "1-1:1.0").mkdir()
    bare = tmp_path / "2-1"
    bare.mkdir()
    (bare / "idProduct").write_text("0001\n")
    (bare / "idVendor").write_text("05ac\n")
    monkeypatch.setattr(name="SYSFS_USB", target=identify, value=tmp_path)
    assert identify.linux_devices() == [
        AEOBC,
        identify.UsbDevice(
            manufacturer="", product="", product_id=1, serial="", vendor_id=0x05AC
        ),
    ]


def test_linux_without_sysfs_lists_nothing(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="SYSFS_USB", target=identify, value=tmp_path / "none")
    assert identify.linux_devices() == []


@pytest.mark.parametrize(
    "stdout",
    ["ioreg: not found", plistlib.dumps("text").decode()],
    ids=["text", "string"],
)
def test_macos_output_that_is_not_a_device_tree_lists_nothing(
    *, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    answered(monkeypatch=monkeypatch, stdout=stdout)
    assert identify.darwin_devices() == []


def test_macos_reads_the_ioreg_tree(*, monkeypatch: pytest.MonkeyPatch) -> None:
    tree = {
        "IORegistryEntryChildren": [
            {
                "IORegistryEntryChildren": [
                    {
                        "USB Product Name": "AEOBC",
                        "USB Serial Number": "G090000000000000",
                        "USB Vendor Name": "MediaTek",
                        "idProduct": 0x201C,
                        "idVendor": 0x0E8D,
                    },
                    {"IOObjectClass": "hub, no ids"},
                ]
            }
        ]
    }
    asked = answered(monkeypatch=monkeypatch, stdout=plistlib.dumps([tree]).decode())
    assert identify.darwin_devices() == [
        identify.UsbDevice(
            manufacturer="MediaTek",
            product="AEOBC",
            product_id=0x201C,
            serial="G090000000000000",
            vendor_id=0x0E8D,
        )
    ]
    assert asked[0][:2] == ["ioreg", "-a"]


@pytest.mark.parametrize(
    ("usb", "how"),
    [
        ([], "USB product nothing"),
        ([AEOBC, AEORD], "USB product 'AEOBC', 'Echo (2nd Gen)'"),
    ],
    ids=["none", "two"],
)
def test_no_device_or_two_devices_name_none(
    *, how: str, monkeypatch: pytest.MonkeyPatch, usb: list[identify.UsbDevice]
) -> None:
    connected(monkeypatch=monkeypatch, usb=usb)
    assert identify.identify() == identify.Identity(device=None, how=how)


def test_only_the_usb_ids_an_echo_uses_are_counted(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = dataclasses.replace(AEORD, product="Pixel 7", product_id=0x4EE7)
    monkeypatch.setattr(
        name="usb_devices", target=identify, value=lambda: [AEOBC, AEORD, phone]
    )
    assert identify.echo_devices() == [AEOBC, AEORD]


@pytest.mark.parametrize("usb", [[AEOBC, KEYBOARD], []], ids=["biscuit", "nothing"])
def test_the_report_lines_name_the_device_and_its_usb_devices(
    *, monkeypatch: pytest.MonkeyPatch, usb: list[identify.UsbDevice]
) -> None:
    connected(monkeypatch=monkeypatch, usb=usb)
    device = "Echo Dot (2nd Generation), by its USB product 'AEOBC'"
    if not usb:
        device = "not known, by its USB product nothing"
    assert identify.identity_lines() == [
        identify.labelled(label="device", value=device),
        *([identify.labelled(label="usb", value=AEOBC)] if usb else []),
    ]


def test_the_report_lines_read_usb_once(*, monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[int] = []

    def counted() -> list[identify.UsbDevice]:
        reads.append(1)
        return [AEOBC]

    connected(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="usb_devices", target=identify, value=counted)
    assert len(identify.identity_lines()) == 2
    assert reads == [1]


def test_windows_reads_the_bus_reported_name(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = answered(
        monkeypatch=monkeypatch,
        stdout="USB\\VID_0E8D&PID_201C\\G090000000000000\tAEOBC\r\n"
        "USB\\VID_18D1&PID_D001\\6&2A1B3C&0&2\tEcho (2nd Gen)\n"
        "USB\\VID_ZZZZ&PID_0001\\X\tbad\n"
        "USB\\ROOT_HUB30\\4&1\t\n"
        "noise\n",
    )
    assert identify.windows_devices() == [
        identify.UsbDevice(
            manufacturer="",
            product="AEOBC",
            product_id=0x201C,
            serial="G090000000000000",
            vendor_id=0x0E8D,
        ),
        dataclasses.replace(AEORD, manufacturer=""),
    ]
    assert asked[0][:4] == ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive"]


def test_with_android_serial_only_that_device_counts(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    connected(monkeypatch=monkeypatch, usb=[AEOBC, AEORD])
    monkeypatch.setattr(name="USER_SERIAL", target=identify, value=AEOBC.serial)
    assert identify.identify() == identify.Identity(
        device=BISCUIT, how="USB product 'AEOBC'"
    )
