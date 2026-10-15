from __future__ import annotations

import argparse
import sys

import pytest
import update_checker

from firebreak import __main__ as main


def parse_into_namespace(*, monkeypatch: pytest.MonkeyPatch) -> None:
    subparsers = argparse._SubParsersAction  # ruff: ignore[private-member-access]

    def call(
        self: argparse._SubParsersAction,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: list[str],
        option_string: str | None = None,  # ruff: ignore[unused-function-argument]
    ) -> None:
        name, *rest = values
        setattr(namespace, self.dest, name)
        chosen = self._name_parser_map[name]
        _, extras = chosen.parse_known_args(rest, namespace)
        if extras:
            parser.error(message="unrecognized arguments: " + " ".join(extras))

    monkeypatch.setattr(name="__call__", target=subparsers, value=call)


def test_a_child_does_not_check_for_an_update(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "_child", "emos", "find", "any"]
    )
    monkeypatch.setattr(name="child_main", target=main, value=lambda **_: 0)
    monkeypatch.setattr(
        name="check_for_update", target=main, value=lambda: pytest.fail("checked")
    )
    with pytest.raises(SystemExit, match="0"):
        main.main()


@pytest.mark.parametrize(
    argnames=("arguments", "said"),
    argvalues=[
        (
            ["--device", "biscuit", "amonet-radar-v1.0.0"],
            "argument TARGET|COMMAND: invalid choice",
        ),
        (["--device", "radar"], "argument --device: invalid choice"),
        (
            ["--device", "biscuit", "survey", "x"],
            "survey takes no --device",
        ),
    ],
    ids=["unknown-target", "device-without-targets", "survey"],
)
def test_a_device_is_one_with_targets_and_survey_takes_none(
    *,
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    said: str,
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", *arguments])
    with pytest.raises(SystemExit):
        main.cli()
    assert said in capsys.readouterr().err


def test_a_failing_update_check_is_silent(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def failed(*_: object, **__: str) -> None:
        raise RuntimeError

    monkeypatch.setattr(name="check", target=update_checker.UpdateChecker, value=failed)
    main.check_for_update()
    assert capsys.readouterr() == ("", "")


def test_a_newer_release_is_named_with_how_to_upgrade(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    newer = update_checker.UpdateResult(
        available="9.0.0",
        package="firebreak",
        release_date=None,
        running=main.__version__,
    )
    monkeypatch.setattr(
        name="check", target=update_checker.UpdateChecker, value=lambda *_, **__: newer
    )
    command = "/a/very/long/path/to/a/virtual/environment/bin/python3 -m pip install"
    monkeypatch.setattr(name="upgrade", target=main, value=lambda: ("run", command))
    main.check_for_update()
    out, err = capsys.readouterr()
    *notice, line = out.splitlines()
    assert " ".join(" ".join(notice).split()) == (
        f"Version {main.__version__} of firebreak is outdated. Version 9.0.0 is"
        " available. To use it, run:"
    )
    assert line == "  " + command
    assert err == ""


def test_a_refused_user_stops_before_the_update_check(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak"])
    monkeypatch.setattr(name="which", target=main.shutil, value=lambda **_: "adb")
    monkeypatch.setattr(name="check_user", target=main, value=lambda: sys.exit(1))
    monkeypatch.setattr(
        name="check_for_update", target=main, value=lambda: pytest.fail("checked")
    )
    with pytest.raises(SystemExit):
        main.cli()


def test_a_run_checks_for_an_update_once(*, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[dict[str, str]] = []
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak"])
    monkeypatch.setattr(name="which", target=main.shutil, value=lambda **_: "adb")
    monkeypatch.setattr(name="check_user", target=main, value=lambda: None)
    monkeypatch.setattr(name="check_adb", target=main, value=lambda: sys.exit(1))
    monkeypatch.setattr(
        name="check",
        target=update_checker.UpdateChecker,
        value=lambda _, **options: checked.append(options),
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert checked == [
        {"package_name": "firebreak", "package_version": main.__version__}
    ]


@pytest.mark.parametrize(
    ("raised", "said"),
    [
        (main.FatalError(message="no download link"), "ERROR: no download link"),
        (KeyboardInterrupt(), "stopped"),
        (
            main.subprocess.TimeoutExpired(cmd=["adb", "get-state"], timeout=30),
            "ERROR: adb get-state did not finish in 30 seconds",
        ),
    ],
)
def test_a_run_that_stops_exits_with_what_it_says(
    *, monkeypatch: pytest.MonkeyPatch, raised: BaseException, said: str
) -> None:
    def cli() -> None:
        raise raised

    monkeypatch.setattr(name="argv", target=sys, value=["firebreak"])
    monkeypatch.setattr(name="cli", target=main, value=cli)
    with pytest.raises(SystemExit) as stopped:
        main.main()
    assert str(stopped.value) == said


def test_a_run_with_no_update_check_does_not_check(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "--no-update-check"]
    )
    monkeypatch.setattr(name="which", target=main.shutil, value=lambda **_: "adb")
    monkeypatch.setattr(name="check_user", target=main, value=lambda: None)
    monkeypatch.setattr(name="check_adb", target=main, value=lambda: sys.exit(1))
    monkeypatch.setattr(
        name="check_for_update", target=main, value=lambda: pytest.fail("checked")
    )
    with pytest.raises(SystemExit):
        main.cli()


@pytest.mark.parametrize("into_namespace", [False, True], ids=["3.9.6", "bpo-45235"])
def test_an_option_before_a_command_that_does_not_take_it_is_refused(
    *,
    capsys: pytest.CaptureFixture[str],
    into_namespace: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if into_namespace:
        parse_into_namespace(monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "--short", "report"]
    )
    with pytest.raises(SystemExit):
        main.parsed()
    assert "report takes no --short" in capsys.readouterr().err


def test_no_newer_release_says_nothing(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="check", target=update_checker.UpdateChecker, value=lambda *_, **__: None
    )
    main.check_for_update()
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(
    argnames=("arguments", "parsed"),
    argvalues=[
        ([], (None, "", False, None, False)),
        (["--short"], (None, "", True, None, False)),
        (["--short", "stock"], ("stock", "8149", True, None, False)),
        (["stock", "4315", "--short"], ("stock", "4315", True, None, False)),
        (
            ["--verbose", "--device", "biscuit", "amonet-biscuit-v2.0.0"],
            ("amonet-biscuit-v2.0.0", "", False, "biscuit", True),
        ),
        (
            ["amonet-biscuit-v2.0.0", "--device", "biscuit", "--verbose"],
            ("amonet-biscuit-v2.0.0", "", False, "biscuit", True),
        ),
        (["--short", "write-test"], ("write-test", "", True, None, False)),
        (["write-test", "--short"], ("write-test", "", True, None, False)),
        (["report", "--verbose"], ("report", "", False, None, True)),
    ],
)
@pytest.mark.parametrize("into_namespace", [False, True], ids=["3.9.6", "bpo-45235"])
def test_options_count_before_or_after_the_target_or_command(
    *,
    arguments: list[str],
    into_namespace: bool,
    monkeypatch: pytest.MonkeyPatch,
    parsed: tuple[object, ...],
) -> None:
    if into_namespace:
        parse_into_namespace(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", *arguments])
    options = main.parsed()
    assert (
        options.command,
        options.build,
        options.short,
        options.device,
        options.verbose,
    ) == parsed


@pytest.mark.parametrize(
    argnames=("arguments", "build"),
    argvalues=[
        (["stock"], "8149"),
        (["stock", "4315"], "4315"),
        (["amonet-biscuit-v2.0.0"], ""),
    ],
    ids=["stock-alone", "stock-with-a-build", "another-target"],
)
def test_the_build_each_target_gets(
    *, arguments: list[str], build: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="build", target=main.ARGUMENTS, value="")
    monkeypatch.setattr(name="target", target=main.ARGUMENTS, value="")
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", *arguments])
    monkeypatch.setattr(name="which", target=main.shutil, value=lambda **_: "adb")
    monkeypatch.setattr(name="check_user", target=main, value=lambda: sys.exit(1))
    with pytest.raises(SystemExit):
        main.cli()
    assert main.ARGUMENTS.build == build


def test_the_help_lists_each_device_s_targets_its_default_first() -> None:
    assert main.target_help().splitlines()[:3] == [
        "targets for the Echo Dot (2nd Generation):",
        "  amonet-biscuit-v1.1.0-bboe, the default",
        "      rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP 3.7.0_9-bboe2.",
    ]
    assert "  stock [BUILD]" in main.target_help().splitlines()
