from __future__ import annotations

import base64
import dataclasses
import pathlib
import plistlib
import subprocess
import sys
import time
import xml.parsers.expat
from typing import TYPE_CHECKING

from firebreak.cache import ERASED, HELD
from firebreak.devices import DEFAULTS, DEPRECATED, DEVICES, TARGETS, biscuit
from firebreak.host import (
    USER_SERIAL,
    adb_shell,
    command,
    getvar,
    in_fastboot,
    run,
    usb_serial,
)
from firebreak.report import labelled, whole
from firebreak.targets import REMOVED_IN
from firebreak.ui import SESSION, FatalError, warn

if TYPE_CHECKING:
    from firebreak.plugin import Device, Target

ECHO_IDS = frozenset({(0x0BB4, 0x0C01), (0x18D1, 0x4EE2), (0x18D1, 0xD001)})
ECHO_VENDORS = frozenset({0x0E8D, 0x1949})
FASTBOOT_ID = (0x0BB4, 0x0C01)
INSTANCE_PARTS = 3
NAMED = "device-named"
NAME_POLLS = 30
POLL = 2
SERIAL_SHOWN = 4
SYSFS_USB = pathlib.Path("/sys/bus/usb/devices")
TWRP_ID = (0x18D1, 0xD001)
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


def bootrom_target(*, choices: list[Target]) -> Target | None:
    device = biscuit.UNLOCK_FROM_BOOTROM.device
    return next((each for each in choices if each.device == device), None)


def check_target(*, target: Target) -> None:
    identity = identify()
    if identity.device is None or identity.device == target.device:
        return
    raise FatalError(
        message=f"this is an {identity.device.title}, by its {identity.how}, and"
        f" {target.name} is for the {target.device.title}, so nothing was done."
    )


def choose_target(*, device: Device | None, name: str | None) -> Target:
    was = DEPRECATED.get(name or "")
    if was is not None:
        warn(
            text=f"`{name}` goes away in firebreak {REMOVED_IN}: use"
            f" `firebreak unlock {was.name}` instead, which always takes the"
            " newest amonet this supports." + (" " + was.note if was.note else "")
        )
        device, name = was.device, was.name
    choices = [
        targets[wanted]
        for each, targets in TARGETS.items()
        if device in {None, each} and (wanted := name or DEFAULTS.get(each)) in targets
    ]
    if len(choices) == 1:
        check_target(target=choices[0])
        return choices[0]
    devices = " or ".join(
        f"{target.device.name} for the {target.device.title}" for target in choices
    )
    identity = named_device(devices=devices)
    found, how = identity.device, identity.how
    marker = next((each for each in (ERASED, HELD) if each.exists()), None)
    if found is None and marker is not None:
        marked = marker.read_text().strip()
        found = next((each for each in DEVICES if each.name == marked), None)
        if found is not None:
            how = f"the device named in {marker.name}"
    for target in choices:
        if target.device == found:
            return target
    if found is None and SESSION.short:
        shorted = bootrom_target(choices=choices)
        if shorted is not None:
            return shorted
    if found is None:
        raise FatalError(
            message=f"firebreak cannot tell which Echo this is, by its"
            f" {identity.how}, so nothing was done. Run it again with --device:"
            f" {devices}."
        )
    raise FatalError(
        message=f"this is an {found.title}, by its {how}, and firebreak has no"
        f" {name or 'default'} target for it, so nothing was done."
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


def fastboot_driver_missing() -> bool:
    return (
        sys.platform == "win32"
        and any(
            (usb.vendor_id, usb.product_id) == FASTBOOT_ID for usb in echo_devices()
        )
        and not in_fastboot()
    )


def identify(*, found: list[UsbDevice] | None = None) -> Identity:
    if in_fastboot():
        product = getvar(name="product")
        device = next((device for device in DEVICES if device.product == product), None)
        return Identity(device=device, how=f"fastboot product {product or '<none>'}")
    if found is None:
        found = echo_devices()
    named = {
        device
        for device in DEVICES
        for usb in found
        if usb.product in device.models
        or (
            usb.product in device.twrp_models
            and (usb.vendor_id, usb.product_id) == TWRP_ID
        )
    }
    products = ", ".join(sorted({repr(usb.product) for usb in found})) or "nothing"
    if not named and usb_serial():
        said = recovery_device()
        if said:
            named = {device for device in DEVICES if device.name == said}
            products = f"{products}, and recovery's ro.product.device {said!r}"
    return Identity(
        device=named.pop() if len(named) == 1 else None,
        how=f"USB product {products}",
    )


def identity_lines() -> list[str]:
    found = echo_devices()
    identity = identify(found=found)
    if identity.device:
        SESSION.named = identity.device.title
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


def named_device(*, devices: str) -> Identity:
    identity = identify()
    polls = 0
    while identity.device is None and not (
        SESSION.short or ERASED.exists() or HELD.exists()
    ):
        if polls == NAME_POLLS:
            warn(
                text="Waiting for the Echo to say which device it is, which it"
                " does in fastboot and in a recovery. This goes on by itself once"
                " it does. An Echo that shows no light never says, and needs"
                f" --device instead: {devices}."
            )
        polls += 1
        time.sleep(POLL)
        identity = identify()
    return identity


def recovery_device() -> str | None:
    try:
        state = run(arguments=["adb", "get-state"], timeout=USB_TIMEOUT).stdout
        if state.strip() != "recovery":
            return None
        return whole(
            marker=NAMED,
            said=adb_shell(
                command=f"getprop ro.product.device; echo {NAMED}",
                timeout=USB_TIMEOUT,
            ),
        )
    except subprocess.TimeoutExpired:
        return None


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
