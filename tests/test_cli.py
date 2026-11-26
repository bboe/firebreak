from __future__ import annotations

import importlib.metadata
import os
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

from firebreak import __version__
from firebreak.devices import BUILDS
from firebreak.host import NO_ACCESS

PLAIN = {
    **{key: value for key, value in os.environ.items() if key != "FORCE_COLOR"},
    "COLUMNS": "80",
    "NO_COLOR": "1",
}
ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_builds_lists_every_build_with_its_fire_os_version() -> None:
    output = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "builds"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    listed = re.findall(r"^  (\S+) +Fire OS (\S+)$", output, flags=re.MULTILINE)
    assert sorted(build for build, _ in listed) == sorted(
        build for builds in BUILDS.values() for build in builds
    )
    assert ("8138", "6574.1") in listed
    assert ("8349", "6.5.7.5") in listed
    assert ("5.5.0.3-1973", "5.5.0.3") in listed


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
    ],
    ids=["wheel", "module"],
)
def test_help(*, command: list[str]) -> None:
    output = subprocess.run(
        args=[*command, "--help"],
        capture_output=True,
        check=True,
        env=PLAIN,
        text=True,
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
        (
            ["stock", "9999"],
            "no Echo has a stock build 9999. `firebreak builds` lists",
        ),
        (["survey"], "the following arguments are required: OTA"),
        (["--force", "survey", "x.zip"], "survey takes no --force"),
        (["report", "--force"], "unrecognized arguments: --force"),
        (["report", "8149"], "unrecognized arguments: 8149"),
        (["--factory-reset", "write-test"], "write-test takes no --factory-reset"),
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


def test_the_readme_gives_the_help_a_run_prints() -> None:
    output = subprocess.run(
        args=[sys.executable, "-m", "firebreak", "--help"],
        capture_output=True,
        check=True,
        env=PLAIN,
        text=True,
    ).stdout.replace("\noptional arguments:\n", "\noptions:\n")
    assert f"```text\n{output.rstrip()}\n```" in (ROOT / "README.md").read_text()


def test_the_readme_gives_the_udev_commands_a_run_prints() -> None:
    commands = NO_ACCESS.split("\n\n")[1]
    assert f"```sh\n{commands}\n```" in (ROOT / "README.md").read_text()
    rules = commands.split("<<'EOF'\n")[1].split("\nEOF")[0]
    unlocking = (ROOT / "docs" / "unlocking.md").read_text()
    assert textwrap.indent(rules, "  ") in unlocking


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
