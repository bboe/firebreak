from __future__ import annotations

import base64
import dataclasses
import pathlib
import plistlib
import subprocess
import sys
import xml.parsers.expat
from typing import TYPE_CHECKING

from firebreak.devices import DEVICES
from firebreak.host import USER_SERIAL, command, getvar, in_fastboot
from firebreak.report import labelled
from firebreak.ui import FatalError

if TYPE_CHECKING:
    from firebreak.plugin import Device, Target

ECHO_IDS = frozenset({(0x0BB4, 0x0C01), (0x18D1, 0x4EE2), (0x18D1, 0xD001)})
ECHO_VENDORS = frozenset({0x0E8D, 0x1949})
INSTANCE_PARTS = 3
SERIAL_SHOWN = 4
SYSFS_USB = pathlib.Path("/sys/bus/usb/devices")
USB_TIMEOUT = 30
WINDOWS_QUERY = r"""$ProgressPreference = "SilentlyContinue"
$key = "DEVPKEY_Device_BusReportedDeviceDesc"
Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
  Where-Object { $_.InstanceId -match "^USB\\VID_[0-9A-F]{4}&PID_[0-9A-F]{4}\\" } |
  ForEach-Object {
    $id = $_.InstanceId
    $bus = Get-PnpDeviceProperty -InstanceId $id -KeyName $key -ErrorAction Ignore
    "{0}`t{1}" -f $id, $bus.Data
  }"""


@dataclasses.dataclass(frozen=True)
class Identity:
    device: Device | None
    how: str


@dataclasses.dataclass(frozen=True)
class UsbDevice:
    manufacturer: str
    product: str
    product_id: int
    serial: str
    vendor_id: int

    def __str__(self) -> str:
        serial = self.serial[:SERIAL_SHOWN] or "<none>"
        if len(self.serial) > SERIAL_SHOWN:
            serial += "..."
        return (
            f"{self.vendor_id:04x}:{self.product_id:04x}"
            f" {self.manufacturer or '<none>'!r} {self.product or '<none>'!r}"
            f" serial {serial}"
        )


def check_target(*, target: Target) -> None:
    identity = identify()
    if identity.device is None or identity.device == target.device:
        return
    raise FatalError(
        message=f"this is an {identity.device.title}, by its {identity.how}, and"
        f" {target.name} is for the {target.device.title}, so nothing was done."
    )


def darwin_devices() -> list[UsbDevice]:
    said = stdout_of(arguments=["ioreg", "-a", "-l", "-p", "IOUSB", "-w", "0"])
    try:
        tree = plistlib.loads(said.encode())
    except (plistlib.InvalidFileException, ValueError, xml.parsers.expat.ExpatError):
        return []
    return [
        UsbDevice(
            manufacturer=node.get("USB Vendor Name", ""),
            product=node.get("USB Product Name", ""),
            product_id=node["idProduct"],
            serial=node.get("USB Serial Number", ""),
            vendor_id=node["idVendor"],
        )
        for node in walked(node=tree)
        if "idVendor" in node and "idProduct" in node
    ]


def echo_devices() -> list[UsbDevice]:
    return [
        usb
        for usb in usb_devices()
        if (
            usb.vendor_id in ECHO_VENDORS or (usb.vendor_id, usb.product_id) in ECHO_IDS
        )
        and (not USER_SERIAL or usb.serial.casefold() == USER_SERIAL.casefold())
    ]


def identify(*, found: list[UsbDevice] | None = None) -> Identity:
    if in_fastboot():
        product = getvar(name="product")
        device = next((device for device in DEVICES if device.product == product), None)
        return Identity(device=device, how=f"fastboot product {product or '<none>'}")
    if found is None:
        found = echo_devices()
    named = {
        device for device in DEVICES for usb in found if usb.product in device.models
    }
    products = ", ".join(sorted({repr(usb.product) for usb in found})) or "nothing"
    return Identity(
        device=named.pop() if len(named) == 1 else None,
        how=f"USB product {products}",
    )


def identity_lines() -> list[str]:
    found = echo_devices()
    identity = identify(found=found)
    title = identity.device.title if identity.device else "not known"
    return [labelled(label="device", value=f"{title}, by its {identity.how}")] + [
        labelled(label="usb", value=usb) for usb in found
    ]


def linux_devices() -> list[UsbDevice]:
    found = []
    for node in sorted(SYSFS_USB.glob("*")) if SYSFS_USB.is_dir() else []:
        try:
            vendor_id = int((node / "idVendor").read_text(encoding="ascii"), 16)
            product_id = int((node / "idProduct").read_text(encoding="ascii"), 16)
        except (OSError, ValueError):
            continue
        found.append(
            UsbDevice(
                manufacturer=sysfs_text(path=node / "manufacturer"),
                product=sysfs_text(path=node / "product"),
                product_id=product_id,
                serial=sysfs_text(path=node / "serial"),
                vendor_id=vendor_id,
            )
        )
    return found


def stdout_of(*, arguments: list[str]) -> str:
    return (
        command(
            arguments=[*arguments],
            standard_error=subprocess.DEVNULL,
            standard_input=subprocess.DEVNULL,
            standard_output=subprocess.PIPE,
            timeout=USB_TIMEOUT,
        )
        .stdout.decode(encoding="utf-8", errors="replace")
        .replace("\r", "")
    )


def sysfs_text(*, path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def usb_devices() -> list[UsbDevice]:
    readers = {
        "darwin": darwin_devices,
        "linux": linux_devices,
        "win32": windows_devices,
    }
    reader = readers.get(sys.platform)
    if reader is None:
        return []
    try:
        return reader()
    except (OSError, subprocess.TimeoutExpired):
        return []


def walked(*, node: object) -> list[dict]:
    if isinstance(node, list):
        return [found for child in node for found in walked(node=child)]
    if not isinstance(node, dict):
        return []
    return [node, *walked(node=node.get("IORegistryEntryChildren", []))]


def windows_devices() -> list[UsbDevice]:
    encoded = base64.b64encode(WINDOWS_QUERY.encode(encoding="utf-16-le")).decode()
    said = stdout_of(
        arguments=[
            "powershell",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ]
    )
    found = []
    for row in said.splitlines():
        instance, _, product = row.partition("\t")
        parts = instance.split("\\")
        if len(parts) != INSTANCE_PARTS or not parts[1].startswith("VID_"):
            continue
        ids = dict(part.split("_", 1) for part in parts[1].split("&") if "_" in part)
        try:
            vendor_id, product_id = int(ids["VID"], 16), int(ids["PID"], 16)
        except (KeyError, ValueError):
            continue
        found.append(
            UsbDevice(
                manufacturer="",
                product=product.strip(),
                product_id=product_id,
                serial=parts[2] if "&" not in parts[2] else "",
                vendor_id=vendor_id,
            )
        )
    return found
