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


@pytest.mark.parametrize(
    argnames="arguments",
    argvalues=[["stock"], ["amonet-biscuit-v2.0.0", "8146"]],
    ids=["stock-alone", "build-without-stock"],
)
def test_only_stock_takes_a_build(*, arguments: list[str]) -> None:
    finished = subprocess.run(
        args=[sys.executable, "-m", "firebreak", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    assert finished.returncode == 2
    assert "stock takes a BUILD, and no other target does" in finished.stderr
