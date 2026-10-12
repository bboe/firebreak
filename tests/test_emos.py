from __future__ import annotations

import itertools
import subprocess
import types
from typing import TYPE_CHECKING

import pytest
import serial
from serial.tools import list_ports

from firebreak import emos
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

    from typing_extensions import Self


class FakeConsole:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def __init__(self, *, said: bytes) -> None:
        self.said = bytearray(said)
        self.written = bytearray()

    def read(self, *, size: int) -> bytes:
        taken = bytes(self.said[:size])
        del self.said[:size]
        return taken

    def reset_input_buffer(self) -> None:
        pass

    def write(self, *, data: bytes) -> int:
        self.written += data
        return len(data)


def consoles(
    *, monkeypatch: pytest.MonkeyPatch, serials: list[str]
) -> list[types.SimpleNamespace]:
    vendor, product = emos.EMOS_DEVICE_ID
    ports = [
        types.SimpleNamespace(
            device=f"/dev/tty{index}", pid=product, serial_number=number, vid=vendor
        )
        for index, number in enumerate(serials)
    ]
    other = types.SimpleNamespace(
        device="/dev/ttyX", pid=0x2000, serial_number="X", vid=vendor
    )
    monkeypatch.setattr(
        name="comports", target=list_ports, value=lambda: [*ports, other]
    )
    return ports


def opened(*, console: FakeConsole, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    def connect(**options: object) -> FakeConsole:
        asked.append(str(options["port"]))
        return console

    monkeypatch.setattr(name="Serial", target=serial, value=connect)
    return asked


def ran(*, monkeypatch: pytest.MonkeyPatch, stdout: str) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    def run(**options: object) -> subprocess.CompletedProcess[str]:
        calls.append(options)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)

    monkeypatch.setattr(name="pyserial_wheel", target=emos, value=lambda: None)
    monkeypatch.setattr(name="run", target=emos.subprocess, value=run)
    return calls


def test_a_console_that_asks_for_a_password_is_not_answered(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    consoles(monkeypatch=monkeypatch, serials=["A"])
    console = FakeConsole(said=b"\nPassword: password: ")
    opened(console=console, monkeypatch=monkeypatch)
    assert emos.child_emos(action="recovery", want="") == 1
    assert capsys.readouterr().out == "password\n"
    assert console.written == b"\n"


@pytest.mark.parametrize(
    ("answer", "said"),
    [
        ("password", "asks for a password"),
        ("denied", "cannot open the Dot over USB"),
        ("silent", "did not answer"),
        ("0", "did not answer"),
    ],
)
def test_a_console_that_does_not_start_recovery_stops_the_run(
    *, answer: str, monkeypatch: pytest.MonkeyPatch, said: str
) -> None:
    ran(monkeypatch=monkeypatch, stdout=answer)
    with pytest.raises(FatalError, match=said):
        emos.stage_emos()
    assert not emos.PROGRESS.open


def test_a_console_that_says_nothing_is_silent(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    consoles(monkeypatch=monkeypatch, serials=["A"])
    opened(console=FakeConsole(said=b""), monkeypatch=monkeypatch)
    clock = itertools.count(start=0, step=3)
    monkeypatch.setattr(name="monotonic", target=emos.time, value=lambda: next(clock))
    assert emos.child_emos(action="recovery", want="") == 1
    assert capsys.readouterr().out == "silent\n"


def test_a_console_the_user_cannot_open_is_denied(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    consoles(monkeypatch=monkeypatch, serials=["A"])

    def refuse(**_: object) -> FakeConsole:
        raise serial.SerialException

    monkeypatch.setattr(name="Serial", target=serial, value=refuse)
    assert emos.child_emos(action="recovery", want="") == 1
    assert capsys.readouterr().out == "denied\n"


def test_a_root_prompt_is_told_to_start_recovery(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    consoles(monkeypatch=monkeypatch, serials=["A", "B"])
    console = FakeConsole(said=b"\n# ")
    asked = opened(console=console, monkeypatch=monkeypatch)
    assert emos.child_emos(action="recovery", want="B") == 0
    assert asked == ["/dev/tty1"]
    assert console.written == b"\n/init recovery\n"
    assert capsys.readouterr().out == "recovery\n"


def test_emos_runs_its_child_for_this_dot(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="USER_SERIAL", target=emos, value="G0")
    calls = ran(monkeypatch=monkeypatch, stdout=" 1\n")
    assert emos.emos(action="find") == "1"
    assert calls[0]["args"][-3:] == ["emos", "find", "G0"]
    assert calls[0]["cwd"] == tmp_path / "real-cache"


def test_emos_says_what_it_runs_only_when_verbose(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown: list[str] = []
    monkeypatch.setattr(
        name="show", target=emos, value=lambda **said: shown.append(said["text"])
    )
    ran(monkeypatch=monkeypatch, stdout="recovery\n")
    emos.ARGUMENTS.verbose = True
    emos.emos(action="find")
    assert shown == []
    emos.emos(action="recovery")
    assert len(shown) == 1
    assert shown[0].endswith("_child emos recovery")


def test_emos_stops_when_more_than_one_answers(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(monkeypatch=monkeypatch, stdout="2\n")
    with pytest.raises(FatalError, match="more than one"):
        emos.emos(action="find")


@pytest.mark.parametrize(
    ("action", "serials", "want", "printed", "returned"),
    [
        ("find", ["A", "B"], "", "2\n", 0),
        ("find", ["A"], "B", "0\n", 0),
        ("recovery", [], "", "0\n", 1),
        ("recovery", ["A", "B"], "", "2\n", 1),
    ],
)
def test_finding_consoles_counts_the_emos_ports(  # ruff: ignore[too-many-arguments]
    *,
    action: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    printed: str,
    returned: int,
    serials: list[str],
    want: str,
) -> None:
    consoles(monkeypatch=monkeypatch, serials=serials)
    monkeypatch.setattr(
        name="Serial", target=serial, value=lambda **_: pytest.fail("opened")
    )
    assert emos.child_emos(action=action, want=want) == returned
    assert capsys.readouterr().out == printed


def test_the_emos_stage_waits_for_recovery(*, monkeypatch: pytest.MonkeyPatch) -> None:
    ran(monkeypatch=monkeypatch, stdout="recovery")
    emos.stage_emos()
    assert emos.PROGRESS.open
