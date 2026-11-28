from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

DEVICES = ("biscuit", "donut", "radar")
HERE = pathlib.Path(__file__).resolve().parent.parent
PLUG_PROMPT = re.compile(r"test point and plug it in|start it in its bootrom")
VERDICT = re.compile(r"(✅ The|ERROR:|Start the|Short the).*")
WORK = pathlib.Path(
    os.environ.get("FIREBREAK_SIM") or pathlib.Path.home() / ".cache/firebreak-sim"
)


@pytest.fixture
def plugger() -> Iterator[threading.Event]:
    stop = threading.Event()
    yield stop
    stop.set()


@pytest.fixture
def simulated() -> Iterator[None]:
    dot("destroy")
    yield
    dot("destroy")


def dot(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HERE / "dot.py"), *arguments],
        capture_output=True,
        check=False,
        text=True,
    )


def environment() -> dict[str, str]:
    return {
        **os.environ,
        "FIREBREAK_SIM_SPEED": os.environ.get("FIREBREAK_SIM_SPEED", "20"),
        "PATH": f"{HERE / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": str(HERE.parent),
        "PYTHONUNBUFFERED": "1",
        "XDG_CACHE_HOME": os.environ.get("FIREBREAK_SIM_CACHE")
        or str(pathlib.Path.home() / ".cache/firebreak-sim-cache"),
    }


def firebreak(*, arguments: list[str], log: pathlib.Path, seconds: int) -> str:
    with log.open(encoding="utf-8", mode="w") as output:
        try:
            subprocess.run(
                [
                    str(WORK / "venv/bin/python"),
                    "-m",
                    "firebreak",
                    *arguments,
                    "--no-update-check",
                ],
                check=False,
                env=environment(),
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                stdout=output,
                timeout=seconds,
            )
        except subprocess.TimeoutExpired:
            output.write(f"\n(stopped after {seconds} s)\n")
    return log.read_text(encoding="utf-8")


def plug_when_asked(*, log: pathlib.Path, stop: threading.Event) -> threading.Thread:
    def watch() -> None:
        while not stop.wait(timeout=0.2):
            if log.is_file() and PLUG_PROMPT.search(log.read_text(encoding="utf-8")):
                subprocess.run(
                    [str(WORK / "venv/bin/python"), str(HERE / "dot.py"), "plug"],
                    capture_output=True,
                    check=False,
                )
                return

    thread = threading.Thread(daemon=True, target=watch)
    thread.start()
    return thread


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--simulator",
        action="store_true",
        help="run the simulator's tests, which start Docker and take minutes",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--simulator"):
        return
    skip = pytest.mark.skip(reason="the simulator runs only with --simulator")
    for item in items:
        item.add_marker(skip)


def pytest_configure(config: pytest.Config) -> None:
    for device in DEVICES:
        config.addinivalue_line("markers", f"{device}: needs a simulated {device}")
    config.addinivalue_line("markers", "pr: one of the runs every pull request gets")


def verdict(*, said: str) -> str:
    found = VERDICT.search(said)
    if found:
        return found.group(0)[:76]
    return "no verdict; it ended:\n" + "\n".join(said.strip().splitlines()[-5:])
