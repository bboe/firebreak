from __future__ import annotations

import sys

import pytest
import update_checker

from firebreak import __main__ as main


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


def test_no_newer_release_says_nothing(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="check", target=update_checker.UpdateChecker, value=lambda *_, **__: None
    )
    main.check_for_update()
    assert capsys.readouterr() == ("", "")


def test_target_names_are_the_unlocks_names() -> None:
    assert main.AMONET_BISCUIT_V1_1_0 == "amonet-biscuit-v1.1.0"
    assert main.AMONET_BISCUIT_V1_1_0_BBOE == "amonet-biscuit-v1.1.0-bboe"
    assert main.AMONET_BISCUIT_V2_0_0 == "amonet-biscuit-v2.0.0"
