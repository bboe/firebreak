from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

PYZ = pathlib.Path(__file__).resolve().parent.parent / "build" / "firebreak.pyz"


@pytest.mark.parametrize(
    "command",
    [["firebreak"], [sys.executable, "-m", "firebreak"], [sys.executable, str(PYZ)]],
    ids=["wheel", "module", "pyz"],
)
def test_help(command: list[str]) -> None:
    out = subprocess.run(
        [*command, "--help"], capture_output=True, check=True, text=True
    ).stdout
    assert out.startswith("usage: firebreak ")
