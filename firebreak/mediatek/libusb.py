from __future__ import annotations

import contextlib
import types
from typing import TYPE_CHECKING, Any

from firebreak.mediatek.usbdl import (
    MEDIATEK_VENDOR_ID,
    READ_TIMEOUT,
    ProductId,
    UsbdlError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

CDC_DATA_CLASS = 0x0A
CONFIGURATION_DESCRIPTOR = 0x0200
DESCRIPTOR_REQUEST = 0x06
DESCRIPTOR_SIZE = 9
DRAIN_TIMEOUT = 0.05
ENDPOINT_IN = 0x80
FROM_DEVICE = 0x80
LINE_CODING_SIZE = 7
MILLISECONDS = 1000
READ_LINE_CODING = 0x21
SET_LINE_CODING = 0x20
TO_INTERFACE = 0x21
TRANSFER_LIMIT = 0x4000


class NoLibusbError(UsbdlError):
    pass


class NoPyusbError(UsbdlError):
    pass


class NotThereError(UsbdlError):
    pass


class Usb:
    def __init__(
        self,
        *,
        device: Any,  # ruff: ignore[any-type]
        inward: Any,  # ruff: ignore[any-type]
        outward: Any,  # ruff: ignore[any-type]
        timeout: float = READ_TIMEOUT,
    ) -> None:
        self.device = device
        self.held = b""
        self.inward = inward
        self.outward = outward
        self.timeout = timeout

    def _gathered(self, *, size: int) -> bytes:
        core = pyusb()
        try:
            return bytes(bytearray(self.inward.read(size, self._milliseconds())))
        except core.core.USBTimeoutError:
            return b""

    def _milliseconds(self) -> int:
        return max(1, int(self.timeout * MILLISECONDS))

    def close(self) -> None:
        core = pyusb()
        self.held = b""
        with contextlib.suppress(core.core.USBError):
            core.util.dispose_resources(self.device)

    def configuration_descriptor(self) -> bytes:
        return self.control(
            length=DESCRIPTOR_SIZE,
            request=DESCRIPTOR_REQUEST,
            request_type=FROM_DEVICE,
            value=CONFIGURATION_DESCRIPTOR,
        )

    def control(
        self,
        *,
        data: bytes = b"",
        length: int = 0,
        request: int,
        request_type: int,
        value: int = 0,
    ) -> bytes:
        held = self.device.ctrl_transfer(
            request_type, request, value, 0, length or data
        )
        return bytes(bytearray(held)) if length else b""

    def line_coding(self) -> bytes:
        return self.control(
            length=LINE_CODING_SIZE,
            request=READ_LINE_CODING,
            request_type=TO_INTERFACE | FROM_DEVICE,
        )

    def read(self, *, size: int) -> bytes:
        if len(self.held) < size:
            packet = self.inward.wMaxPacketSize
            want = -(-(size - len(self.held)) // packet) * packet
            self.held += self._gathered(size=min(want, TRANSFER_LIMIT))
        got, self.held = self.held[:size], self.held[size:]
        return got

    def reset_input_buffer(self) -> None:
        self.held = b""
        was, self.timeout = self.timeout, DRAIN_TIMEOUT
        try:
            while self._gathered(size=self.inward.wMaxPacketSize):
                pass
        finally:
            self.timeout = was

    def set_line_coding(self, *, data: bytes) -> None:
        self.control(data=data, request=SET_LINE_CODING, request_type=TO_INTERFACE)

    def write(self, *, data: bytes) -> int | None:
        for chunk in chunked(data=data, limit=self.outward.wMaxPacketSize):
            self.outward.write(chunk, self._milliseconds())
        return len(data)


def chunked(*, data: bytes, limit: int) -> Iterator[bytes]:
    step = max(limit, TRANSFER_LIMIT // limit * limit)
    for index in range(0, len(data), step):
        yield data[index : index + step]


def endpoints(*, device: Any) -> tuple[Any, Any, Any]:  # ruff: ignore[any-type]
    core = pyusb()
    data = core.util.find_descriptor(
        device.get_active_configuration(), bInterfaceClass=CDC_DATA_CLASS
    )
    if data is None:
        message = "the bootrom offers no CDC data interface"
        raise NotThereError(message)
    inward, outward = (
        facing(core=core, data=data, wanted=wanted)
        for wanted in (core.util.ENDPOINT_IN, core.util.ENDPOINT_OUT)
    )
    if inward is None or outward is None:
        message = "the bootrom's data interface has no pair of bulk endpoints"
        raise NotThereError(message)
    return data, inward, outward


def facing(*, core: Any, data: Any, wanted: int) -> Any:  # ruff: ignore[any-type]
    return core.util.find_descriptor(
        data,
        custom_match=lambda each: (
            core.util.endpoint_direction(each.bEndpointAddress) == wanted
        ),
    )


def open_bootrom(*, timeout: float = READ_TIMEOUT) -> Usb:
    core = pyusb()
    try:
        device = core.core.find(
            idProduct=ProductId.BOOTROM, idVendor=MEDIATEK_VENDOR_ID
        )
    except core.core.NoBackendError as error:
        message = (
            f"libusb is not installed, so this run cannot speak raw USB: {error}."
            " On macOS `brew install libusb` provides it, and on Linux it is the"
            " libusb-1.0 package."
        )
        raise NoLibusbError(message) from error
    if device is None:
        message = f"no {MEDIATEK_VENDOR_ID:04x}:{ProductId.BOOTROM:04x} answered libusb"
        raise NotThereError(message)
    _, inward, outward = endpoints(device=device)
    return Usb(device=device, inward=inward, outward=outward, timeout=timeout)


def pyusb() -> Any:  # ruff: ignore[any-type]
    try:
        from usb import core, util  # ruff: ignore[import-outside-top-level]
    except ImportError as error:
        message = (
            "pyusb is not installed, so this run cannot speak raw USB:"
            f" {error}. `pip install pyusb` provides it."
        )
        raise NoPyusbError(message) from error
    return types.SimpleNamespace(core=core, util=util)
