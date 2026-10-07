from __future__ import annotations

import struct
import sys
import types
from typing import TYPE_CHECKING

import pytest

from firebreak.mediatek import bootrom

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

    from typing_extensions import Self

HANDSHAKE = {b"\xa0": b"\x5f", b"\x0a": b"\xf5", b"\x50": b"\xaf", b"\x05": b"\xfa"}


class Connection:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def __init__(self, *, port: str = "p", reads: list[bytes] | None = None) -> None:
        self.port = port
        self.reads = reads or []
        self.writes: list[bytes] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def flushInput(self) -> None:  # ruff: ignore[invalid-function-name]
        pass

    def read(self, *, size: int) -> bytes:
        return self.reads.pop(0) if self.reads else bytes(size)

    def write(self, *, data: bytes) -> None:
        self.writes.append(data)


class Fakes(types.SimpleNamespace):
    pass


class Port(types.SimpleNamespace):
    pass


class SerialError(Exception):
    pass


@pytest.fixture
def fakes(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> Iterator[Fakes]:
    found = Fakes(
        clock=[0.0],
        logged=[],
        open_fails=0,
        opened=[],
        ports=[[]],
        started=[],
    )

    def comports() -> list[Port]:
        return found.ports.pop(0) if len(found.ports) > 1 else found.ports[0]

    def serial_open(*, port: str, **__: object) -> Connection:
        if found.open_fails:
            found.open_fails -= 1
            raise SerialError(port)
        connection = Connection(port=port)
        found.opened.append(connection)
        return connection

    serial = types.ModuleType("serial")
    serial.SerialException = SerialError
    serial.Serial = serial_open
    tools = types.ModuleType("serial.tools")
    list_ports = types.ModuleType("serial.tools.list_ports")
    list_ports.comports = comports
    tools.list_ports = list_ports
    serial.tools = tools

    class Device:
        def __init__(self) -> None:
            self.dev: Connection | None = Connection()
            self.checked: list[tuple[bytes, bytes]] = []
            self.switched: list[int] = []

        @staticmethod
        def _writeb(*, out_str: bytes) -> bytes:
            return found.answer(data=out_str)

        def check(self, *, gold: bytes, test: bytes) -> None:
            self.checked.append((test, gold))

        def emmc_switch(self, *, part: int) -> None:
            self.switched.append(part)

    common = types.ModuleType("common")
    common.BAUD = 115200
    common.TIMEOUT = 5
    common.Device = Device
    amonet = types.ModuleType("main")
    amonet.load_payload = lambda *, dev, path: found.started.append((dev, path))
    amonet.main = lambda: None
    logger = types.ModuleType("logger")
    logger.log = lambda *, s: found.logged.append(s)
    found.answer = lambda *, data: HANDSHAKE.get(data)
    found.common, found.amonet = common, amonet
    for name, module in {
        "common": common,
        "logger": logger,
        "main": amonet,
        "serial": serial,
        "serial.tools": tools,
        "serial.tools.list_ports": list_ports,
    }.items():
        monkeypatch.setitem(dic=sys.modules, name=name, value=module)

    def monotonic() -> float:
        found.clock[0] += 0.5
        return found.clock[0]

    monkeypatch.setattr(
        name="time",
        target=bootrom,
        value=types.SimpleNamespace(monotonic=monotonic, sleep=lambda _: None),
    )
    monkeypatch.setattr(name="path", target=sys, value=list(sys.path))
    monkeypatch.chdir(path=tmp_path)
    monkeypatch.setenv(name="FIREBREAK_ERASED", value=str(tmp_path / "erased"))
    monkeypatch.delenv(name="FIREBREAK_RESUME", raising=False)
    return found


def bootrom_port(
    *, device: str, product_id: int | None = bootrom.BOOTROM_PRODUCT_ID
) -> Port:
    return Port(device=device, pid=product_id, vid=bootrom.MEDIATEK_VENDOR_ID)


def run_child(*, fakes: Fakes) -> type:
    assert bootrom.child_bootrom() == 0
    return fakes.common.Device


def test_child_bootrom_patches_amonet(*, fakes: Fakes, tmp_path: pathlib.Path) -> None:
    device = run_child(fakes=fakes)
    assert sys.path[0] == str(tmp_path)
    for name in (
        "emmc_read",
        "emmc_write_blocks",
        "find_device",
        "handshake",
        "rpmb_read",
    ):
        assert getattr(device, name).__module__ == bootrom.__name__
    assert fakes.amonet.flash_data.__module__ == bootrom.__name__
    assert fakes.amonet.load_payload.__module__ == bootrom.__name__


def test_child_reset(*, fakes: Fakes) -> None:
    fakes.ports = [
        [
            bootrom_port(device="p1"),
            Port(device="usb0", pid=1, vid=0x1234),
            bootrom_port(device="p2"),
        ]
    ]
    fakes.open_fails = 1
    assert bootrom.child_reset() == 0
    assert [connection.port for connection in fakes.opened] == ["p2"]
    assert fakes.opened[0].writes == [struct.pack(">II", 0xF00DD00D, 0x3000)]
    assert fakes.opened[0].closed


def test_emmc_read(*, fakes: Fakes) -> None:
    device = run_child(fakes=fakes)()
    device.dev.reads = [b"s" * 512 + b"tail"]
    assert device.emmc_read(index=7) == b"s" * 512
    assert device.dev.writes == [
        struct.pack(">III", 0xF00DD00D, 0x1000, 7),
        struct.pack(">IIII", 0xF00DD00D, 0x5000, 0x201000, 4),
    ]
    device.dev.reads = [b"short"]
    with pytest.raises(expected_exception=RuntimeError, match="read fail"):
        device.emmc_read(index=7)


def test_emmc_write_blocks(*, fakes: Fakes) -> None:
    device = run_child(fakes=fakes)()
    device.dev.reads = [b"\xd0\xd0\xd0\xd0", b"nope"]
    device.emmc_write_blocks(data=bytes(1024), index=9)
    assert device.dev.writes == [
        struct.pack(">IIII", 0xF00DD00D, 0x1003, 9, 2),
        bytes(1024),
    ]
    with pytest.raises(expected_exception=RuntimeError, match="device failure"):
        device.emmc_write_blocks(data=bytes(512), index=9)


def test_find_device_resumes_on_a_waiting_bootrom(
    *, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name="FIREBREAK_RESUME", value="1")
    fakes.ports = [[bootrom_port(device="p1")]]
    device = run_child(fakes=fakes)()
    device.find_device()
    assert device.dev.port == "p1"


def test_find_device_retries_a_port_it_cannot_open(*, fakes: Fakes) -> None:
    fakes.ports = [[], [bootrom_port(device="p1")]]
    fakes.open_fails = 3
    device = run_child(fakes=fakes)()
    device.find_device()
    assert device.dev.port == "p1"
    assert fakes.logged.count("Cannot open p1: p1") == 1


def test_find_device_waits_for_a_new_bootrom(*, fakes: Fakes) -> None:
    other = Port(device="usb0", pid=1, vid=0x1234)
    preloader = bootrom_port(device="p2", product_id=bootrom.PRELOADER_PRODUCT_ID)
    fakes.ports = [
        [bootrom_port(device="p1"), other],
        [bootrom_port(device="p1"), bootrom_port(device="p0", product_id=None)],
        [preloader],
        [preloader, bootrom_port(device="p3")],
    ]
    device = run_child(fakes=fakes)()
    device.find_device()
    assert device.dev.port == "p3"
    assert fakes.logged == [
        "Waiting for bootrom",
        "Ignoring the preloader on p2",
        "Found port = p3",
    ]


def test_flash_data(*, fakes: Fakes, tmp_path: pathlib.Path) -> None:
    run_child(fakes=fakes)
    written: list[tuple[int, int]] = []
    device = types.SimpleNamespace(
        emmc_write_blocks=lambda *, data, index: written.append((index, len(data)))
    )
    fakes.amonet.flash_data(data=bytes(64 * 512 + 10), device=device, start_block=100)
    assert written == [(100, 64 * 512), (164, 512)]
    assert (tmp_path / "erased").exists()
    with pytest.raises(expected_exception=RuntimeError, match="data too big"):
        fakes.amonet.flash_data(
            data=bytes(1025), device=device, max_size=1024, start_block=0
        )


def test_flash_data_without_a_marker(
    *, fakes: Fakes, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv(name="FIREBREAK_ERASED")
    run_child(fakes=fakes)
    device = types.SimpleNamespace(emmc_write_blocks=lambda **_: None)
    fakes.amonet.flash_data(data=bytes(512), device=device, start_block=0)
    assert not (tmp_path / "erased").exists()


def test_handshake(*, fakes: Fakes) -> None:
    device = run_child(fakes=fakes)()
    device.handshake()
    assert device.checked == [
        (b"\xf5", b"\xf5"),
        (b"\xaf", b"\xaf"),
        (b"\xfa", b"\xfa"),
    ]


def test_handshake_retries_until_the_deadline(
    *, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="HANDSHAKE_WAIT", target=bootrom, value=2)
    misses = [b"\x00"] * 4

    def answer(*, data: bytes) -> bytes:
        if data == b"\xa0" and misses:
            return misses.pop()
        return HANDSHAKE[data]

    fakes.answer = answer
    fakes.ports = [[], [], [bootrom_port(device="p2")]]
    device = run_child(fakes=fakes)()
    device.handshake()
    assert device.dev.port == "p2"
    assert len(fakes.logged) >= 2


def test_handshake_waits_for_the_port_to_return(*, fakes: Fakes) -> None:
    answers = [SerialError("gone"), b"\x00", b"\x00"]

    def answer(*, data: bytes) -> bytes:
        if data == b"\xa0" and answers:
            reply = answers.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return HANDSHAKE[data]

    fakes.answer = answer
    fakes.ports = [[bootrom_port(device="p")], [], [], [bootrom_port(device="p2")]]
    device = run_child(fakes=fakes)()
    device.dev.port = "p"
    first = device.dev
    device.handshake()
    assert first.closed
    assert device.dev.port == "p2"
    assert fakes.logged.count("The bootrom did not answer the handshake") == 1


def test_load_payload(*, fakes: Fakes) -> None:
    run_child(fakes=fakes)
    device = types.SimpleNamespace(
        emmc_read=lambda **_: bytes(510) + b"\x55\xaa",
        emmc_switch=lambda **_: None,
    )
    fakes.amonet.load_payload(device=device, path="payload.bin")
    assert fakes.started == [(device, "payload.bin")]


@pytest.mark.parametrize(argnames="fails", argvalues=[True, False])
def test_load_payload_needs_the_emmc(*, fails: bool, fakes: Fakes) -> None:
    run_child(fakes=fakes)

    def read(**_: int) -> bytes:
        if fails:
            raise RuntimeError
        return bytes(512)

    device = types.SimpleNamespace(emmc_read=read, emmc_switch=lambda **_: None)
    with pytest.raises(expected_exception=SystemExit) as raised:
        fakes.amonet.load_payload(device=device, path="payload.bin")
    assert raised.value.code == 3
    assert "The eMMC did not answer" in fakes.logged


def test_rpmb_read(*, fakes: Fakes) -> None:
    device = run_child(fakes=fakes)()
    device.dev.reads = [b"r" * 0x104]
    assert device.rpmb_read() == b"r" * 0x100
    assert device.dev.writes[0] == struct.pack(">II", 0xF00DD00D, 0x2000)
