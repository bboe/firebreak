from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

import pytest
import update_checker

from firebreak import __main__ as main
from firebreak.devices import BISCUIT, DEFAULTS, RADAR, TARGETS

if TYPE_CHECKING:
    from firebreak.plugin import Device


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


def ran(*, device: Device, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="build", target=main.ARGUMENTS, value="")
    monkeypatch.setattr(name="factory_reset", target=main.ARGUMENTS, value=False)
    monkeypatch.setattr(name="target", target=main.ARGUMENTS, value="")
    monkeypatch.setattr(name="which", target=main.shutil, value=lambda **_: "adb")
    for name in ("check_adb", "check_python", "check_user", "make_cache"):
        monkeypatch.setattr(name=name, target=main, value=lambda: None)
    monkeypatch.setattr(
        name="choose_target",
        target=main,
        value=lambda *, name, **_: TARGETS[device][name or DEFAULTS.get(device)],
    )
    monkeypatch.setattr(name="bootrom_device", target=main, value=lambda: None)
    monkeypatch.setattr(name="root", target=main, value=lambda: sys.exit(0))
    monkeypatch.setattr(name="check_for_update", target=main, value=lambda: None)


def test_a_bare_run_says_what_replaced_the_default_and_stops(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak"])
    with pytest.raises(SystemExit, match="1"):
        main.parsed()
    said = capsys.readouterr().out
    out = " ".join(said.split())
    assert said.count("The command line arguments have changed") == 2
    assert (
        said.index("The command line arguments have changed")
        < said.index("usage: firebreak")
        < said.rindex("The command line arguments have changed")
    )
    assert "is now `firebreak unlock fireos5`" in out
    assert "the new default is `firebreak unlock fireos6`" in out
    assert "This warning goes away in firebreak 1.0" in out
    assert "usage: firebreak" in out


def test_a_bootrom_build_is_held_in_its_bootrom_instead_of_fastboot(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=BISCUIT, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="fastboot", target=main.SESSION, value=True)
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "5.5.0.3"]
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert main.SESSION.fastboot is True
    said = " ".join(capsys.readouterr().out.split())
    assert "cannot leave the Echo Dot (2nd Generation) in fastboot" in said
    assert "holds it in its bootrom" in said


def test_a_bootrom_names_the_device_before_the_target_is_chosen(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[Device | None] = []
    ran(device=RADAR, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="choose_target",
        target=main,
        value=lambda *, device, name, **_: (
            asked.append(device),
            TARGETS[RADAR][name or DEFAULTS[RADAR]],
        )[1],
    )
    monkeypatch.setattr(name="bootrom_device", target=main, value=lambda: RADAR)
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "unlock"])
    with pytest.raises(SystemExit):
        main.cli()
    assert asked == [RADAR]


def test_a_build_the_device_has_no_ota_for_is_refused(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=RADAR, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "5.5.0.3"]
    )
    with pytest.raises(
        main.FatalError,
        match=r"the Echo \(2nd Generation\) has no stock build 5\.5\.0\.3: use"
        r" one of 8349",
    ):
        main.cli()


def test_a_build_with_a_way_back_takes_no_flag_to_install(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=RADAR, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "stock", "8149"])
    with pytest.raises(expected_exception=SystemExit):
        main.cli()
    assert main.ARGUMENTS.build == "8149"


def test_a_build_with_no_way_back_is_marked_in_the_help() -> None:
    said = main.stock_builds_help()
    free, marked, gated = said.partition(
        "and, only with --no-way-back, which cannot be undone:"
    )
    assert marked
    assert "8349" in gated
    assert "8349" not in free
    assert "\n\n  Echo (2nd Generation), 8149 when left out:" in said


