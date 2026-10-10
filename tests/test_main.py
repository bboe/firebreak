from __future__ import annotations

import functools
import hashlib
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import __main__ as main

if TYPE_CHECKING:
    import pathlib

LK = {"stock": b"S" * 241664, "v1.1.0": b"1" * 372368, "v2.0.0": b"2" * 359744}


def described(*, value: object) -> object:
    if isinstance(value, functools.partial):
        return value.func, {
            name: described(value=held) for name, held in value.keywords.items()
        }
    return value


def guard(
    *, monkeypatch: pytest.MonkeyPatch, slots: dict[str, bytes], tmp_path: pathlib.Path
) -> list[str]:
    read: list[str] = []
    numbers = {"lk_a": 3, "lk_b": 5}
    held = {f"{main.DISK}p{numbers[slot]}": data for slot, data in slots.items()}
    releases = {
        main.AMONET_BISCUIT_V1_1_0_ZIP.name: LK["v1.1.0"],
        main.AMONET_BISCUIT_V2_0_0_ZIP.name: LK["v2.0.0"],
    }

    def unpacked(*, download: object) -> pathlib.Path:
        root = tmp_path / download.name
        (root / "bin").mkdir(exist_ok=True, parents=True)
        (root / "bin" / "lk.bin").write_bytes(releases[download.name])
        return root

    def shell(*, command: str, timeout: float) -> str:
        del timeout
        node = command.split(sep=" ")[2]
        size = int(command.split(sep="bs=")[1].split(maxsplit=1, sep=" ")[0])
        read.append(node)
        data = held[node][:size]
        return f"{hashlib.md5(data, usedforsecurity=False).hexdigest()}  -"

    monkeypatch.setattr(name="adb_shell", target=main, value=shell)
    monkeypatch.setattr(
        name="partitions",
        target=main,
        value=lambda: {slot: (numbers[slot], 0, 0) for slot in slots},
    )
    monkeypatch.setattr(name="unpack", target=main, value=unpacked)
    main.amonet_chain()
    return read


def test_a_downgrade_that_meets_a_locked_fastboot_returns_false(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    answers = {"lk_build_desc": main.LK.FIREOS6.value, "unlock_status": "true"}
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="pyserial_wheel", target=main, value=lambda: None)
    monkeypatch.setattr(
        name="getvar", target=main, value=lambda **o: answers[o["name"]]
    )
    monkeypatch.setattr(name="bootrom_step", target=main, value=lambda **_: True)
    monkeypatch.setattr(
        name="amonet_v2_0_0_payload", target=main, value=lambda: tmp_path
    )
    monkeypatch.setattr(name="amonet_v1_1_0_recovery", target=main, value=lambda: False)
    assert main.downgrade() is False


