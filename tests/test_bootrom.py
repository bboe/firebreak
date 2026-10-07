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


class Dev:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def __init__(self, port: str = "p", reads: list[bytes] | None = None) -> None:
        self.port = port
        self.reads = reads or []
        self.writes: list[bytes] = []
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def flushInput(self) -> None:  # ruff: ignore[invalid-function-name]
        pass

    def read(self, size: int) -> bytes:
        return self.reads.pop(0) if self.reads else bytes(size)

    def write(self, data: bytes) -> None:
        self.writes.append(data)


class Fakes(types.SimpleNamespace):
    pass


class Port(types.SimpleNamespace):
    pass


class SerialError(Exception):
    pass


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Iterator[Fakes]:
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

    def serial_open(port: str, *_: object, **__: object) -> Dev:
        if found.open_fails:
            found.open_fails -= 1
            raise SerialError(port)
        dev = Dev(port)
        found.opened.append(dev)
        return dev

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
            self.dev: Dev | None = Dev()
            self.checked: list[tuple[bytes, bytes]] = []
            self.switched: list[int] = []

        @staticmethod
        def _writeb(data: bytes) -> bytes:
            return found.answer(data)

        def check(self, got: bytes, want: bytes) -> None:
            self.checked.append((got, want))

        def emmc_switch(self, part: int) -> None:
            self.switched.append(part)

    common = types.ModuleType("common")
    common.BAUD = 115200
    common.TIMEOUT = 5
    common.Device = Device
    amonet = types.ModuleType("main")
    amonet.load_payload = lambda dev, path: found.started.append((dev, path))
    amonet.main = lambda: None
    logger = types.ModuleType("logger")
    logger.log = found.logged.append
    found.answer = HANDSHAKE.get
    found.common, found.amonet = common, amonet
    for name, module in {
        "common": common,
        "logger": logger,
        "main": amonet,
        "serial": serial,
        "serial.tools": tools,
        "serial.tools.list_ports": list_ports,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    def monotonic() -> float:
        found.clock[0] += 0.5
        return found.clock[0]

    monkeypatch.setattr(
        bootrom,
        "time",
        types.SimpleNamespace(monotonic=monotonic, sleep=lambda _: None),
    )
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FIREBREAK_ERASED", str(tmp_path / "erased"))
    monkeypatch.delenv("FIREBREAK_RESUME", raising=False)
    return found


def brom(device: str, pid: int | None = bootrom.BROM_PID) -> Port:
    return Port(device=device, pid=pid, vid=bootrom.MEDIATEK_VID)


def run_child(fakes: Fakes) -> type:
    assert bootrom.child_bootrom() == 0
    return fakes.common.Device


def test_child_bootrom_patches_amonet(fakes: Fakes, tmp_path: pathlib.Path) -> None:
    device = run_child(fakes)
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


def test_child_reset(fakes: Fakes) -> None:
    fakes.ports = [[brom("p1"), Port(device="usb0", pid=1, vid=0x1234), brom("p2")]]
    fakes.open_fails = 1
    assert bootrom.child_reset() == 0
    assert [dev.port for dev in fakes.opened] == ["p2"]
    assert fakes.opened[0].writes == [struct.pack(">II", 0xF00DD00D, 0x3000)]
    assert fakes.opened[0].closed


def test_emmc_read(fakes: Fakes) -> None:
    dev = run_child(fakes)()
    dev.dev.reads = [b"s" * 512 + b"tail"]
    assert dev.emmc_read(7) == b"s" * 512
    assert dev.dev.writes == [
        struct.pack(">III", 0xF00DD00D, 0x1000, 7),
        struct.pack(">IIII", 0xF00DD00D, 0x5000, 0x201000, 4),
    ]
    dev.dev.reads = [b"short"]
    with pytest.raises(RuntimeError, match="read fail"):
        dev.emmc_read(7)


def test_emmc_write_blocks(fakes: Fakes) -> None:
    dev = run_child(fakes)()
    dev.dev.reads = [b"\xd0\xd0\xd0\xd0", b"nope"]
    dev.emmc_write_blocks(9, bytes(1024))
    assert dev.dev.writes == [
        struct.pack(">IIII", 0xF00DD00D, 0x1003, 9, 2),
        bytes(1024),
    ]
    with pytest.raises(RuntimeError, match="device failure"):
        dev.emmc_write_blocks(9, bytes(512))


def test_find_device_resumes_on_a_waiting_bootrom(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIREBREAK_RESUME", "1")
    fakes.ports = [[brom("p1")]]
    dev = run_child(fakes)()
    dev.find_device()
    assert dev.dev.port == "p1"


def test_find_device_retries_a_port_it_cannot_open(fakes: Fakes) -> None:
    fakes.ports = [[], [brom("p1")]]
    fakes.open_fails = 3
    dev = run_child(fakes)()
    dev.find_device()
    assert dev.dev.port == "p1"
    assert fakes.logged.count("Cannot open p1: p1") == 1


def test_find_device_waits_for_a_new_bootrom(fakes: Fakes) -> None:
    other = Port(device="usb0", pid=1, vid=0x1234)
    preloader = brom("p2", bootrom.PRELOADER_PID)
    fakes.ports = [
        [brom("p1"), other],
        [brom("p1"), brom("p0", None)],
        [preloader],
        [preloader, brom("p3")],
    ]
    dev = run_child(fakes)()
    dev.find_device()
    assert dev.dev.port == "p3"
    assert fakes.logged == [
        "Waiting for bootrom",
        "Ignoring the preloader on p2",
        "Found port = p3",
    ]


def test_flash_data(fakes: Fakes, tmp_path: pathlib.Path) -> None:
    run_child(fakes)
    written: list[tuple[int, int]] = []
    dev = types.SimpleNamespace(
        emmc_write_blocks=lambda block, data: written.append((block, len(data)))
    )
    fakes.amonet.flash_data(dev, bytes(64 * 512 + 10), 100)
    assert written == [(100, 64 * 512), (164, 512)]
    assert (tmp_path / "erased").exists()
    with pytest.raises(RuntimeError, match="data too big"):
        fakes.amonet.flash_data(dev, bytes(1025), 0, 1024)


def test_flash_data_without_a_marker(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.delenv("FIREBREAK_ERASED")
    run_child(fakes)
    dev = types.SimpleNamespace(emmc_write_blocks=lambda *_: None)
    fakes.amonet.flash_data(dev, bytes(512), 0)
    assert not (tmp_path / "erased").exists()


def test_handshake(fakes: Fakes) -> None:
    dev = run_child(fakes)()
    dev.handshake()
    assert dev.checked == [(b"\xf5", b"\xf5"), (b"\xaf", b"\xaf"), (b"\xfa", b"\xfa")]


def test_handshake_retries_until_the_deadline(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootrom, "HANDSHAKE_WAIT", 2)
    misses = [b"\x00"] * 4

    def answer(data: bytes) -> bytes:
        if data == b"\xa0" and misses:
            return misses.pop()
        return HANDSHAKE[data]

    fakes.answer = answer
    fakes.ports = [[], [], [brom("p2")]]
    dev = run_child(fakes)()
    dev.handshake()
    assert dev.dev.port == "p2"
    assert len(fakes.logged) >= 2


def test_handshake_waits_for_the_port_to_return(fakes: Fakes) -> None:
    answers = [SerialError("gone"), b"\x00", b"\x00"]

    def answer(data: bytes) -> bytes:
        if data == b"\xa0" and answers:
            reply = answers.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return HANDSHAKE[data]

    fakes.answer = answer
    fakes.ports = [[brom("p")], [], [], [brom("p2")]]
    dev = run_child(fakes)()
    dev.dev.port = "p"
    first = dev.dev
    dev.handshake()
    assert first.closed
    assert dev.dev.port == "p2"
    assert fakes.logged.count("The bootrom did not answer the handshake") == 1


def test_load_payload(fakes: Fakes) -> None:
    run_child(fakes)
    dev = types.SimpleNamespace(
        emmc_read=lambda _: bytes(510) + b"\x55\xaa", emmc_switch=lambda _: None
    )
    fakes.amonet.load_payload(dev, "payload.bin")
    assert fakes.started == [(dev, "payload.bin")]


@pytest.mark.parametrize("fails", [True, False])
def test_load_payload_needs_the_emmc(fakes: Fakes, fails: bool) -> None:
    run_child(fakes)

    def read(_: int) -> bytes:
        if fails:
            raise RuntimeError
        return bytes(512)

    dev = types.SimpleNamespace(emmc_read=read, emmc_switch=lambda _: None)
    with pytest.raises(SystemExit) as raised:
        fakes.amonet.load_payload(dev, "payload.bin")
    assert raised.value.code == 3
    assert "The eMMC did not answer" in fakes.logged


def test_rpmb_read(fakes: Fakes) -> None:
    dev = run_child(fakes)()
    dev.dev.reads = [b"r" * 0x104]
    assert dev.rpmb_read() == b"r" * 0x100
    assert dev.dev.writes[0] == struct.pack(">II", 0xF00DD00D, 0x2000)
