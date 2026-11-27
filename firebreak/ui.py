from __future__ import annotations

import argparse
import dataclasses
import enum
import os
import pathlib
import re
import shlex
import sys
import textwrap
import threading
import time
from typing import TYPE_CHECKING, NoReturn, TextIO

if TYPE_CHECKING:
    from firebreak.plugin import Device

ANSI_ESCAPE = re.compile(pattern=r"\033\[[0-9;]*[A-Za-z]")
ARGUMENTS = argparse.Namespace(build="", factory_reset=False, target="", verbose=False)
BOOT0_EMPTY = (
    "boot0 may hold no preloader until the last step, so an Echo that restarts"
    " before then shows no light and starts nothing: it waits in its bootrom,"
    " and firebreak takes it from there by itself when it runs again on this"
    " computer"
)
MANAGED_PYTHON = re.compile(pattern=r"cpython-\d[^-]*-[^-]+-[^-]+-[^-]+")
MINUTE = 60
MOST_RELIABLE = (
    "A USB 3 port on the computer itself, with nothing else on it, is the most"
    " reliable."
)
ON_CLIPBOARD = (
    "Everything after the line that asks for help is on your clipboard. Paste"
    " it in #firebreak-support with the output of the run that failed."
)
RELEASES = "https://github.com/bboe/firebreak/releases/latest"
SPINNER = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"
SUPPORT = (
    "If you are troubleshooting a problem and would like help, please stop by"
    " #firebreak-support in the 0x7E Labs Discord,"
    " https://discord.gg/huE5XhWbsz, and paste both the output of the run that"
    " failed and everything below."
)
WAIT = 600


class ANSIColor(enum.Enum):
    RED = 31
    YELLOW = 33


class FatalError(Exception):
    def __init__(self, *, message: str, prefix: str = "ERROR: ") -> None:
        super().__init__(prefix + message)
        self.message = message
        self.prefix = prefix


class Kind(enum.Enum):
    ERROR = "error"
    GOOD = "good"
    INFO = "info"
    WARN = "warn"


class Progress:
    def __init__(self) -> None:
        self.t0 = time.monotonic()
        self.ts = self.t0
        self.line = ""
        self.open = False
        self.step = 0
        self.steps: int | None = 0
        self.stopped = threading.Event()
        self.ticker = None

    def begin(self, *, estimate: int = 0, label: str) -> None:
        self.end()
        self.step += 1
        about = f"~{estimate}s" if estimate else ""
        self.line = f"{self.counter()}{label:<43} {about:>5} "
        self.ts = time.monotonic()
        self.open = True
        if ARGUMENTS.verbose:
            show(text=f"{clock()} {self.line.rstrip()}")
        elif not sys.stdout.isatty():
            show(text=self.line.rstrip())
        else:
            self.start()

    def counter(self) -> str:
        if self.steps is None:
            return ""
        total = str(self.steps or "?")
        digits = max(2, len(total))
        return f"[{self.step:>{digits}}/{total:>{digits}}] "

    def end(self, *, failed: bool = False, skipped: bool = False) -> None:
        if not self.open:
            return
        self.open = False
        back = "\r" if self.halt() else ""
        took = "skip" if skipped else self.seconds()
        total = f"{since(start=self.t0)} total"
        stamp = f"{clock()} " if ARGUMENTS.verbose else ""
        show(text=f"{back}{stamp}{self.line}{mark(failed=failed)} {took} {total:>13}")

    def halt(self) -> bool:
        if not self.ticker:
            return False
        self.stopped.set()
        self.ticker.join()
        self.ticker = None
        return True

    def note(self, *, message: str) -> None:
        running = self.halt()
        if running:
            print()
        warn(text=message)
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
        while not self.stopped.wait(timeout=0.1):
            frame = frames[count % len(frames)]
            show(
                end="",
                flush=True,
                text=f"\r{self.line}{frame:<{width}} {self.seconds()}",
            )
            count += 1


@dataclasses.dataclass
class Session:
    boot0_erased: bool = False
    carries: bool | None = None
    dd: str = "dd"
    device: Device | None = None
    fastboot: bool = False
    hardware_code: int | None = None
    held: bool = False
    migration_confirmed: bool = False
    named: str = ""
    no_wait: bool = False
    probing: bool = False
    raw_usb: bool = False
    read_flash: bool = False
    record: list[str] | None = None
    short: bool = False
    shown: Kind | None = None
    system_lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    usb_read: tuple[float, list] | None = None
    verified: set[pathlib.Path] = dataclasses.field(default_factory=set)


SESSION = Session()


def again() -> str:
    return f"Run {this_command()} again."


def amonet_has_no_fastboot() -> str:
    return (
        f"An {title()} already unlocked with amonet has no fastboot: hold the"
        " + button instead while you plug it back in, which starts its TWRP."
    )


def asked_for() -> str:
    return (
        f"If it fails the same way, run {invocation(options=['report'])} and"
        " paste both this run's output and what the report prints in"
        " #firebreak-support in the 0x7E Labs Discord,"
        f" https://discord.gg/huE5XhWbsz: the report says what this {title()}'s"
        f" eMMC and partitions are. {invocation(options=['write-test'])} then tells"
        " a failing card from a failing cable."
    )


