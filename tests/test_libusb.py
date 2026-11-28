from __future__ import annotations

import errno
import sys
import types
from typing import TYPE_CHECKING, Any

import pytest
from usb.backend import libusb1

from firebreak.mediatek import libusb

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

PACKET = 8


class FakeDevice:
    def __init__(
        self, *, data: object = None, disposed: bool = False, refuse: bool = False
    ) -> None:
        self._ctx = types.SimpleNamespace(managed_claim_interface=claim_refused)
        self.data = data
        self.detached: list[int] = []
        self.disposed = disposed
        self.held = False
        self.refuse = refuse
        self.refuse_detach = False
        self.transfers: list[tuple[int, int, int, int]] = []
        self.unsupported = False

    def allow_claims(self) -> None:
        self._ctx.managed_claim_interface = lambda *_: None

    def ctrl_transfer(
        self,
        request_type: int,
        request: int,
        value: int,
        index: int,
        payload: object,
        *_: int,
    ) -> object:
        self._ctx.managed_claim_interface(self, index & 0xFF)
        self.transfers.append((request_type, request, value, index))
        if self.refuse:
            message = "the device went away"
            raise FakeUsbError(message)
        return payload

    def detach_kernel_driver(self, interface: int) -> None:
        if self.refuse_detach:
            message = "[Errno 16] Resource busy"
            raise FakeUsbError(message)
        self.detached.append(interface)

    def get_active_configuration(self) -> object:
        return self.data

    def is_kernel_driver_active(self, interface: int) -> bool:
        if self.unsupported:
            message = "not implemented on this platform"
            raise NotImplementedError(message)
        assert interface >= 0
        return self.held


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


class Unconfigured(FakeDevice):
    def __init__(self, *, data: object) -> None:
        super().__init__(data=data)
        self.configured = False

    def get_active_configuration(self) -> object:
        if not self.configured:
            message = "Configuration not set"
            raise FakeUsbError(message)
        return self.data

    def set_configuration(self) -> None:
        self.configured = True


