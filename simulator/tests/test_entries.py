from __future__ import annotations

import dataclasses
import os
from typing import TYPE_CHECKING

import pytest
from conftest import dot, firebreak, plug_when_asked, verdict

if TYPE_CHECKING:
    import pathlib
    import threading

A = "is in unlocked fastboot."
AH = "already waits in its bootrom."
CYCLE = "waits in its bootrom, and nothing here restarts it"
D_GESTURE = "Start the Echo Dot (3rd Generation)'s fastboot"
GESTURE = "Start the Echo Dot (2nd Generation)'s fastboot"
H = "waits in its bootrom."
LOCKED = "is locked, so reaching a TWRP unlocks it"
NOT_AMONET = "Echo Dot (3rd Generation), which amonet does not unlock"
NO_CHAIN = "has no bootrom chain for the Echo Dot (3rd Generation)"
NO_WAY = "reads as stock-booted, which nothing here"
REFUSED = "locked, and a locked bootloader"
RUNS = "runs its firmware, read as stock-booted."
STOCK = "is in stock fastboot."
T = "is in TWRP."


@dataclasses.dataclass(frozen=True)
class Case:
    name: str
    device: str
    start: str
    command: tuple[str, ...]
    first: str
    second: str
    prep: tuple[str, ...] = ()
    seconds: int = 600


CASES = (
    Case("fb-twrp", "biscuit", "twrp", ("fastboot",), A, A),
    Case("fb-stockfb", "biscuit", "fastboot", ("fastboot",), STOCK, STOCK),
    Case("twrp-twrp", "biscuit", "twrp", ("twrp",), T, T),
    Case("twrp-stockfb", "biscuit", "fastboot", ("twrp",), LOCKED, LOCKED),
    Case("twrpf-stockfb", "biscuit", "fastboot", ("twrp", "--force"), T, T),
    Case("twrp-amonetfb", "biscuit", "twrp", ("twrp",), T, T, prep=("fastboot",)),
    Case("brom-twrp", "biscuit", "twrp", ("bootrom", "--force"), H, AH),
    Case(
        "brom-stockfb", "biscuit", "fastboot", ("bootrom", "--force"), REFUSED, REFUSED
    ),
    Case(
        "brom-amonetfb",
        "biscuit",
        "twrp",
        ("bootrom", "--force"),
        H,
        AH,
        prep=("fastboot",),
    ),
    Case("short-dark", "biscuit", "no-light", ("short", "--device", "biscuit"), H, AH),
    Case(
        "brom-booted", "biscuit", "stock-booted", ("bootrom", "--force"), NO_WAY, NO_WAY
    ),
    Case(
        "fb-booted",
        "biscuit",
        "stock-booted",
        ("fastboot",),
        GESTURE,
        GESTURE,
        seconds=60,
    ),
    Case(
        "twrp-booted",
        "biscuit",
        "stock-booted",
        ("twrp",),
        GESTURE,
        GESTURE,
        seconds=60,
    ),
    Case("rb-twrp", "biscuit", "twrp", ("reboot",), RUNS, RUNS),
    Case("rb-stockfb", "biscuit", "fastboot", ("reboot",), RUNS, RUNS),
    Case("rb-amonetfb", "biscuit", "twrp", ("reboot",), RUNS, RUNS, prep=("fastboot",)),
    Case(
        "rb-brom",
        "biscuit",
        "twrp",
        ("reboot",),
        CYCLE,
        CYCLE,
        prep=("bootrom", "--force"),
    ),
    Case("rb-booted", "biscuit", "stock-booted", ("reboot",), RUNS, RUNS),
    Case("r-fb-twrp", "radar", "twrp", ("fastboot",), A, A),
    Case("r-twrp-twrp", "radar", "twrp", ("twrp",), T, T),
    Case("r-brom-twrp", "radar", "twrp", ("bootrom", "--force"), H, AH),
    Case("r-short-dark", "radar", "no-light", ("short", "--device", "radar"), H, AH),
    Case("r-rb-twrp", "radar", "twrp", ("reboot",), RUNS, RUNS),
    Case("d-fb-twrp", "donut", "twrp", ("fastboot",), A, A),
    Case("d-fb-stockfb", "donut", "fastboot", ("fastboot",), STOCK, STOCK),
    Case("d-twrp-twrp", "donut", "twrp", ("twrp",), T, T),
    Case("d-twrp-amonetfb", "donut", "twrp", ("twrp",), T, T, prep=("fastboot",)),
    Case("d-twrp-stockfb", "donut", "fastboot", ("twrp", "--force"), T, T),
    Case("d-brom-twrp", "donut", "twrp", ("bootrom", "--force"), NO_CHAIN, NO_CHAIN),
    Case(
        "d-short",
        "donut",
        "twrp",
        ("short", "--device", "donut"),
        NOT_AMONET,
        NOT_AMONET,
    ),
    Case(
        "d-fb-booted",
        "donut",
        "stock-booted",
        ("fastboot",),
        D_GESTURE,
        D_GESTURE,
        seconds=60,
    ),
    Case("d-rb-twrp", "donut", "twrp", ("reboot",), RUNS, RUNS),
    Case("d-rb-stockfb", "donut", "fastboot", ("reboot",), RUNS, RUNS),
    Case("d-rb-booted", "donut", "stock-booted", ("reboot",), RUNS, RUNS),
)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=case.name, marks=getattr(pytest.mark, case.device))
        for case in CASES
    ],
)
@pytest.mark.usefixtures("simulated")
def test_an_entry_command_says_where_it_left_the_echo_twice(
    *, case: Case, plugger: threading.Event, tmp_path: pathlib.Path
) -> None:
    created = dot(
        "create",
        "--device",
        case.device,
        "--runner",
        str(os.getpid()),
        "--start",
        case.start,
    )
    assert created.returncode == 0, created.stdout + created.stderr
    first = tmp_path / "first.log"
    watcher = (
        plug_when_asked(log=first, stop=plugger)
        if case.start == "no-light" or case.device == "donut"
        else None
    )
    if case.prep:
        firebreak(arguments=list(case.prep), log=tmp_path / "prep.log", seconds=600)
    said = firebreak(arguments=list(case.command), log=first, seconds=case.seconds)
    assert case.first in said, verdict(said=said)
    if watcher is not None:
        plugger.set()
        watcher.join()
    said = firebreak(
        arguments=list(case.command), log=tmp_path / "second.log", seconds=case.seconds
    )
    assert case.second in said, verdict(said=said)
