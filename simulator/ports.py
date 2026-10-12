"""Show the simulated Dot's bootrom as the only serial port pyserial lists.

Run each process's clock FIREBREAK_SIM_SPEED times faster, except while a call
to the simulated Dot or its eMMC runs.
"""

from __future__ import annotations

import contextlib
import fcntl
import importlib.abc
import json
import os
import pathlib
import select
import selectors
import sys
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType

BOOTROM_PRODUCT_ID = 0x0003
CHUNK_SECONDS = 0.05
MEDIATEK_VENDOR_ID = 0x0E8D
MODULE = "serial.tools.list_ports"
NANOSECONDS = 1_000_000_000
REAL_MONOTONIC = time.monotonic_ns
REAL_SELECT = select.select
REAL_SLEEP = time.sleep
REAL_WALL = time.time_ns
SELECTORS = (
    "DevpollSelector",
    "EpollSelector",
    "KqueueSelector",
    "PollSelector",
    "SelectSelector",
)
SPEED = float(os.environ.get("FIREBREAK_SIM_SPEED") or 1)
WORK = pathlib.Path(
    os.environ.get("FIREBREAK_SIM") or pathlib.Path.home() / ".cache" / "firebreak-sim"
)
CLOCK = WORK / "clock.json"
CLOCK_LOCK = WORK / "clock.lock"
STATE = WORK / "state.json"


class Clock:
    def __init__(self) -> None:
        real = REAL_MONOTONIC()
        self.depth = 0
        self.latest = 0
        self.reading = {
            "busy": [],
            "real": real,
            "virtual": real,
            "wall": REAL_WALL() - real,
        }

    def hold(self, *, depth: int) -> None:
        if (self.depth > 0) == (depth > 0):
            self.depth = depth
            return
        with CLOCK_LOCK.open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            virtual, _ = self.now()
            reading = dict(self.reading, real=REAL_MONOTONIC(), virtual=virtual)
            reading["busy"] = [
                pid
                for pid in reading["busy"]
                if pid != os.getpid() and running(pid=pid)
            ] + ([os.getpid()] if depth > 0 else [])
            temporary = CLOCK.with_name(f"{CLOCK.name}.{os.getpid()}")
            temporary.write_text(json.dumps(reading))
            temporary.replace(CLOCK)
            self.reading = reading
            self.depth = depth

    def monotonic(self) -> float:
        return self.monotonic_ns() / NANOSECONDS

    def monotonic_ns(self) -> int:
        return self.now()[0]

    def now(self) -> tuple[int, float]:
        with contextlib.suppress(OSError, ValueError):
            self.reading = json.loads(CLOCK.read_bytes())
        rate = 1 if self.reading["busy"] else SPEED
        virtual = self.reading["virtual"] + int(
            rate * (REAL_MONOTONIC() - self.reading["real"])
        )
        self.latest = max(self.latest, virtual)
        return self.latest, rate

    def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            REAL_SLEEP(seconds)
            return
        depth = self.depth
        self.hold(depth=0)
        try:
            self.waited(call=REAL_SLEEP, seconds=seconds)
        finally:
            self.hold(depth=depth)

    def time(self) -> float:
        return self.time_ns() / NANOSECONDS

    def time_ns(self) -> int:
        return self.monotonic_ns() + self.reading["wall"]

    def waited(self, *, call: Callable[[float], object], seconds: float) -> object:
        target = self.now()[0] + seconds * NANOSECONDS
        while True:
            virtual, rate = self.now()
            left = (target - virtual) / NANOSECONDS
            result = call(max(0, min(left / rate, CHUNK_SECONDS)))
            if left <= 0 or any(result or ()):
                return result


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname != MODULE:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                spec.loader = Loader(inner=spec.loader)
                return spec
        return None


class Loader(importlib.abc.Loader):
    def __init__(self, *, inner: importlib.abc.InspectLoader) -> None:
        self.inner = inner

    def exec_module(self, module: ModuleType) -> None:
        exec(  # ruff: ignore[exec-builtin]
            self.inner.get_code(module.__name__), module.__dict__
        )
        module.comports = comports


@contextlib.contextmanager
def busy() -> Generator[None, None, None]:
    if FAST_CLOCK is None:
        yield
        return
    FAST_CLOCK.hold(depth=FAST_CLOCK.depth + 1)
    try:
        yield
    finally:
        FAST_CLOCK.hold(depth=FAST_CLOCK.depth - 1)


def comports(*_: object) -> list:
    from serial.tools.list_ports_common import (  # ruff: ignore[import-outside-top-level]
        ListPortInfo,
    )

    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return []
    port = state.get("port")
    if state.get("mode") != "bootrom" or not port:
        return []
    info = ListPortInfo(port, skip_link_detection=True)
    info.vid = MEDIATEK_VENDOR_ID
    info.pid = BOOTROM_PRODUCT_ID
    info.serial_number = None
    info.manufacturer = "MediaTek Inc"
    info.product = "MT65xx Preloader"
    info.hwid = f"USB VID:PID={MEDIATEK_VENDOR_ID:04X}:{BOOTROM_PRODUCT_ID:04X}"
    return [info]


def install_clock() -> Clock | None:
    if SPEED <= 1:
        return None
    WORK.mkdir(exist_ok=True, parents=True)
    clock = Clock()
    with CLOCK_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not CLOCK.exists():
            CLOCK.write_text(json.dumps(clock.reading))
    clock.now()

    def select_any(
        readers: list, writers: list, errors: list, timeout: float | None = None
    ) -> tuple[list, list, list]:
        if timeout is None or timeout <= 0:
            return REAL_SELECT(readers, writers, errors, timeout)
        return clock.waited(
            call=lambda seconds: REAL_SELECT(readers, writers, errors, seconds),
            seconds=timeout,
        )

    def scaled(original: Callable) -> Callable:
        def select_ready(
            self: selectors.BaseSelector, timeout: float | None = None
        ) -> list:
            if timeout is None or timeout <= 0:
                return original(self, timeout)
            return clock.waited(
                call=lambda seconds: original(self, seconds), seconds=timeout
            )

        return select_ready

    time.monotonic = time.perf_counter = clock.monotonic
    time.monotonic_ns = time.perf_counter_ns = clock.monotonic_ns
    time.sleep = clock.sleep
    time.time = clock.time
    time.time_ns = clock.time_ns
    select.select = select_any
    for name in SELECTORS:
        kind = getattr(selectors, name, None)
        if kind is not None:
            kind.select = scaled(kind.select)
    return clock


def running(*, pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


sys.meta_path.insert(0, Finder())
FAST_CLOCK = install_clock()
