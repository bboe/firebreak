from __future__ import annotations

import types
from typing import TYPE_CHECKING

import pytest

from firebreak import entry
from firebreak.devices import BISCUIT, CROWN, RADAR
from firebreak.states import State
from firebreak.ui import ARGUMENTS, SESSION, FatalError

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterable


NOTHING = types.SimpleNamespace(device=None)


def bootrom(*, monkeypatch: pytest.MonkeyPatch, states: Iterable[State]) -> list[str]:
    done = reads(monkeypatch=monkeypatch, states=states)
    monkeypatch.setattr(
        name="amonet_payload", target=entry, value=lambda: "payload.bin"
    )
    monkeypatch.setattr(name="pyserial_wheel", target=entry, value=lambda: None)
    monkeypatch.setattr(name="ask_for_short", target=entry, value=lambda: None)
    monkeypatch.setattr(
        name="clear_boot0", target=entry, value=lambda: done.append("cleared")
    )
    monkeypatch.setattr(
        name="erase_by_fastboot", target=entry, value=lambda: done.append("erased")
    )
    monkeypatch.setattr(
        name="run", target=entry, value=lambda **_: done.append("rebooted")
    )
    monkeypatch.setattr(
        name="bootrom_client",
        target=entry,
        value=lambda **options: (
            done.append(
                "looked for the bootrom" + (" to erase for" if options["erase"] else "")
            ),
            types.SimpleNamespace(port=types.SimpleNamespace(close=lambda: None)),
        )[1],
    )
    monkeypatch.setattr(
        name="exploit", target=entry, value=lambda **_: done.append("ran the payload")
    )
    return done


def reads(*, monkeypatch: pytest.MonkeyPatch, states: Iterable[State]) -> list[str]:
    done: list[str] = []
    reported = iter(states)
    monkeypatch.setattr(name="device", target=SESSION, value=BISCUIT)
    monkeypatch.setattr(name="sleep", target=entry.time, value=lambda _: None)
    monkeypatch.setattr(name="state", target=entry, value=lambda: next(reported))
    monkeypatch.setattr(
        name="reboot",
        target=entry,
        value=lambda **options: done.append(
            "reboot " + options.get("into", "recovery")
        ),
    )
    for name in ("stage_amonet_recovery", "stage_fastbrick", "stage_fireos5_recovery"):
        monkeypatch.setattr(
            name=name,
            target=entry,
            value=lambda name=name, **options: done.append(
                name + (" restart only" if options.get("carries_twrp") is False else "")
            ),
        )
    monkeypatch.setattr(
        name="confirm",
        target=entry,
        value=lambda **options: done.append("asked: " + options["what"]),
    )
    monkeypatch.setattr(
        name="say", target=entry, value=lambda **options: done.append(options["text"])
    )
    monkeypatch.setattr(
        name="restart_refusals",
        target=entry,
        value=lambda: done.append("restarted") and [],
    )
    return done


