from __future__ import annotations

import argparse
import dataclasses
import enum
import os
import pathlib
import shlex
import sys
import textwrap
import threading
import time
from typing import NoReturn, TextIO

ARGS = argparse.Namespace(build="", target="", verbose=False)
MINUTE = 60
SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"


class ANSIColor(enum.Enum):
    RED = 31
    YELLOW = 33


class Kind(enum.Enum):
    ERROR = "error"
    INFO = "info"
    WARN = "warn"


class Progress:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.ts = self.t0
        self.line = ""
        self.open = False
        self.step = 0
        self.steps = 0
        self.stopped = threading.Event()
        self.ticker = None

    def begin(self, *, estimate: str = "", label: str) -> None:
        self.end()
        self.step += 1
        about = f"(~{estimate})" if estimate else ""
        total = str(self.steps or "?")
        self.line = f"[{self.step:>{len(total)}}/{total}] {label:<38} {about:<8} "
        self.ts = time.monotonic()
        self.open = True
        if ARGS.verbose:
            show(text=f"{clock()} {self.line.rstrip()}")
        elif not sys.stdout.isatty():
            show(text=self.line.rstrip())
        else:
            self.start()

    def end(self, *, skipped: bool = False) -> None:
        if not self.open:
            return
        self.open = False
        back = "\r" if self.halt() else ""
        took = "skip" if skipped else self.seconds()
        total = f"({since(self.t0)} total)"
        stamp = f"{clock()} " if ARGS.verbose else ""
        show(text=f"{back}{stamp}{self.line}{mark()} {took} {total:>15}")

    def halt(self) -> bool:
        if not self.ticker:
            return False
        self.stopped.set()
        self.ticker.join()
        self.ticker = None
        return True

    def note(self, message: str) -> None:
        running = self.halt()
        if running:
            print()
        warn(message)
        if running:
            self.start()

    def seconds(self) -> str:
        return f"{int(time.monotonic() - self.ts):3d}s"

    def start(self) -> None:
        show(end="", flush=True, text=self.line)
        self.stopped.clear()
        self.ticker = threading.Thread(daemon=True, target=self.tick)
        self.ticker.start()

    def tick(self) -> None:
        width = 2 if mark() == "✅" else len(mark())
        frames = SPINNER if mark() == "✅" else "|/-\\"
        count = 0
        while not self.stopped.wait(0.1):
            frame = frames[count % len(frames)]
            show(
                end="",
                flush=True,
                text=f"\r{self.line}{frame:<{width}} {self.seconds()}",
            )
            count += 1


@dataclasses.dataclass
class Session:
    dd: str = "dd"
    probing: bool = False
    short: bool = False
    shown: Kind | None = None
    system_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    verified: set[pathlib.Path] = dataclasses.field(default_factory=set)


SESSION = Session()


def _die(*, message: str, prefix: str = "ERROR: ") -> NoReturn:
    if PROGRESS.halt():
        print()
    if SESSION.shown not in {None, Kind.ERROR}:
        print()
    SESSION.shown = Kind.ERROR
    text = prefix + message
    if "\n" not in text:
        text = textwrap.fill(text, 79)
    if prefix and color(sys.stderr):
        text = f"\033[{ANSIColor.RED.value}m{text}\033[0m"
    raise SystemExit(text)


def again() -> str:
    command = [pathlib.Path(word).name for word in program()]
    if command[1:2] != ["-m"] and pathlib.Path(command[-1]).suffix != ".pyz":
        command = command[1:]
    return f"Run {shlex.join([*command, *sys.argv[1:]])} again."


def clock() -> str:
    return time.strftime("%H:%M:%S")


def color(stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt" and "WT_SESSION" not in os.environ:
        return False
    return stream.isatty()


def mark() -> str:
    try:
        "\u2705".encode(sys.stdout.encoding or "ascii")
    except (LookupError, UnicodeEncodeError):
        return "done"
    return "\u2705"


def paint(*, code: ANSIColor, text: str) -> str:
    return f"\033[{code.value}m{text}\033[0m" if color(sys.stdout) else text


def passed(message: str) -> None:
    show(text=f"{mark()} {message}")


def program() -> list[str]:
    if pathlib.Path(sys.argv[0]).name == "__main__.py":
        return [sys.executable, "-m", "firebreak"]
    return [sys.executable, sys.argv[0]]


def say(*, code: ANSIColor | None = None, text: str) -> None:
    text = textwrap.fill(text, 79)
    show(
        kind=Kind.WARN if code else Kind.INFO,
        text=paint(code=code, text=text) if code else text,
    )


def show(*, kind: Kind = Kind.INFO, text: str, **options: str | bool) -> None:
    if SESSION.shown not in {None, kind}:
        print()
    SESSION.shown = kind
    print(text, **options)


def since(start: float) -> str:
    seconds = int(time.monotonic() - start)
    if seconds < MINUTE:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def status(text: str) -> None:
    if sys.stdout.isatty():
        show(
            end="",
            flush=True,
            kind=Kind.WARN,
            text="\r" + paint(code=ANSIColor.YELLOW, text=text.ljust(79)),
        )
    else:
        warn(text)


def warn(text: str) -> None:
    show(
        kind=Kind.WARN, text=paint(code=ANSIColor.YELLOW, text=textwrap.fill(text, 79))
    )


PROGRESS = Progress()
