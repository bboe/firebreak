from __future__ import annotations

import importlib.metadata
import pathlib
import re
import subprocess
import sys
import zipfile

import pytest

from firebreak import __version__
from firebreak.devices.biscuit import BUILDS

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZIPAPP = ROOT / "build" / "firebreak.pyz"


def test_credits_name_every_link_the_readme_credits() -> None:
    output = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "--credits"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    readme = (ROOT / "README.md").read_text()
    section = readme.split("\n## Credits\n")[1].split("\n## ")[0]
    assert set(re.findall(r"\]\((https://[^)]+)\)", section)) == set(
        re.findall(r"https://\S+", output)
    )


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
        args=[sys.executable, "-m", "firebreak", "unlock", "fireos6", "8146"],
        capture_output=True,
        check=False,
        text=True,
    )
    assert finished.returncode == 2
    assert "unrecognized arguments: 8146" in finished.stderr


def test_stock_help_lists_the_builds() -> None:
    output = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "stock", "-h"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert all(build in " ".join(output.split()) for build in BUILDS)


def test_survey_takes_options_before_it(*, tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(data=b"not a zip")
    finished = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "--verbose", "survey", str(bad)],
        capture_output=True,
        check=False,
        text=True,
    )
    assert finished.returncode == 1
    assert "could not survey bad.zip" in finished.stderr


@pytest.mark.parametrize(
    argnames=("arguments", "message"),
    argvalues=[
        (["stock", "4315", "8146"], "unrecognized arguments: 8146"),
        (["stock", "9999"], "argument BUILD: invalid choice: '9999'"),
        (["survey"], "the following arguments are required: OTA"),
        (["--short", "survey", "x.zip"], "survey takes no --short"),
        (["report", "--short"], "unrecognized arguments: --short"),
        (["report", "8149"], "unrecognized arguments: 8149"),
        (["--device", "biscuit", "write-test"], "write-test takes no --device"),
    ],
)
def test_the_positional_arguments_are_checked(
    *, arguments: list[str], message: str
) -> None:
    finished = subprocess.run(
        args=[sys.executable, "-m", "firebreak", *arguments],
        capture_output=True,
        check=False,
        text=True,
    )
    assert finished.returncode == 2
    assert message in finished.stderr


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


def test_the_wheel_takes_its_version_from_the_package() -> None:
    assert importlib.metadata.version("firebreak") == __version__


def test_version() -> None:
    output = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "--version"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    assert output == f"firebreak {__version__}\n"
