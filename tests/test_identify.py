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
from firebreak.unlocks.targets import TARGETS

if TYPE_CHECKING:
    import pathlib

AEOBC = identify.UsbDevice(
    manufacturer="MediaTek",
    product="AEOBC",
    product_id=0x201C,
    serial="G090LF0964230U8T",
    vendor_id=0x0E8D,
)
AEORD = identify.UsbDevice(
    manufacturer="Amazon",
    product="Echo (2nd Gen)",
    product_id=0xD001,
    serial="",
    vendor_id=0x18D1,
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
    identify.check_target(target=TARGETS["stock"])


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
        identify.check_target(target=TARGETS["stock"])
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
        "serial": "G090LF0964230U8T\n",
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
                        "USB Serial Number": "G090L90971660D6B",
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
            serial="G090L90971660D6B",
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
        stdout="USB\\VID_0E8D&PID_201C\\G090LF0965270NJ3\tAEOBC\r\n"
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
            serial="G090LF0965270NJ3",
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
