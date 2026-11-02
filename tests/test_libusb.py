from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING, Any

import pytest

from firebreak.mediatek import libusb

if TYPE_CHECKING:
    from collections.abc import Callable

PACKET = 8


class FakeDevice:
    def __init__(self, *, data: object = None, disposed: bool = False) -> None:
        self.data = data
        self.disposed = disposed
        self.transfers: list[tuple[int, int, int, bytes]] = []

    def ctrl_transfer(
        self,
        request_type: int,
        request: int,
        value: int,
        index: int,
        payload: object,
    ) -> object:
        assert index == 0
        if isinstance(payload, int):
            self.transfers.append((request_type, request, value, b""))
            return bytearray(range(payload))
        self.transfers.append((request_type, request, value, bytes(payload)))
        return len(bytes(payload))

    def get_active_configuration(self) -> object:
        return self.data


class FakeEndpoint:
    def __init__(self, *, address: int, replies: bytes = b"") -> None:
        self.bEndpointAddress = address
        self.replies = bytearray(replies)
        self.timeouts = 0
        self.wMaxPacketSize = PACKET
        self.written: list[bytes] = []

    def read(self, size: int, timeout: int) -> bytes:
        assert timeout > 0
        if not self.replies:
            self.timeouts += 1
            message = "nothing to read"
            raise FakeTimeoutError(message)
        taken = bytes(self.replies[:size])
        del self.replies[: len(taken)]
        return taken

    def write(self, data: bytes, timeout: int) -> int:
        assert timeout > 0
        self.written.append(bytes(data))
        return len(data)


class FakeNoBackendError(ValueError):
    pass


class FakeUsbError(OSError):
    pass


class FakeTimeoutError(FakeUsbError):
    pass


def fake_usb(
    *,
    device: object,
    find: Callable[..., object] | None = None,
    interface: object = None,
) -> types.SimpleNamespace:
    def find_descriptor(holder: object, **options: object) -> object:
        if "bInterfaceClass" in options:
            return interface
        match = options["custom_match"]
        assert callable(match)
        return next(
            (
                endpoint
                for endpoint in getattr(holder, "endpoints", ())
                if match(endpoint)
            ),
            None,
        )

    def dispose(target: object) -> None:
        assert isinstance(target, FakeDevice)
        if target.disposed:
            message = "already disposed"
            raise FakeUsbError(message)
        target.disposed = True

    core = types.SimpleNamespace(
        NoBackendError=FakeNoBackendError,
        USBError=FakeUsbError,
        USBTimeoutError=FakeTimeoutError,
        find=find if find is not None else lambda **_: device,
    )
    util = types.SimpleNamespace(
        ENDPOINT_IN=libusb.ENDPOINT_IN,
        ENDPOINT_OUT=0,
        dispose_resources=dispose,
        endpoint_direction=lambda address: address & libusb.ENDPOINT_IN,
        find_descriptor=find_descriptor,
    )
    return types.SimpleNamespace(core=core, util=util)


def interfaced(*, replies: bytes = b"") -> tuple[Any, FakeDevice, Any]:
    inward = FakeEndpoint(address=0x81, replies=replies)
    outward = FakeEndpoint(address=0x01)
    interface = types.SimpleNamespace(bInterfaceNumber=1, endpoints=(inward, outward))
    device = FakeDevice(data=interface)
    return interface, device, (inward, outward)


def patch_usb(
    *,
    device: object,
    find: Callable[..., object] | None = None,
    interface: object = None,
    monkeypatch: pytest.MonkeyPatch,
) -> types.SimpleNamespace:
    fake = fake_usb(device=device, find=find, interface=interface)
    monkeypatch.setattr(name="pyusb", target=libusb, value=lambda: fake)
    return fake


def ported(
    *, monkeypatch: pytest.MonkeyPatch, replies: bytes = b""
) -> tuple[libusb.Usb, FakeDevice, Any]:
    interface, device, pair = interfaced(replies=replies)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    inward, outward = pair
    return (
        libusb.Usb(device=device, inward=inward, outward=outward, timeout=0.01),
        device,
        pair,
    )


def test_a_device_with_no_cdc_interface_is_named() -> None:
    assert libusb.CDC_DATA_CLASS == 0x0A


