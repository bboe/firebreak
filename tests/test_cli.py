from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

ZIPAPP = pathlib.Path(__file__).resolve().parent.parent / "build" / "firebreak.pyz"


@pytest.mark.parametrize(
    argnames="command",
    argvalues=[
        ["firebreak"],
        [sys.executable, "-m", "firebreak"],
        [sys.executable, str(ZIPAPP)],
    ],
    ids=["wheel", "module", "pyz"],
)
def test_help(*, command: list[str]) -> None:
    output = subprocess.run(
        args=[*command, "--help"], capture_output=True, check=True, text=True
    ).stdout
    assert output.startswith("usage: firebreak ")