def test_a_bootrom_entry_asks_before_it_erases_boot0(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = bootrom(monkeypatch=monkeypatch, states=[State.AMONET_FASTBOOT])
    entry.bootrom_entry(force=False, short=False)
    assert "asked: erasing boot0 leaves" in done[0]
    assert done[1:3] == ["erased", "looked for the bootrom to erase for"]
    assert "boot0 is erased" in done[-1]
    assert entry.ERASED.read_text(encoding="utf-8") == "biscuit"
    assert not entry.HELD.exists()


@pytest.mark.parametrize(
    "state", [State.AMONET_TWRP, State.AMONET_FASTBOOT], ids=["twrp", "fastboot"]
)
def test_a_bootrom_entry_clears_no_boot0_it_cannot_write_back(
    *, monkeypatch: pytest.MonkeyPatch, state: State
) -> None:
    done = bootrom(monkeypatch=monkeypatch, states=[state])
    monkeypatch.setattr(name="device", target=SESSION, value=CROWN)
    monkeypatch.setattr(name="target", target=ARGUMENTS, value="")
    with pytest.raises(FatalError, match="no bootrom chain for the Echo Show 8"):
        entry.bootrom_entry(force=True, short=False)
    assert done == []
    assert not entry.ERASED.exists()


def test_a_bootrom_entry_from_a_recovery_clears_the_header(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = bootrom(monkeypatch=monkeypatch, states=[State.AMONET_TWRP])
    entry.bootrom_entry(force=True, short=False)
    assert done[1:4] == ["cleared", "rebooted", "looked for the bootrom"]


def test_a_bootrom_entry_refuses_a_locked_bootloader(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootrom(monkeypatch=monkeypatch, states=[State.STOCK_FASTBOOT])
    with pytest.raises(FatalError, match="a locked bootloader refuses to erase"):
        entry.bootrom_entry(force=True, short=False)


def test_a_bootrom_entry_refuses_a_state_with_no_way_in(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootrom(monkeypatch=monkeypatch, states=[State.NONE])
    with pytest.raises(FatalError, match="reads as none, which nothing here can"):
        entry.bootrom_entry(force=True, short=False)


def test_a_bootrom_entry_reports_a_hold_it_finds(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    bootrom(monkeypatch=monkeypatch, states=[])
    entry.HELD.write_text(data="biscuit", encoding="utf-8")
    monkeypatch.setattr(name="device", target=SESSION, value=None)
    monkeypatch.setattr(name="identify", target=entry, value=lambda: NOTHING)
    monkeypatch.setattr(
        name="attach_held_payload",
        target=entry,
        value=lambda **_: types.SimpleNamespace(
            port=types.SimpleNamespace(close=lambda: None)
        ),
    )
    entry.bootrom_entry(force=False, short=False)
    said = capsys.readouterr().out
    assert "The Echo Dot (2nd Generation) already waits in its bootrom" in said


def test_a_bootrom_entry_stops_where_the_erase_fails(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = bootrom(monkeypatch=monkeypatch, states=[State.AMONET_FASTBOOT])
    monkeypatch.setattr(
        name="erase_by_fastboot",
        target=entry,
        value=lambda: "fastboot erase boot0 failed:\nFAILED (remote: unknown command)",
    )
    with pytest.raises(FatalError, match="fastboot erase boot0 failed"):
        entry.bootrom_entry(force=True, short=False)
    assert "looked for the bootrom to erase for" not in done


def test_a_bootrom_entry_takes_the_device_from_the_marker(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootrom(monkeypatch=monkeypatch, states=[State.NONE])
    entry.ERASED.write_text(data="radar", encoding="utf-8")
    monkeypatch.setattr(name="device", target=SESSION, value=None)
    monkeypatch.setattr(name="identify", target=entry, value=lambda: NOTHING)
    monkeypatch.setattr(
        name="attach_held_payload", target=entry, value=lambda **_: None
    )
    with pytest.raises(entry.FatalError, match="reads as none"):
        entry.bootrom_entry(force=False, short=False)
    assert SESSION.device is not None
    assert SESSION.device.name == "radar"


def test_a_bootrom_entry_with_no_bootrom_to_find(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootrom(monkeypatch=monkeypatch, states=[State.AMONET_TWRP])
    monkeypatch.setattr(name="bootrom_client", target=entry, value=lambda **_: None)
    with pytest.raises(FatalError, match="did not reach its bootrom"):
        entry.bootrom_entry(force=True, short=True)


def test_a_fastboot_entry_reboots_an_echo_that_answers_adb(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch,
        states=[State.AMONET_BOOTED, State.STARTING, State.AMONET_FASTBOOT],
    )
    entry.fastboot_entry()
    assert done == ["reboot bootloader"]


def test_a_fastboot_entry_that_is_there_already_does_nothing(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(monkeypatch=monkeypatch, states=[State.STOCK_FIREOS5_FASTBOOT])
    entry.fastboot_entry()
    assert done == []


def test_a_fastboot_entry_waits_for_the_gesture_without_a_limit(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch,
        states=[*[State.STOCK_BOOTED] * 4, State.STOCK_FASTBOOT],
    )
    monkeypatch.setattr(name="monotonic", target=entry.time, value=lambda: 0.0)
    entry.fastboot_entry()
    assert len(done) == 1
    assert "Start the Echo Dot (2nd Generation)'s fastboot" in done[0]


def test_a_short_bootrom_entry_holds_the_payload(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = bootrom(monkeypatch=monkeypatch, states=[])
    entry.bootrom_entry(force=False, short=True)
    assert done[:2] == ["looked for the bootrom", "ran the payload"]
    assert "the next run joins that payload" in done[2]
    assert entry.HELD.read_text(encoding="utf-8") == "biscuit"
    assert not entry.ERASED.exists()
    assert entry.SESSION.held is True


def test_a_twrp_entry_asks_before_it_unlocks_a_locked_echo(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch, states=[State.STOCK_FASTBOOT, State.AMONET_TWRP]
    )
    monkeypatch.setattr(name="device", target=SESSION, value=None)
    monkeypatch.setattr(name="target", target=ARGUMENTS, value="")
    monkeypatch.setattr(
        name="identify",
        target=entry,
        value=lambda: types.SimpleNamespace(device=BISCUIT),
    )
    entry.twrp_entry(force=False)
    assert done[1] == "stage_fastbrick"
    assert "unlocks it first, which erases everything on it" in done[0]
    assert "asked: the Echo Dot (2nd Generation) is locked" in done[0]


def test_a_twrp_entry_from_the_fireos5_fastboot_writes_that_chain_s_twrp(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch,
        states=[State.AMONET_FIREOS5_FASTBOOT, State.AMONET_FIREOS5_BBOE_TWRP],
    )
    entry.twrp_entry(force=True)
    assert done[1] == "stage_fireos5_recovery"
    assert "and its TEE beside it" in done[0]
    assert "restarted" not in done


def test_a_twrp_entry_reboots_a_rooted_echo(*, monkeypatch: pytest.MonkeyPatch) -> None:
    done = reads(monkeypatch=monkeypatch, states=[State.ROOTED, State.AMONET_TWRP])
    entry.twrp_entry(force=False)
    assert done == ["reboot recovery"]


def test_a_twrp_entry_restarts_an_unlocked_echo_without_a_write(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch,
        states=[State.AMONET_FASTBOOT, State.AMONET_TWRP, State.AMONET_TWRP],
    )
    entry.twrp_entry(force=False)
    assert done == ["restarted"]


def test_a_twrp_entry_says_what_to_do_where_the_recovery_is_not_a_twrp(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads(monkeypatch=monkeypatch, states=[State.AMONET_FASTBOOT])
    monkeypatch.setattr(name="RECOVERY_WAIT", target=entry, value=-1)
    with pytest.raises(FatalError, match="what its recovery holds is not one"):
        entry.twrp_entry(force=False)


def test_a_twrp_entry_unlocks_nothing_it_has_no_fastbrick_for(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(monkeypatch=monkeypatch, states=[State.STOCK_FASTBOOT])
    monkeypatch.setattr(name="device", target=SESSION, value=CROWN)
    monkeypatch.setattr(name="target", target=ARGUMENTS, value="")
    with pytest.raises(FatalError, match="no fastbrick for the Echo Show 8"):
        entry.twrp_entry(force=True)
    assert done == []


def test_a_twrp_entry_where_neither_restart_command_is_taken(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads(monkeypatch=monkeypatch, states=[State.AMONET_FASTBOOT])
    monkeypatch.setattr(
        name="restart_refusals", target=entry, value=lambda: [("reboot", "refused")]
    )
    with pytest.raises(FatalError, match="took neither command that starts"):
        entry.twrp_entry(force=False)


def test_a_twrp_entry_will_not_reach_amazon_s_recovery(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads(monkeypatch=monkeypatch, states=[State.BOOTED])
    with pytest.raises(FatalError, match="reads as booted, which nothing here can"):
        entry.twrp_entry(force=False)


def test_a_twrp_entry_with_force_writes_the_recovery(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch, states=[State.AMONET_FASTBOOT, State.AMONET_TWRP]
    )
    entry.twrp_entry(force=True)
    assert done[1] == "stage_amonet_recovery"
    assert "writes one to its recovery partition" in done[0]


def test_a_wheel_goes_on_the_import_path_once(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    wheel = tmp_path / "pyserial.whl"
    bootrom(monkeypatch=monkeypatch, states=[])
    monkeypatch.setattr(name="pyserial_wheel", target=entry, value=lambda: wheel)
    monkeypatch.setattr(name="path", target=entry.sys, value=["."])
    entry.bootrom_entry(force=True, short=True)
    assert entry.sys.path[0] == str(wheel)


def test_an_entry_gives_up_on_a_state_that_will_not_move(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = iter([0.0, 0.0, entry.STUCK + 1])
    reads(monkeypatch=monkeypatch, states=[State.AMONET_BOOTED] * 3)
    monkeypatch.setattr(name="monotonic", target=entry.time, value=lambda: next(clock))
    with pytest.raises(FatalError, match="has read as amonet-booted for 10 minutes"):
        entry.fastboot_entry()


def test_an_entry_names_the_echo_that_answers_it(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    reads(monkeypatch=monkeypatch, states=[State.AMONET_TWRP])
    monkeypatch.setattr(name="device", target=SESSION, value=None)
    monkeypatch.setattr(
        name="identify",
        target=entry,
        value=lambda: types.SimpleNamespace(device=BISCUIT),
    )
    entry.twrp_entry(force=False)
    assert "The Echo Dot (2nd Generation) is in amonet-twrp" in capsys.readouterr().out


def test_an_entry_refuses_a_state_it_cannot_reach_its_own_from(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    reads(monkeypatch=monkeypatch, states=[State.EMOS])
    with pytest.raises(FatalError, match="reads as emos, which nothing here can"):
        entry.fastboot_entry()


def test_an_entry_waits_out_the_reboot_it_asked_for(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = reads(
        monkeypatch=monkeypatch,
        states=[
            State.AMONET_BOOTED,
            State.NONE,
            State.NONE,
            State.STARTING,
            State.AMONET_FASTBOOT,
        ],
    )
    monkeypatch.setattr(name="monotonic", target=entry.time, value=lambda: 0.0)
    entry.fastboot_entry()
    assert done[0] == "reboot bootloader"
    assert "Waiting for the Echo Dot (2nd Generation) on USB" in done[1]
    assert len(done) == 2