def clock() -> str:
    return time.strftime("%H:%M:%S")


def color(*, stream: TextIO) -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt" and "WT_SESSION" not in os.environ:
        return False
    return stream.isatty()


def confirm(*, force: bool, what: str) -> None:
    if force:
        return
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise FatalError(
            message=f"{what}, and this input is not a terminal, so nothing here"
            " can ask whether that is wanted. Pass --force to write anyway."
        )
    PROGRESS.end()
    warn(text=f"{what}.")
    try:
        answer = input("Type yes to continue: ")
    except EOFError as error:
        raise FatalError(message="Nothing was written.") from error
    if answer.strip().lower() != "yes":
        raise FatalError(message="Nothing was written.")
    print()


def explained(*, error: FatalError) -> str:
    text = error.prefix + error.message
    if "\n" not in text:
        text = textwrap.fill(
            break_long_words=False, break_on_hyphens=False, text=text, width=79
        )
    if SESSION.boot0_erased:
        retry = (
            ""
            if replug() in error.message
            else f" If it fails the same way again, {replug()}"
        )
        text += "\n\n" + textwrap.fill(
            break_long_words=False,
            break_on_hyphens=False,
            text=f"{BOOT0_EMPTY}.{retry}",
            width=79,
        )
    return text


def filled(*, text: str) -> str:
    return "\n\n".join(
        textwrap.fill(
            break_long_words=False, break_on_hyphens=False, text=part, width=79
        )
        for part in text.split(sep="\n\n")
    )


def invocation(*, options: list[str]) -> str:
    command = [pathlib.Path(word).name for word in program()]
    if command[1:2] != ["-m"]:
        command = command[1:]
    if command == ["firebreak"] and any(
        part.startswith("archive-v") for part in pathlib.Path(sys.prefix).parts
    ):
        command = uvx()
    return f"`{shlex.join(split_command=[*command, *options])}`"


def mark(*, failed: bool = False) -> str:
    sign = "\u274c" if failed else "\u2705"
    try:
        sign.encode(encoding=sys.stdout.encoding or "ascii")
    except (LookupError, UnicodeEncodeError):
        return "fail" if failed else "done"
    return sign


def overwriting(*, text: str, width: int) -> str:
    if color(stream=sys.stdout):
        return f"\r{paint(code=ANSIColor.YELLOW, text=text)}\033[K"
    return f"\r{text.ljust(width)}"


def paint(*, code: ANSIColor, text: str) -> str:
    return f"\033[{code.value}m{text}\033[0m" if color(stream=sys.stdout) else text


def passed(*, message: str) -> None:
    alone = threading.current_thread() is threading.main_thread()
    show(kind=Kind.GOOD if alone else Kind.INFO, text=f"{mark()} {message}")


def program() -> list[str]:
    if pathlib.Path(sys.argv[0]).name == "__main__.py":
        return [sys.executable, "-m", "firebreak"]
    return [sys.executable, sys.argv[0]]


def replug() -> str:
    return (
        f"unplug the {title()}, run {this_command()} again,"
        f" then plug the {title()} into another USB port. {MOST_RELIABLE}"
    )


def reseat() -> str:
    return (
        "A poor USB connection can cause this. Unplug both ends of the cable and"
        " plug them back in firmly. " + again()
    )


def say(*, text: str) -> None:
    show(text=filled(text=text))


def show(*, kind: Kind = Kind.INFO, text: str, **options: str | bool) -> None:
    whole = SESSION.record is not None and options.get("end", "\n") == "\n"
    if SESSION.shown not in {None, kind}:
        print()
        if whole:
            SESSION.record.append("")
    SESSION.shown = kind
    print(text, **options)
    if whole:
        SESSION.record.append(ANSI_ESCAPE.sub(repl="", string=text))


def since(*, start: float) -> str:
    seconds = int(time.monotonic() - start)
    if seconds < MINUTE:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60:02d}s"


def status(*, text: str) -> None:
    if sys.stdout.isatty():
        show(end="", flush=True, kind=Kind.WARN, text=overwriting(text=text, width=79))
    else:
        warn(text=text)


def stop(*, error: FatalError) -> NoReturn:
    if PROGRESS.halt():
        print()
    if SESSION.shown not in {None, Kind.ERROR}:
        print()
    SESSION.shown = Kind.ERROR
    text = explained(error=error)
    if error.prefix and color(stream=sys.stderr):
        text = f"\033[{ANSIColor.RED.value}m{text}\033[0m"
    raise SystemExit(text)


def this_command() -> str:
    return invocation(options=sys.argv[1:])


def title() -> str:
    if ARGUMENTS.target:
        return ARGUMENTS.target.device.title
    if SESSION.device is not None:
        return SESSION.device.title
    return SESSION.named or "Echo"


def upgrade() -> tuple[str, str]:
    return "run", shlex.join(split_command=uvx())


def uvx() -> list[str]:
    if MANAGED_PYTHON.fullmatch(string=pathlib.Path(sys.base_prefix).name):
        return ["uvx", "--managed-python", "firebreak@latest"]
    return ["uvx", "firebreak@latest"]


def warn(*, text: str) -> None:
    show(kind=Kind.WARN, text=paint(code=ANSIColor.YELLOW, text=filled(text=text)))


PROGRESS = Progress()
