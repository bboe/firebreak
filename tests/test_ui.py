from __future__ import annotations

import io
import sys
import time
import types

import pytest

from firebreak import ui


@pytest.mark.parametrize(
    argnames=("program_path", "want"),
    argvalues=[
        ("/src/firebreak/__main__.py", "Run python3 -m firebreak stock again."),
        ("/home/me/firebreak.pyz", "Run python3 firebreak.pyz stock again."),
        ("/home/me/.local/bin/firebreak", "Run firebreak stock again."),
    ],
)
def test_again(
    *, monkeypatch: pytest.MonkeyPatch, program_path: str, want: str
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=[program_path, "stock"])
    monkeypatch.setattr(name="executable", target=sys, value="/usr/bin/python3")
    assert ui.again() == want


def test_clock() -> None:
    assert time.strptime(ui.clock(), "%H:%M:%S")


@pytest.mark.parametrize(
    argnames=("environment", "want"),
    argvalues=[({"NO_COLOR": "1"}, False), ({"TERM": "dumb"}, False), ({}, True)],
)
def test_color(
    *, environment: dict[str, str], monkeypatch: pytest.MonkeyPatch, want: bool
) -> None:
    tty(monkeypatch=monkeypatch)
    for name, value in environment.items():
        monkeypatch.setenv(name=name, value=value)
    assert ui.color(stream=sys.stdout) is want


def test_color_needs_a_tty(*, monkeypatch: pytest.MonkeyPatch) -> None:
    tty(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="isatty", target=sys.stdout, value=lambda: False)
    assert not ui.color(stream=sys.stdout)


def test_color_needs_windows_terminal(*, monkeypatch: pytest.MonkeyPatch) -> None:
    tty(monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="os", target=ui, value=types.SimpleNamespace(environ={}, name="nt")
    )
    assert not ui.color(stream=sys.stdout)
    monkeypatch.setattr(name="environ", target=ui.os, value={"WT_SESSION": "1"})
    assert ui.color(stream=sys.stdout)


def test_die_halts_progress_and_fills(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    tty(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="isatty", target=sys.stderr, value=lambda: True)
    ui.PROGRESS.begin(label="step")
    with pytest.raises(expected_exception=SystemExit) as raised:
        ui._die(message="word " * 30)  # ruff: ignore[private-member-access]
    text = str(raised.value)
    assert text.startswith("\033[31mERROR: word")
    assert "\n" in text
    assert ui.PROGRESS.ticker is None
    assert ui.SESSION.shown == ui.Kind.ERROR
    assert capsys.readouterr().out.endswith("\n")


def test_die_keeps_newlines_and_plain_without_color() -> None:
    ui.SESSION.shown = ui.Kind.INFO
    with pytest.raises(expected_exception=SystemExit) as raised:
        ui._die(message="one\ntwo", prefix="")  # ruff: ignore[private-member-access]
    assert str(raised.value) == "one\ntwo"


def test_mark_falls_back_to_ascii(*, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ui.mark() == "✅"
    monkeypatch.setattr(
        name="stdout",
        target=sys,
        value=io.TextIOWrapper(buffer=io.BytesIO(), encoding="ascii"),
    )
    assert ui.mark() == "done"


def test_paint(*, monkeypatch: pytest.MonkeyPatch) -> None:
    assert ui.paint(code=ui.ANSIColor.RED, text="x") == "x"
    tty(monkeypatch=monkeypatch)
    assert ui.paint(code=ui.ANSIColor.RED, text="x") == "\033[31mx\033[0m"


def test_passed(*, capsys: pytest.CaptureFixture[str]) -> None:
    ui.passed(message="ok")
    assert capsys.readouterr().out == "✅ ok\n"


def test_progress_not_a_tty(*, capsys: pytest.CaptureFixture[str]) -> None:
    ui.PROGRESS.steps = 2
    ui.PROGRESS.begin(estimate="1 s", label="first")
    ui.PROGRESS.begin(label="second")
    ui.PROGRESS.end(skipped=True)
    ui.PROGRESS.end()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("[1/2] first")
    assert "(~1 s)" in lines[0]
    assert "✅   0s" in lines[1]
    assert lines[2].startswith("[2/2] second")
    assert "✅ skip" in lines[3]
    assert len(lines) == 4


def test_progress_note_without_a_ticker(*, capsys: pytest.CaptureFixture[str]) -> None:
    ui.PROGRESS.note(message="plain")
    assert capsys.readouterr().out == "plain\n"


def test_progress_spins_in_ascii(*, monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.TextIOWrapper(buffer=io.BytesIO(), encoding="ascii", write_through=True)
    monkeypatch.setattr(name="stdout", target=sys, value=stream)
    monkeypatch.setattr(name="isatty", target=stream, value=lambda: True)
    ui.PROGRESS.begin(label="spin")
    time.sleep(0.15)
    ui.PROGRESS.end()
    assert b"spin" in stream.buffer.getvalue()
    assert b"|" in stream.buffer.getvalue()


def test_progress_spins_on_a_tty(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    tty(monkeypatch=monkeypatch)
    ui.PROGRESS.begin(label="spin")
    time.sleep(0.25)
    ui.PROGRESS.note(message="careful")
    time.sleep(0.25)
    ui.PROGRESS.end()
    output = capsys.readouterr().out
    assert output.startswith("[1/?] spin")
    assert f"{ui.SPINNER[0]}    0s\r[1/?] spin" in output
    assert "careful" in output
    assert output.endswith("(0s total)\n")
    assert ui.PROGRESS.ticker is None


def test_progress_verbose(*, capsys: pytest.CaptureFixture[str]) -> None:
    ui.ARGUMENTS.verbose = True
    ui.PROGRESS.begin(label="loud")
    ui.PROGRESS.end()
    first, second = capsys.readouterr().out.splitlines()
    assert time.strptime(first[:8], "%H:%M:%S")
    assert first[9:].startswith("[1/?] loud")
    assert time.strptime(second[:8], "%H:%M:%S")


def test_say(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ui.say(text="plain")
    tty(monkeypatch=monkeypatch)
    ui.say(code=ui.ANSIColor.YELLOW, text="yellow")
    assert capsys.readouterr().out == "plain\n\n\033[33myellow\033[0m\n"


def test_show_separates_kinds(*, capsys: pytest.CaptureFixture[str]) -> None:
    ui.show(text="a")
    ui.show(text="b")
    ui.show(kind=ui.Kind.WARN, text="c")
    ui.show(text="d")
    assert capsys.readouterr().out == "a\nb\n\nc\n\nd\n"


@pytest.mark.parametrize(
    argnames=("seconds", "want"),
    argvalues=[(59, "59s"), (60, "1m 00s"), (125, "2m 05s")],
)
def test_since(*, monkeypatch: pytest.MonkeyPatch, seconds: int, want: str) -> None:
    monkeypatch.setattr(name="monotonic", target=time, value=lambda: 1000.0 + seconds)
    assert ui.since(start=1000.0) == want


def test_status(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ui.status(text="waiting")
    assert capsys.readouterr().out == "waiting\n"
    tty(monkeypatch=monkeypatch)
    ui.status(text="waiting")
    assert capsys.readouterr().out == "\r\033[33m" + "waiting".ljust(79) + "\033[0m"


def tty(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="isatty", target=sys.stdout, value=lambda: True)
    monkeypatch.delenv(name="NO_COLOR", raising=False)
    monkeypatch.setenv(name="TERM", value="xterm")
    monkeypatch.setenv(name="WT_SESSION", value="1")