def test_a_fastboot_that_never_says_whether_it_is_unlocked_stops_cleanly(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    monkeypatch.setattr(
        name="getvar", target=main, value=lambda **o: asked.append(o["name"]) or ""
    )
    monkeypatch.setattr(name="sleep", target=main.time, value=lambda _: None)
    monkeypatch.setattr(
        name="run", target=main, value=lambda **_: pytest.fail("flashed")
    )
    with pytest.raises(SystemExit, match="did not say whether it is unlocked"):
        main.amonet_v1_1_0_recovery()
    assert asked == ["unlock_status"] * main.PUSH_TRIES


def test_a_locked_fastboot_is_left_for_its_own_stage(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[list[object]] = []
    monkeypatch.setattr(name="getvar", target=main, value=lambda **_: "false")
    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **options: ran.append(options["arguments"]),
    )
    assert main.amonet_v1_1_0_recovery() is False
    assert ran == []
    assert "locked fastboot" in capsys.readouterr().out


def test_a_stage_that_returns_false_counts_none_of_its_passes(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[str] = []
    states = iter([
        main.State.AMONET_V2_0_0_FASTBOOT,
        main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    ])

    def state() -> main.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    table = {
        main.State.AMONET_V2_0_0_FASTBOOT: main.Stage(
            passes=frozenset({main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE}),
            run=lambda: ran.append("downgrade") is not None,
            steps=1,
            then=None,
        ),
        main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: main.Stage(
            run=lambda: ran.append("chain"), steps=1, then=None
        ),
    }
    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=main, value=state)
    monkeypatch.setattr(name="stages", target=main, value=lambda: table)
    monkeypatch.setattr(name="prefetch", target=main, value=lambda: None)
    monkeypatch.setattr(
        name="DOWNLOADER", target=main, value=types.SimpleNamespace(ident=1)
    )
    monkeypatch.setattr(name="sleep", target=main.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target",
        target=main.ARGUMENTS,
        value=main.TARGETS[main.AMONET_BISCUIT_V1_1_0_BBOE],
    )
    with pytest.raises(KeyboardInterrupt):
        main.root()
    assert ran == ["downgrade", "chain"]


def test_a_stage_that_returns_nothing_counts_its_passes(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[str] = []
    states = iter([
        main.State.AMONET_V2_0_0_FASTBOOT,
        main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    ])

    def state() -> main.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    table = {
        main.State.AMONET_V2_0_0_FASTBOOT: main.Stage(
            passes=frozenset({main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE}),
            run=lambda: ran.append("restore"),
            steps=1,
            then=None,
        ),
        main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: main.Stage(
            run=lambda: ran.append("again"), steps=1, then=None
        ),
    }
    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=main, value=state)
    monkeypatch.setattr(name="stages", target=main, value=lambda: table)
    monkeypatch.setattr(name="prefetch", target=main, value=lambda: None)
    monkeypatch.setattr(
        name="DOWNLOADER", target=main, value=types.SimpleNamespace(ident=1)
    )
    monkeypatch.setattr(name="sleep", target=main.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target",
        target=main.ARGUMENTS,
        value=main.TARGETS[main.AMONET_BISCUIT_V1_1_0_BBOE],
    )
    with pytest.raises(KeyboardInterrupt):
        main.root()
    assert ran == ["restore"]


def test_a_stale_marker_says_nothing_before_the_dot_is_seen(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    main.ERASED.parent.mkdir(exist_ok=True, parents=True)
    main.ERASED.touch()
    monkeypatch.setattr(
        name="run", target=main, value=lambda **_: types.SimpleNamespace(stdout="")
    )
    with pytest.raises(SystemExit, match="no -S option") as stopped:
        main.root()
    assert "boot0 may hold no preloader" not in " ".join(str(stopped.value).split())
    assert main.SESSION.boot0_marker is None


def test_an_unlocked_fastboot_takes_v1_1_0_to_its_recovery(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    ran: list[list[object]] = []
    monkeypatch.setattr(name="getvar", target=main, value=lambda **_: "true")
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    monkeypatch.setattr(name="fetch", target=main, value=lambda **_: tmp_path / "twrp")
    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **options: ran.append(options["arguments"]),
    )
    assert main.amonet_v1_1_0_recovery() is True
    assert [words[1:4] for words in ran] == [
        ["-S", "256M", "flash"],
        ["-S", "256M", "flash"],
        ["oem", "reboot-recovery"],
    ]


@pytest.mark.parametrize(
    argnames=("target", "states", "keywords"),
    argvalues=[
        (
            main.AMONET_BISCUIT_V2_0_0,
            (
                main.State.AMONET_V1_1_0_TWRP,
                main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
                main.State.AMONET_V1_1_0_BBOE_TWRP,
            ),
            {
                "after": (
                    main.reboot,
                    {"label": "waiting for v2.0.0 recovery to start"},
                ),
                "guard": main.amonet_chain,
                "unlock": main.amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0,
                "zero": ("misc",),
            },
        ),
        *(
            (
                unlock.name,
                (
                    main.State.AMONET_V2_0_0_TWRP,
                    main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
                ),
                {
                    "after": (
                        main.reboot,
                        {
                            "estimate": "4 min",
                            "into": "",
                            "label": "waiting for rooted Fire OS 5 to boot",
                        },
                    ),
                    "before_preloader": (
                        main.install_fireos,
                        {"reboot": False, "slot": "_a"},
                    ),
                    "guard": main.amonet_chain,
                    "unlock": unlock,
                },
            )
            for unlock in (
                main.amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0,
                main.amonet_biscuit_v1_1_0_bboe.AMONET_BISCUIT_V1_1_0_BBOE,
            )
        ),
    ],
    ids=["v2.0.0", "v1.1.0", "v1.1.0-bboe"],
)
def test_each_twrp_stage_carries_out_its_unlock(
    *,
    keywords: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    states: tuple[main.State, ...],
    target: str,
) -> None:
    monkeypatch.setattr(
        name="target", target=main.ARGUMENTS, value=main.TARGETS[target]
    )
    table = main.stages()
    for state in states:
        assert described(value=table[state].run) == (
            main.recovery.carry_out,
            keywords,
        )


@pytest.mark.parametrize(
    argnames=("target", "stages"),
    argvalues=[
        (
            main.AMONET_BISCUIT_V2_0_0,
            {
                main.State.AMONET_V1_1_0_TWRP: (12, main.State.AMONET_V2_0_0_TWRP),
                main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: (
                    12,
                    main.State.AMONET_V2_0_0_TWRP,
                ),
                main.State.AMONET_V1_1_0_BBOE_TWRP: (
                    12,
                    main.State.AMONET_V2_0_0_TWRP,
                ),
            },
        ),
        *(
            (
                target,
                {
                    main.State.AMONET_V2_0_0_TWRP: (
                        3,
                        main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
                    ),
                    main.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: (17, goal),
                },
            )
            for target, goal in (
                (main.AMONET_BISCUIT_V1_1_0, main.State.ROOTED_AMONET_V1_1_0),
                (
                    main.AMONET_BISCUIT_V1_1_0_BBOE,
                    main.State.ROOTED_AMONET_V1_1_0_BBOE,
                ),
            )
        ),
    ],
    ids=["v2.0.0", "v1.1.0", "v1.1.0-bboe"],
)
def test_each_twrp_stage_counts_its_steps_and_goes_on(
    *,
    monkeypatch: pytest.MonkeyPatch,
    stages: dict[object, tuple[int, object]],
    target: str,
) -> None:
    monkeypatch.setattr(
        name="target", target=main.ARGUMENTS, value=main.TARGETS[target]
    )
    table = main.stages()
    assert {state: (table[state].steps, table[state].then) for state in stages} == (
        stages
    )


def test_erasing_boot0_that_fails_leaves_no_marker(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    main.ERASED.parent.mkdir(exist_ok=True, parents=True)
    main.ERASED.touch()
    answers = iter([1, 0, 1])
    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **_: types.SimpleNamespace(returncode=next(answers), stdout="no"),
    )
    assert main.erase_by_fastboot().startswith("fastboot erase boot0 failed")
    assert not main.ERASED.exists()
    main.ERASED.touch()
    assert main.erase_by_fastboot().startswith("fastboot reboot failed")
    assert main.ERASED.exists()


def test_only_a_fire_os_5_target_leaves_v2_0_0s_fastboot_by_a_stage(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    for target in main.TARGETS.values():
        monkeypatch.setattr(name="target", target=main.ARGUMENTS, value=target)
        assert (main.State.AMONET_V2_0_0_FASTBOOT in main.stages()) == (
            not isinstance(target.installs, main.FireOs6)
        )


def test_probed_prints_an_unreadable_state_plain_and_masked(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    message = (
        "\x1b[31mERROR: sgdisk did not print the Dot's table:\n"
        "Disk identifier (GUID): 0FC63DAF-8483-4772-8E79-3D69D8477DE4\x1b[0m"
    )

    def state() -> main.State:
        raise SystemExit(message)

    monkeypatch.setattr(name="state", target=main, value=state)
    assert main.probed() == (
        "<unreadable: ERROR: sgdisk did not print the Dot's table:>"
    )
    monkeypatch.setattr(name="state", target=main, value=lambda: main.State.NONE)
    assert main.probed() == main.State.NONE.value


def test_target_names_are_the_unlocks_names() -> None:
    assert main.AMONET_BISCUIT_V1_1_0 == "amonet-biscuit-v1.1.0"
    assert main.AMONET_BISCUIT_V1_1_0_BBOE == "amonet-biscuit-v1.1.0-bboe"
    assert main.AMONET_BISCUIT_V2_0_0 == "amonet-biscuit-v2.0.0"


def test_the_guard_needs_both_slots(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    with pytest.raises(SystemExit, match="has no lk_b"):
        guard(monkeypatch=monkeypatch, slots={"lk_a": LK["v2.0.0"]}, tmp_path=tmp_path)


@pytest.mark.parametrize(
    argnames=("slots", "nodes"),
    argvalues=[
        ({"lk_a": LK["v2.0.0"], "lk_b": LK["stock"]}, ["p3"]),
        ({"lk_a": LK["v1.1.0"], "lk_b": LK["stock"]}, ["p3", "p3"]),
        (
            {"lk_a": LK["v1.1.0"][:4096] + LK["v2.0.0"][4096:], "lk_b": LK["v2.0.0"]},
            ["p3", "p3", "p5"],
        ),
        (
            {"lk_a": LK["v2.0.0"][:4096] + LK["stock"][4096:], "lk_b": LK["v1.1.0"]},
            ["p3", "p3", "p5", "p5"],
        ),
    ],
    ids=["v2.0.0", "v1.1.0", "lk_a-torn", "lk_a-torn-over-stock"],
)
def test_the_guard_passes_an_amonet_lk_in_either_slot(
    *,
    monkeypatch: pytest.MonkeyPatch,
    nodes: list[str],
    slots: dict[str, bytes],
    tmp_path: pathlib.Path,
) -> None:
    read = guard(monkeypatch=monkeypatch, slots=slots, tmp_path=tmp_path)
    assert [node[len(main.DISK) :] for node in read] == nodes


def test_the_guard_refuses_a_stock_lk_in_both_slots(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    with pytest.raises(SystemExit, match="neither lk_a nor lk_b"):
        guard(
            monkeypatch=monkeypatch,
            slots={"lk_a": LK["stock"], "lk_b": LK["stock"]},
            tmp_path=tmp_path,
        )


def test_the_session_has_no_marker_while_the_first_probe_runs(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    main.ERASED.parent.mkdir(exist_ok=True, parents=True)
    main.ERASED.touch()

    def state() -> main.State:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=main, value=state)
    monkeypatch.setattr(name="stages", target=main, value=dict)
    with pytest.raises(KeyboardInterrupt):
        main.root()
    assert main.SESSION.boot0_marker is None


def test_the_session_takes_the_marker_after_the_first_probe(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    main.ERASED.parent.mkdir(exist_ok=True, parents=True)
    main.ERASED.touch()
    states = iter([main.State.BOOTED])

    def state() -> main.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    monkeypatch.setattr(
        name="run",
        target=main,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=main, value=state)
    monkeypatch.setattr(name="stages", target=main, value=dict)
    monkeypatch.setattr(name="sleep", target=main.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target",
        target=main.ARGUMENTS,
        value=main.TARGETS[main.AMONET_BISCUIT_V1_1_0_BBOE],
    )
    with pytest.raises(KeyboardInterrupt):
        main.root()
    assert main.SESSION.boot0_marker == main.ERASED
    assert not main.ERASED.exists()
