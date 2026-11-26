from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import TYPE_CHECKING

import pytest
import update_checker

from firebreak import __main__ as main
from firebreak.devices import BISCUIT, BUILDS, DEFAULTS, RADAR, TARGETS

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


def test_a_bare_run_prints_the_help_and_stops(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak"])
    with pytest.raises(SystemExit, match="1"):
        main.parsed()
    said = capsys.readouterr().out
    assert said.startswith("usage: firebreak")
    assert "arguments have changed" not in said


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
        match=r"the Echo \(2nd Generation\) has no stock build 5\.5\.0\.3\."
        r" `firebreak builds` lists",
    ):
        main.cli()


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
            ["--device", "biscuit", "amonet-radar-v1.0.1"],
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
    ("name", "version"),
    [
        ("update-kindle-biscuit_puffin-NS6575_user_8349_0013323246980.bin", "6.5.7.5"),
        ("update-kindle-biscuit_puffin-NS65751_user_8888_0013759592580.bin", "6575.1"),
        ("update-kindle-biscuit_puffin-NS65741_user_8146_0013222531716.bin", "6574.1"),
    ],
)
def test_a_fifth_codename_digit_names_a_patch_not_another_dot(
    *, name: str, version: str
) -> None:
    assert main.fireos_version(build="ignored", name=name) == version


@pytest.mark.parametrize(
    argnames=("arguments", "message"),
    argvalues=[
        (
            ["unlock", "fireos6", "--end-in-fireos"],
            "unrecognized arguments: --end-in-fireos",
        ),
        (["--end-in-fireos", "report"], "report takes no --end-in-fireos"),
        (["--no-wait", "unlock", "fireos6"], "unlock takes no --no-wait"),
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


@pytest.mark.parametrize(
    "name",
    ["amonet-biscuit-v1.1.0", "amonet-biscuit-v1.1.0-bboe", "amonet-biscuit-v2.0.0"],
)
def test_a_name_removed_in_1_0_is_refused(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", name])
    with pytest.raises(SystemExit, match="2"):
        main.parsed()
    assert "argument COMMAND: invalid choice" in capsys.readouterr().err


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


def test_ordered_puts_a_rebuild_after_its_version() -> None:
    assert main.ordered(builds=["5.5.0.3", "8149", "5.5.0.3-1973", "5.5.3.1"]) == [
        "8149",
        "5.5.3.1",
        "5.5.0.3-1973",
        "5.5.0.3",
    ]


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


def test_stock_asks_before_a_build_not_verified(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[bool, str]] = []
    monkeypatch.setattr(
        name="confirm",
        target=main,
        value=lambda *, force, what: asked.append((force, what)),
    )
    monkeypatch.setitem(
        BUILDS[RADAR],
        "8338",
        dataclasses.replace(BUILDS[RADAR]["8338"], verified=False),
    )
    main.stock_build(device=RADAR, force=False, wanted="8149")
    assert not asked
    main.stock_build(device=RADAR, force=True, wanted="8338")
    assert asked == [
        (
            True,
            (
                "stock 8338 has not been restored to and unlocked from on an Echo"
                " (2nd Generation), so this run would be its first"
            ),
        )
    ]


def test_stock_help_hides_no_wait(*, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main.build_parser().parse_args(["stock", "--help"])
    said = capsys.readouterr().out
    assert "--no-wait" not in said
    assert "--force" in said


@pytest.mark.parametrize("build", [[], ["8338"]])
def test_stock_takes_end_in_fireos(
    *, build: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", *build, "--end-in-fireos"]
    )
    assert main.parsed().end_in_fireos is True


def test_stock_takes_force(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "4405", "--force"]
    )
    assert main.parsed().force is True


def test_stock_takes_no_wait_as_force(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["firebreak", "stock", "--no-wait"]
    )
    assert main.parsed().force is True
    assert "--no-wait is deprecated and goes away in firebreak 2.0" in (
        capsys.readouterr().out
    )
    monkeypatch.setattr(name="argv", target=sys, value=["firebreak", "stock"])
    assert main.parsed().force is False
    assert not capsys.readouterr().out


@pytest.mark.parametrize(
    argnames=("arguments", "device", "build"),
    argvalues=[
        (["stock"], BISCUIT, "8349"),
        (["stock", "4315"], BISCUIT, "4315"),
        (["unlock", "fireos6"], BISCUIT, ""),
        (["stock"], RADAR, "8349"),
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


def test_the_builds_list_gives_each_device_a_block_newest_first() -> None:
    blocks = main.builds_list().split("\n\n")
    assert [block.partition("\n")[0] for block in blocks] == [
        "Echo Dot (2nd Generation), 8349 when left out:",
        "Echo Dot (3rd Generation), 8349 when left out:",
        "Echo (2nd Generation), 8349 when left out:",
    ]
    donut = blocks[1].split("\n")[1:]
    assert donut[0] == "  8349          Fire OS 6.5.7.5"
    assert donut[-1] == "  1895          Fire OS 6.5.2.9"


def test_the_builds_list_marks_a_build_not_verified(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        BUILDS[RADAR],
        "8338",
        dataclasses.replace(BUILDS[RADAR]["8338"], verified=False),
    )
    assert (
        "  8338          Fire OS 6.5.7.5, not yet verified on hardware"
        in main.builds_list()
    )


def test_the_help_lists_each_device_s_targets_its_default_first() -> None:
    lines = main.target_help().splitlines()
    assert lines[0] == "commands for the Echo Dot (2nd Generation):"
    assert lines.index("  stock [BUILD]") < lines.index(
        "  unlock [TARGET], where TARGET is one of:"
    )
    assert lines[lines.index("  unlock [TARGET], where TARGET is one of:") + 1] == (
        "    fireos6, the default"
    )


def test_the_stock_help_names_each_default_and_the_builds_command() -> None:
    text = " ".join(main.stock_builds_help().split())
    assert "8349 on the Echo Dot (3rd Generation)" in text
    assert "`firebreak builds` lists every build" in text