@pytest.fixture(autouse=True)
def fresh_backend(*, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(name="USBDK", target=libusb, value=False)
    cached = libusb.backend
    cached.cache_clear()
    yield
    cached.cache_clear()


def claim_refused(device: object, interface: int) -> None:
    message = f"no interface {interface} to claim on {device}"
    raise FakeUsbError(message)


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
        ENDPOINT_IN=libusb.FROM_DEVICE,
        ENDPOINT_OUT=0,
        dispose_resources=dispose,
        endpoint_direction=lambda address: address & libusb.FROM_DEVICE,
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


def test_a_backend_is_left_to_pyusb_off_windows(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="USBDK", target=libusb, value=False)
    assert libusb.backend() is None


def test_a_backend_on_windows_asks_libusb_for_usbdk(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    options: list[tuple[object, int]] = []

    class SetOption:
        def __init__(self) -> None:
            self.argtypes: list[object] = []

        def __call__(self, context: object, option: int) -> int:
            options.append((context, option))
            return 0

    chosen = types.SimpleNamespace(
        ctx="context", lib=types.SimpleNamespace(libusb_set_option=SetOption())
    )
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="get_backend", target=libusb1, value=lambda: chosen)
    assert libusb.backend() is chosen
    assert options == [("context", libusb.USE_USBDK)]


def test_a_backend_on_windows_asks_libusb_for_usbdk_once(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    class SetOption:
        def __init__(self) -> None:
            self.argtypes: list[object] = []

        def __call__(self, *_: object) -> int:
            calls.append(1)
            return 0

    chosen = types.SimpleNamespace(
        ctx="context", lib=types.SimpleNamespace(libusb_set_option=SetOption())
    )
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="get_backend", target=libusb1, value=lambda: chosen)
    assert libusb.backend() is libusb.backend() is chosen
    assert calls == [1]


def test_a_backend_on_windows_refuses_a_libusb_too_old_for_usbdk(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = types.SimpleNamespace(ctx="context", lib=types.SimpleNamespace())
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="get_backend", target=libusb1, value=lambda: old)
    with pytest.raises(expected_exception=libusb.NoLibusbError, match=r"1\.0\.22"):
        libusb.backend()


def test_a_backend_on_windows_says_when_usbdk_does_not_answer(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Refused:
        def __init__(self) -> None:
            self.argtypes: list[object] = []

        def __call__(self, *_: object) -> int:
            return -5

    chosen = types.SimpleNamespace(
        ctx="context", lib=types.SimpleNamespace(libusb_set_option=Refused())
    )
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="get_backend", target=libusb1, value=lambda: chosen)
    with pytest.raises(expected_exception=libusb.NotPermittedError, match="UsbDk"):
        libusb.backend()


def test_a_backend_on_windows_with_no_libusb_says_how_to_install_it(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="get_backend", target=libusb1, value=lambda: None)
    with pytest.raises(expected_exception=libusb.NoLibusbError, match="#windows"):
        libusb.backend()


def test_a_device_with_no_cdc_interface_is_named() -> None:
    assert libusb.CDC_DATA_CLASS == 0x0A


def test_authorize_asks_sudo_only_where_the_trigger_needs_it(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def run(arguments: list[str], **_: object) -> object:
        asked.append(arguments)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(name="run", target=libusb.subprocess, value=run)
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    assert libusb.authorize() is True
    assert asked == []
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=True)
    assert libusb.authorize() is True
    assert asked == [["sudo", "-v"]]


def test_authorized_already_asks_sudo_without_a_prompt(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def run(arguments: list[str], **_: object) -> object:
        asked.append(arguments)
        return types.SimpleNamespace(returncode=1)

    monkeypatch.setattr(name="run", target=libusb.subprocess, value=run)
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    assert libusb.authorized_already() is True
    assert asked == []
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=True)
    assert libusb.authorized_already() is False
    assert asked == [["sudo", "-n", "-v"]]


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


def test_control_in_returns_bytes_and_control_out_goes_to_the_interface(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, device, _ = ported(monkeypatch=monkeypatch)
    device.allow_claims()
    assert (
        port.control_in(index=0, length=3, request=0x21, request_type=0xA1, value=0)
        == b"\x00\x00\x00"
    )
    port.control_out(data=b"\x01\x02", index=0, request=0x20, value=0)
    assert device.transfers == [(0xA1, 0x21, 0, 0), (libusb.TO_INTERFACE, 0x20, 0, 0)]


def test_elevated_runs_the_helper_with_the_index(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[list[str]] = []

    def run(arguments: list[str], **_: object) -> object:
        asked.append(arguments)
        return types.SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(name="run", target=libusb.subprocess, value=run)
    libusb.elevated(index=0xCC)
    assert asked[0][0] == "sudo"
    assert asked[0][2] == "-c"
    assert asked[0][3] == libusb.TRIGGER
    assert asked[0][4] == "204"


def test_elevated_says_when_the_privileged_helper_will_not_run(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="run",
        target=libusb.subprocess,
        value=lambda *_, **__: types.SimpleNamespace(
            returncode=1, stderr="sudo: a password is required", stdout=""
        ),
    )
    with pytest.raises(
        expected_exception=libusb.NotPermittedError, match="a password is required"
    ):
        libusb.elevated(index=0xCC)


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


def test_open_bootrom_asks_nothing_of_a_driver_where_a_helper_sends_the_trigger(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    device.held = True
    device.refuse_detach = True
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=True)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    assert libusb.open_bootrom() is not None
    assert device.detached == []


def test_open_bootrom_configures_a_bootrom_usbdk_hands_over_unset(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, _, (inward, outward) = interfaced()
    device = Unconfigured(data=interface)
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="backend", target=libusb, value=lambda: None)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    port = libusb.open_bootrom()
    assert device.configured
    assert port.inward is inward
    assert port.outward is outward


def test_open_bootrom_hands_back_a_port(*, monkeypatch: pytest.MonkeyPatch) -> None:
    interface, device, (inward, outward) = interfaced()
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    port = libusb.open_bootrom()
    assert port.device is device
    assert port.inward is inward
    assert port.outward is outward


def test_open_bootrom_leaves_a_platform_with_no_detaching_alone(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    device.unsupported = True
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    assert libusb.open_bootrom() is not None
    assert device.detached == []


def test_open_bootrom_leaves_an_unconfigured_bootrom_alone_off_windows(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, _, _ = interfaced()
    device = Unconfigured(data=interface)
    monkeypatch.setattr(name="USBDK", target=libusb, value=False)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    with pytest.raises(
        expected_exception=libusb.NotPermittedError, match="Configuration not set"
    ):
        libusb.open_bootrom()
    assert not device.configured


def test_open_bootrom_lets_go_of_a_device_it_cannot_use(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface = types.SimpleNamespace(bInterfaceNumber=1, endpoints=())
    device = FakeDevice(data=interface)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotThereError, match="bulk endpoints"):
        libusb.open_bootrom()
    assert device.disposed


def test_open_bootrom_names_a_bootrom_gone_from_usb_without_the_udev_rules(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def gone(**_: object) -> object:
        raise FakeUsbError(
            errno.ENODEV, "No such device (it may have been disconnected)"
        )

    device = FakeDevice()
    monkeypatch.setattr(name="get_active_configuration", target=device, value=gone)
    patch_usb(device=device, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="platform", target=sys, value="linux")
    with pytest.raises(libusb.NotPermittedError, match="No such device") as stopped:
        libusb.open_bootrom()
    assert not isinstance(stopped.value, libusb.NoAccessError)


def test_open_bootrom_on_windows_points_at_usbdk_when_it_cannot_open(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(**_: object) -> object:
        message = "[Errno 13] Access denied (insufficient permissions)"
        raise FakeUsbError(message)

    device = FakeDevice()
    monkeypatch.setattr(name="get_active_configuration", target=device, value=denied)
    monkeypatch.setattr(
        name="set_configuration", raising=False, target=device, value=denied
    )
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="backend", target=libusb, value=lambda: None)
    patch_usb(device=device, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotPermittedError, match="UsbDk"):
        libusb.open_bootrom()


def test_open_bootrom_on_windows_retries_only_an_unset_configuration(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(**_: object) -> object:
        message = "[Errno 13] Access denied (insufficient permissions)"
        raise FakeUsbError(message)

    interface, _, _ = interfaced()
    device = Unconfigured(data=interface)
    monkeypatch.setattr(name="get_active_configuration", target=device, value=denied)
    monkeypatch.setattr(name="USBDK", target=libusb, value=True)
    monkeypatch.setattr(name="backend", target=libusb, value=lambda: None)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    with pytest.raises(
        expected_exception=libusb.NotPermittedError, match="Access denied"
    ):
        libusb.open_bootrom()
    assert not device.configured


def test_open_bootrom_says_when_libusb_is_missing(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(**_: object) -> object:
        message = "no backend available"
        raise FakeNoBackendError(message)

    patch_usb(device=None, find=refuse, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NoLibusbError, match="brew install"):
        libusb.open_bootrom()


def test_open_bootrom_says_when_libusb_may_not_open_what_it_sees(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(**_: object) -> object:
        raise FakeUsbError(errno.EACCES, "Access denied (insufficient permissions)")

    device = FakeDevice()
    monkeypatch.setattr(name="get_active_configuration", target=device, value=denied)
    patch_usb(device=device, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="platform", target=sys, value="linux")
    with pytest.raises(expected_exception=libusb.NoAccessError, match="Access denied"):
        libusb.open_bootrom()
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    with pytest.raises(libusb.NotPermittedError, match="Access denied") as stopped:
        libusb.open_bootrom()
    assert not isinstance(stopped.value, libusb.NoAccessError)


def test_open_bootrom_says_when_nothing_answers(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_usb(device=None, monkeypatch=monkeypatch)
    with pytest.raises(expected_exception=libusb.NotThereError, match="0e8d:0003"):
        libusb.open_bootrom()


def test_open_bootrom_says_when_the_kernel_will_not_let_the_interface_go(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    device.held = True
    device.refuse_detach = True
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="platform", target=sys, value="linux")
    with pytest.raises(libusb.NotPermittedError, match="Resource busy") as stopped:
        libusb.open_bootrom()
    assert not isinstance(stopped.value, libusb.NoAccessError)


def test_open_bootrom_takes_both_interfaces_where_no_helper_sends_the_trigger(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    device.held = True
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    assert libusb.open_bootrom() is not None
    assert device.detached == [libusb.CONTROL_INTERFACE, interface.bInterfaceNumber]


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


def test_trigger_hands_off_to_the_helper_where_endpoint_zero_needs_root(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    handed: list[int] = []
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=True)
    monkeypatch.setattr(
        name="elevated", target=libusb, value=lambda *, index: handed.append(index)
    )
    libusb.trigger(index=0xCC)
    assert handed == [0xCC]


def test_trigger_sends_one_transfer_past_the_interface_claim(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    libusb.trigger(index=0xCC)
    assert device.transfers == [(libusb.TO_INTERFACE | libusb.FROM_DEVICE, 0, 0, 0xCC)]
    assert device.disposed


def test_trigger_swallows_the_error_the_payload_leaves_behind(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    interface, device, _ = interfaced()
    device.refuse = True
    patch_usb(device=device, interface=interface, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="ELEVATES", target=libusb, value=False)
    libusb.trigger(index=0xCC)
    assert device.disposed


def test_write_chunks_by_the_packet_size(*, monkeypatch: pytest.MonkeyPatch) -> None:
    port, _, (_, outward) = ported(monkeypatch=monkeypatch)
    assert port.write(data=bytes(0x4008)) == 0x4008
    assert [len(chunk) for chunk in outward.written] == [0x4000, 8]
