from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from conftest import HERE, verdict

if TYPE_CHECKING:
    import pathlib


PR = pytest.mark.pr


def route(
    *, arguments: list[str], device: str, out: pathlib.Path, start: str
) -> tuple[int, str]:
    ran = subprocess.run(
        [str(HERE / "run.sh"), str(out), *arguments],
        capture_output=True,
        check=False,
        env={**os.environ, "DEVICE": device, "START": start},
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=3600,
    )
    log = out.with_name(out.name + ".log")
    said = log.read_text(encoding="utf-8") if log.is_file() else ""
    return ran.returncode, said + ran.stderr


@pytest.mark.radar
def test_a_radar_backup_restores_onto_the_echo_it_came_from(
    *, tmp_path: pathlib.Path
) -> None:
    backup = tmp_path / "backup"
    status, said = route(
        arguments=["backup", str(backup)],
        device="radar",
        out=tmp_path / "backup-run",
        start="twrp",
    )
    assert status == 0, verdict(said=said)
    assert "is backed up to" in said, verdict(said=said)
    status, said = route(
        arguments=["restore", "--force", str(backup)],
        device="radar",
        out=tmp_path / "restore-run",
        start="fastboot",
    )
    assert status == 0, verdict(said=said)
    assert "holds the bytes of" in said, verdict(said=said)


@pytest.mark.parametrize(
    argnames=("device", "start", "arguments", "want"),
    argvalues=[
        pytest.param(
            "biscuit",
            "fastboot",
            ["unlock"],
            "is rooted: Fire OS 6",
            id="biscuit-unlock",
            marks=[pytest.mark.biscuit, PR],
        ),
        pytest.param(
            "biscuit",
            "twrp",
            ["stock"],
            "Stock 8349 is written",
            id="biscuit-stock",
            marks=[pytest.mark.biscuit, PR],
        ),
        pytest.param(
            "radar",
            "fastboot",
            ["unlock"],
            "is rooted: Fire OS 6",
            id="radar-unlock",
            marks=[pytest.mark.radar, PR],
        ),
        pytest.param(
            "donut",
            "stock-booted",
            ["unlock"],
            "is rooted: Fire OS 6",
            id="donut-unlock",
            marks=[pytest.mark.donut, PR],
        ),
        pytest.param(
            "biscuit",
            "fireos5",
            ["unlock", "--force"],
            "is rooted: Fire OS 6",
            id="biscuit-fireos5-move",
            marks=pytest.mark.biscuit,
        ),
        pytest.param(
            "biscuit",
            "fastboot",
            ["unlock", "--factory-reset", "--force"],
            "is rooted: Fire OS 6",
            id="biscuit-factory-reset",
            marks=pytest.mark.biscuit,
        ),
        pytest.param(
            "donut",
            "twrp",
            ["stock"],
            "runs stock 8349.",
            id="donut-stock",
            marks=pytest.mark.donut,
        ),
    ],
)
def test_a_route_reaches_its_target(
    *, arguments: list[str], device: str, start: str, tmp_path: pathlib.Path, want: str
) -> None:
    status, said = route(
        arguments=arguments, device=device, out=tmp_path / "run", start=start
    )
    assert status == 0, verdict(said=said)
    assert want in said, verdict(said=said)