def test_a_build_with_no_way_back_needs_the_flag(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=RADAR, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "stock", "8338"])
    with pytest.raises(
        main.FatalError,
        match=r"stock 8338 ships a bootloader no payload here unlocks, so a"
        r" restore to it leaves an Echo \(2nd Generation\) that firebreak cannot"
        r" unlock again",
    ):
        main.cli()
    monkeypatch.setattr(
        name="argv",
        target=sys,
        value=["firebreak", "stock", "8338", "--no-way-back"],
    )
    with pytest.raises(expected_exception=SystemExit):
        main.cli()
    assert main.ARGUMENTS.build == "8338"


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
    "name",
    ["amonet-biscuit-v1.1.0", "amonet-biscuit-v1.1.0-bboe", "amonet-biscuit-v2.0.0"],
)
def test_a_deprecated_name_parses_but_is_not_in_the_help(
    *, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", name])
    assert main.parsed().command == name
    assert name not in main.target_help()


@pytest.mark.parametrize(
    argnames=("arguments", "said"),
    argvalues=[
        (
            ["--device", "biscuit", "amonet-radar-v1.0.0"],
            "argument COMMAND: invalid choice",
        ),
        (["--device", "radar", "unlock", "fireos5"], "unlock takes no --device"),
        (["--device", "crown"], "argument --device: invalid choice"),
        (["--device", "radar", "stock", "5.5.0.3"], "stock takes no --device"),
        (["--device", "biscuit", "survey", "x"], "survey takes no --device"),
    ],
    ids=[
        "unknown-target",
        "unlock",
        "device-without-targets",
        "stock",
        "survey",
    ],
)
def test_a_device_is_one_with_targets_and_only_the_short_takes_one(
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


@pytest.mark.parametrize(
    argnames=("arguments", "message"),
    argvalues=[
        (
            ["unlock", "fireos6", "--end-in-fireos"],
            "unrecognized arguments: --end-in-fireos",
        ),
        (["--end-in-fireos", "report"], "report takes no --end-in-fireos"),
        (["--no-wait", "unlock", "fireos6"], "unlock takes no --no-wait"),
        (
            ["--no-way-back", "unlock", "fireos6"],
            "unlock takes no --no-way-back",
        ),
        (["bootrom", "--device", "biscuit"], "bootrom takes no --device"),
        (["--device", "biscuit", "bootrom"], "bootrom takes no --device"),
        (["stock", "--device", "biscuit"], "stock takes no --device"),
    ],
)
def test_a_flag_is_refused_on_a_command_that_does_not_take_it(
    *,
    arguments: list[str],
    capsys: pytest.CaptureFixture[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", *arguments])
    with pytest.raises(SystemExit):
        main.parsed()
    assert message in capsys.readouterr().err


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


@pytest.mark.parametrize(
    ("arguments", "fastboot"), [([], True), (["--end-in-fireos"], False)]
)
def test_a_restore_ends_in_fastboot_unless_asked_for_fire_os(
    *, arguments: list[str], fastboot: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=BISCUIT, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="fastboot", target=main.SESSION, value=not fastboot)
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "8344", *arguments]
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert main.SESSION.fastboot is fastboot


def test_a_run_checks_for_an_update_once(*, monkeypatch: pytest.MonkeyPatch) -> None:
    checked: list[dict[str, str]] = []
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "unlock"])
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


def test_a_target_only_one_device_has_reads_no_bootrom(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=BISCUIT, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="bootrom_device", target=main, value=lambda: pytest.fail("read")
    )
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "unlock", "fireos5"]
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
        name="argv", target=sys, value=["firebreak", "--force", "report"]
    )
    with pytest.raises(SystemExit):
        main.parsed()
    assert "report takes no --force" in capsys.readouterr().err


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
        (["--force", "bootrom"], ("bootrom", "", True, None, False)),
        (["bootrom", "--force"], ("bootrom", "", True, None, False)),
        (
            ["--device", "biscuit", "short"],
            ("short", "", False, "biscuit", False),
        ),
        (
            ["short", "--device", "biscuit"],
            ("short", "", False, "biscuit", False),
        ),
        (
            ["--verbose", "unlock", "fireos6"],
            ("unlock", "", False, None, True),
        ),
        (
            ["unlock", "fireos6", "--verbose"],
            ("unlock", "", False, None, True),
        ),
        (["--verbose", "write-test"], ("write-test", "", False, None, True)),
        (["write-test", "--verbose"], ("write-test", "", False, None, True)),
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
        options.force,
        options.device,
        options.verbose,
    ) == parsed


def test_reset_is_refused_on_a_command_that_installs_no_fire_os_6(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "--factory-reset", "stock"]
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert "stock takes no --factory-reset" in capsys.readouterr().err
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "--factory-reset"]
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert "unrecognized arguments: --factory-reset" in capsys.readouterr().err


def test_reset_is_refused_on_a_target_that_installs_no_fire_os_6(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=BISCUIT, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="argv",
        target=sys,
        value=["firebreak", "unlock", "fireos5", "--factory-reset"],
    )
    with pytest.raises(main.FatalError, match="fireos5 takes no --factory-reset"):
        main.cli()


@pytest.mark.parametrize("device", [BISCUIT, RADAR], ids=["biscuit", "radar"])
def test_reset_reaches_a_fire_os_6_unlock(
    *, device: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(device=device, monkeypatch=monkeypatch)
    monkeypatch.setattr(
        name="argv",
        target=sys,
        value=["firebreak", "unlock", "fireos6", "--factory-reset"],
    )
    with pytest.raises(SystemExit):
        main.cli()
    assert main.ARGUMENTS.factory_reset is True


@pytest.mark.parametrize("build", [[], ["8338"]])
def test_stock_takes_end_in_fireos(
    *, build: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", *build, "--end-in-fireos"]
    )
    assert main.parsed().end_in_fireos is True


def test_stock_takes_no_wait(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "--no-wait"]
    )
    assert main.parsed().no_wait is True
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "stock"])
    assert main.parsed().no_wait is False


@pytest.mark.parametrize(
    argnames=("arguments", "device", "build"),
    argvalues=[
        (["stock"], BISCUIT, "8149"),
        (["stock", "4315"], BISCUIT, "4315"),
        (["unlock", "fireos6"], BISCUIT, ""),
        (["stock"], RADAR, "8149"),
    ],
    ids=["stock-alone", "stock-with-a-build", "another-target", "radar-stock"],
)
def test_the_build_each_target_gets(
    *,
    arguments: list[str],
    build: str,
    device: Device,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran(device=device, monkeypatch=monkeypatch)
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", *arguments])
    with pytest.raises(SystemExit):
        main.cli()
    assert main.ARGUMENTS.build == build


def test_the_help_lists_each_device_s_targets_its_default_first() -> None:
    lines = main.target_help().splitlines()
    assert lines[0] == "commands for the Echo Dot (2nd Generation):"
    assert lines.index("  stock [BUILD]") < lines.index(
        "  unlock [TARGET], where TARGET is one of:"
    )
    assert lines[lines.index("  unlock [TARGET], where TARGET is one of:") + 1] == (
        "    fireos6, the default"
    )