def test_chunked_never_yields_more_than_the_transfer_limit() -> None:
    chunks = list(libusb.chunked(data=bytes(0x9000), limit=0x40))
    assert len(chunks) == 3
    assert [len(chunk) for chunk in chunks] == [0x4000, 0x4000, 0x1000]
    assert list(libusb.chunked(data=b"", limit=0x40)) == []


def test_close_swallows_a_dispose_that_fails(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, device, _ = ported(monkeypatch=monkeypatch)
    port.held = b"left over"
    port.close()
    assert device.disposed
    assert port.held == b""
    port.close()


def test_control_reads_and_writes(*, monkeypatch: pytest.MonkeyPatch) -> None:
    port, device, _ = ported(monkeypatch=monkeypatch)
    assert port.line_coding() == bytes(range(libusb.LINE_CODING_SIZE))
    assert port.configuration_descriptor() == bytes(range(libusb.DESCRIPTOR_SIZE))
    port.set_line_coding(data=b"sevenxx")
    assert device.transfers == [
        (libusb.TO_INTERFACE | libusb.FROM_DEVICE, libusb.READ_LINE_CODING, 0, b""),
        (
            libusb.FROM_DEVICE,
            libusb.DESCRIPTOR_REQUEST,
            libusb.CONFIGURATION_DESCRIPTOR,
            b"",
        ),
        (libusb.TO_INTERFACE, libusb.SET_LINE_CODING, 0, b"sevenxx"),
    ]


def test_endpoints_needs_a_cdc_data_interface(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    device = FakeDevice()
    patch_usb(device=device, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotThereError, match="CDC data"):
        libusb.endpoints(device=device)


def test_endpoints_needs_a_pair_of_bulk_endpoints(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface = types.SimpleNamespace(
        bInterfaceNumber=1, endpoints=(FakeEndpoint(address=0x81),)
    )
    device = FakeDevice(data=interface)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotThereError, match="bulk endpoints"):
        libusb.endpoints(device=device)


def test_open_bootrom_hands_back_a_port(*, monkeypatch: pytest.MonkeyPatch) -> None:
    interface, device, (inward, outward) = interfaced()
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    port = libusb.open_bootrom()
    assert port.device is device
    assert port.inward is inward
    assert port.outward is outward


def test_open_bootrom_says_when_libusb_is_missing(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(**_: object) -> object:
        message = "no backend available"
        raise FakeNoBackendError(message)

    patch_usb(device=None, find=refuse, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NoLibusbError, match="brew install"):
        libusb.open_bootrom()


def test_open_bootrom_says_when_nothing_answers(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_usb(device=None, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotThereError, match="0e8d:0003"):
        libusb.open_bootrom()


def test_pyusb_imports_the_real_module() -> None:
    found = libusb.pyusb()
    assert found.core.find is not None
    assert found.util.find_descriptor is not None


def test_pyusb_says_when_it_is_not_installed(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "usb", None)
    monkeypatch.setitem(sys.modules, "usb.core", None)
    with pytest.raises(expected_exception=libusb.NoPyusbError, match="pip install"):
        libusb.pyusb()


def test_read_buffers_what_it_did_not_ask_for(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, _ = ported(monkeypatch=monkeypatch, replies=b"0123456789abcdef")
    assert port.read(size=3) == b"012"
    assert port.held == b"34567"
    assert port.read(size=9) == b"3456789ab"
    assert port.read(size=5) == b"cdef"


def test_read_returns_short_rather_than_spinning(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, (inward, _) = ported(monkeypatch=monkeypatch, replies=b"ab")
    assert port.read(size=4) == b"ab"
    assert port.read(size=4) == b""
    assert inward.timeouts == 1


def test_reset_input_buffer_drains_and_keeps_the_timeout(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, (inward, _) = ported(monkeypatch=monkeypatch, replies=b"stale bytes here")
    port.held = b"held too"
    port.reset_input_buffer()
    assert port.held == b""
    assert inward.replies == bytearray()
    assert port.timeout == pytest.approx(0.01)


def test_write_chunks_by_the_packet_size(*, monkeypatch: pytest.MonkeyPatch) -> None:
    port, _, (_, outward) = ported(monkeypatch=monkeypatch)
    assert port.write(data=bytes(0x4008)) == 0x4008
    assert [len(chunk) for chunk in outward.written] == [0x4000, 8]
