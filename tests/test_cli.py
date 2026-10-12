from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import zipfile

import pytest

from firebreak import __version__

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZIPAPP = ROOT / "build" / "firebreak.pyz"


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


def test_only_stock_takes_a_build() -> None:
    finished = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "amonet-biscuit-v2.0.0", "8146"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert finished.returncode == 2
    assert "only stock takes a BUILD" in finished.stderr


def test_the_pyz_holds_the_pinned_update_checker() -> None:
    with zipfile.ZipFile(file=ZIPAPP) as archive:
        names = set(archive.namelist())
    assert "update_checker/core.py" in names
    assert "update_checker-1.0.1.dist-info/licenses/LICENSE.txt" in names
    assert not any(name.startswith("serial") for name in names)


def test_the_pyz_imports_its_update_checker() -> None:
    script = (
        "import sys; sys.path.insert(0, sys.argv[1]); import update_checker;"
        " print(update_checker.__file__.startswith(sys.argv[1]),"
        " update_checker.__version__)"
    )
    said = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script, str(ZIPAPP)],
        capture_output=True,
        check=True,
        text=True,
    )
    assert said.stdout == "True 1.0.1\n"


def test_the_version_matches_pyproject() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(
        flags=re.MULTILINE, pattern=r'^version = "([^"]+)"$', string=pyproject
    )
    assert version, "pyproject.toml has no version"
    assert version[1] == __version__
