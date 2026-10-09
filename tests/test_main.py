from __future__ import annotations

import hashlib
import types
from typing import TYPE_CHECKING

import pytest
from test_gpt import OTHERS
from test_gpt import raw as gpt_raw

from firebreak import __main__ as main
from firebreak.android.gpt import Partition
from firebreak.plan import Action

if TYPE_CHECKING:
    import pathlib

ACTIONS = (
    Action(data=b"h", kind="ClearBoot0Header", label="clear", length=1, offset=0),
    Action(kind="ZeroRpmb", label="rpmb"),
    Action(data=b"l", kind="Write", label="lk", length=1, offset=0),
    Action(kind="ForceFastboot", label="fastboot"),
    Action(
        data=b"p",
        kind="Write",
        label="preloader",
        length=1,
        offset=0,
        unrecoverable=True,
    ),
    Action(kind="Reboot", label="reboot"),
    Action(data=b"t", kind="FastbootFlash", label="twrp", length=1, offset=0),
)

LK = {"stock": b"S" * 241664, "v1.1.0": b"1" * 372368, "v2.0.0": b"2" * 359744}


MISC = Partition(first=118784, number=8, sectors=1025)
MOVED = (Action(data=b"t", kind="Repartition", label="table", length=1, offset=0),)


V2_ACTIONS = (
    Action(kind="ZeroRpmb", label="rpmb"),
    Action(data=b"l", kind="Write", label="lk", length=1, offset=0),
    Action(
        data=b"p",
        kind="Write",
        label="preloader",
        length=1,
        offset=0,
        unrecoverable=True,
    ),
    Action(kind="ForceFastboot", label="fastboot"),
    Action(kind="Reboot", label="reboot"),
    Action(data=b"t", kind="FastbootFlash", label="twrp", length=1, offset=0),
)


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


def install(
    *,
    boot0: str = "4096 0",
    calls: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
    plans: list[tuple[Action, ...]],
) -> list[Action]:
    checked: list[Action] = []
    main.ERASED.parent.mkdir(exist_ok=True, parents=True)

    def plan(*, written: str) -> tuple[dict[str, Partition], tuple[Action, ...]]:
        calls.append(("plan", written))
        return {"misc": MISC}, plans.pop(0)

    def record(name: str) -> object:
        def called(**options: object) -> None:
            actions = options.pop("actions", ())
            if name == "check":
                checked.extend(actions)
            labels = tuple(action.label for action in actions)
            calls.append((name, labels, main.ERASED.exists(), options))

        return called

    def shell(**_: object) -> str:
        calls.append(("boot0", main.ERASED.exists()))
        return boot0

    monkeypatch.setattr(name="amonet_v2_0_0_plan", target=main, value=plan)
    monkeypatch.setattr(
        name="restore_stock_table", target=main, value=record("restore")
    )
    monkeypatch.setattr(name="adb_shell", target=main, value=shell)
    monkeypatch.setattr(name="run", target=main, value=record("run"))
    for name in ("check", "execute"):
        monkeypatch.setattr(name=name, target=main.recovery, value=record(name))
    main.install_amonet_v2_0_0()
    return checked


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


@pytest.mark.parametrize(
    argnames="error",
    argvalues=[FileNotFoundError, KeyError, ValueError],
    ids=["missing-image", "missing-partition", "bad-table"],
)
def test_a_plan_that_does_not_resolve_stops_before_anything_is_written(
    *, error: type[Exception], monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    def unresolvable(**_: object) -> None:
        message = "biscuit has no lk_c partition"
        raise error(message)

    for name in ("amonet_chain", "chain_nodes"):
        monkeypatch.setattr(name=name, target=main, value=lambda: None)
    monkeypatch.setattr(name="read_sectors", target=main, value=lambda **_: b"")
    monkeypatch.setattr(name="resolve", target=main, value=unresolvable)
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="target", target=main.ARGUMENTS, value=main.AMONET_BISCUIT_V1_1_0
    )
    with pytest.raises(SystemExit, match="does not fit this Dot: biscuit has no"):
        main.amonet_v1_1_0_chain()
    assert not main.ERASED.exists()


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
        name="target", target=main.ARGUMENTS, value=main.AMONET_BISCUIT_V1_1_0_BBOE
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
        name="target", target=main.ARGUMENTS, value=main.AMONET_BISCUIT_V1_1_0_BBOE
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


def test_a_stock_table_is_left_alone(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        name="partitions", target=main, value=lambda: {"boot_a": (10, 1, 2)}
    )
    monkeypatch.setattr(
        name="adb_shell", target=main, value=lambda **_: pytest.fail("sgdisk ran")
    )
    main.restore_stock_table()


def test_amonet_v2_0_0_clears_boot0_then_restores_the_table_then_writes(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    checked = install(
        calls=calls, monkeypatch=monkeypatch, plans=[MOVED + V2_ACTIONS, V2_ACTIONS]
    )
    assert calls == [
        ("plan", "Nothing was written."),
        ("check", ("lk", "preloader", "twrp", "zero misc"), False, {}),
        ("boot0", True),
        ("restore", (), True, {}),
        ("plan", "boot0's header is cleared and the table is stock."),
        ("execute", ("lk", "twrp", "zero misc"), True, {}),
        ("execute", ("preloader",), True, {}),
        (
            "run",
            (),
            False,
            {
                "arguments": ["adb", "reboot", "recovery"],
                "check": True,
                "timeout": 60,
            },
        ),
    ]
    wipe = checked[-1]
    assert (wipe.offset, wipe.length, wipe.partition) == (
        MISC.first * 512,
        MISC.size,
        MISC,
    )
    assert wipe.data == bytes(MISC.size)


def test_amonet_v2_0_0_stops_before_the_table_if_boot0_does_not_clear(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    with pytest.raises(SystemExit, match="did not read back as cleared"):
        install(
            boot0="4096 12", calls=calls, monkeypatch=monkeypatch, plans=[V2_ACTIONS]
        )
    assert "restore" not in [call[0] for call in calls]
    assert not main.ERASED.exists()


def test_amonet_v2_0_0_stops_with_boot0_cleared_if_sgdisk_left_another_table(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    main.SESSION.boot0_marker = main.ERASED
    with pytest.raises(SystemExit, match="not the one checked") as stopped:
        install(
            calls=calls, monkeypatch=monkeypatch, plans=[V2_ACTIONS, MOVED + V2_ACTIONS]
        )
    assert "execute" not in [call[0] for call in calls]
    assert main.ERASED.exists()
    assert "shows no light and starts nothing" in " ".join(str(stopped.value).split())


def test_amonet_v2_0_0_that_does_not_fit_writes_nothing(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    def unresolvable(**_: object) -> None:
        raise ValueError(("the partition table is in no layout",))

    monkeypatch.setattr(name="read_sectors", target=main, value=lambda **_: b"")
    monkeypatch.setattr(name="resolve", target=main, value=unresolvable)
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="adb_shell", target=main, value=lambda **_: pytest.fail("boot0 changed")
    )
    with pytest.raises(SystemExit, match="does not fit this Dot") as stopped:
        main.install_amonet_v2_0_0()
    said = " ".join(str(stopped.value).split())
    assert "Nothing was written." in said
    assert "boot0 may hold no preloader" not in said


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


def test_the_chain_checks_then_marks_boot0_then_writes_the_preloader_last(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    calls: list[tuple] = []
    main.ERASED.parent.mkdir(parents=True)

    def record(name: str) -> object:
        def called(**options: object) -> None:
            labels = tuple(action.label for action in options.pop("actions", ()))
            calls.append((name, labels, main.ERASED.exists(), options))

        return called

    def resolved(**options: object) -> tuple[Action, ...]:
        calls.append(("resolve", options["unlock"].name))
        return ACTIONS

    for name in ("amonet_chain", "chain_nodes", "install_fireos"):
        monkeypatch.setattr(name=name, target=main, value=record(name))
    for name in ("check", "execute"):
        monkeypatch.setattr(name=name, target=main.recovery, value=record(name))
    monkeypatch.setattr(name="read_sectors", target=main, value=lambda **_: b"table")
    monkeypatch.setattr(name="resolve", target=main, value=resolved)
    monkeypatch.setattr(name="run", target=main, value=lambda **_: None)
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="target", target=main.ARGUMENTS, value=main.AMONET_BISCUIT_V1_1_0_BBOE
    )
    main.amonet_v1_1_0_chain()
    assert calls == [
        ("amonet_chain", (), False, {}),
        ("chain_nodes", (), False, {}),
        ("resolve", main.AMONET_BISCUIT_V1_1_0_BBOE),
        ("check", ("clear", "lk", "preloader", "twrp"), False, {}),
        ("execute", ("clear", "lk", "twrp"), True, {}),
        ("install_fireos", (), True, {"reboot": False, "slot": "_a"}),
        ("execute", ("preloader",), True, {}),
    ]
    assert not main.ERASED.exists()


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
        name="target", target=main.ARGUMENTS, value=main.AMONET_BISCUIT_V1_1_0_BBOE
    )
    with pytest.raises(KeyboardInterrupt):
        main.root()
    assert main.SESSION.boot0_marker == main.ERASED
    assert not main.ERASED.exists()


@pytest.mark.parametrize(
    argnames=("left", "fields_after", "error"),
    argvalues=[
        ({}, ("CODE", "UNIQUE"), ""),
        ({"boot_b": (17, 7199744, 7425023)}, ("CODE", "UNIQUE"), "left boot_b as"),
        ({"boot_a": (11, 196608, 229375)}, ("CODE", "UNIQUE"), "left boot_a as"),
        ({"userdata": (16, 5046272, 7199743)}, ("CODE", "UNIQUE"), "left userdata"),
        ({}, ("CODE", "OTHER"), "a different Partition unique GUID"),
        ({}, ("OTHER", "UNIQUE"), "a different Partition GUID code"),
    ],
    ids=["restored", "boot_b", "boot_a", "userdata", "guid", "code"],
)
def test_the_stock_table_is_restored_with_sgdisk(
    *,
    error: str,
    fields_after: tuple[str, str],
    left: dict[str, tuple[int, int, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moved = {
        "boot_a": (17, 7199744, 7425023),
        "boot_a_x": (10, 163840, 196607),
        "boot_b": (18, 7425024, 7650303),
        "boot_b_x": (11, 196608, 229375),
        "userdata": (16, 5046272, 7199743),
    }
    stock = {
        "boot_a": (10, 163840, 196607),
        "boot_b": (11, 196608, 229375),
        "userdata": (16, 5046272, 7651294),
        **left,
    }
    tables = [moved, stock]
    fields = {
        "Partition GUID code": ["CODE", fields_after[0]],
        "Partition unique GUID": ["UNIQUE", fields_after[1]],
    }
    commands: list[str] = []
    header = bytearray(1024)
    header[560:568] = (7651294).to_bytes(8, "little")

    def field(*, name: str, number: int) -> str:
        return f"{fields[name].pop(0)}{number}"

    def shell(*, command: str, timeout: float) -> None:
        del timeout
        commands.append(command)

    monkeypatch.setattr(name="partitions", target=main, value=lambda: tables.pop(0))
    monkeypatch.setattr(
        name="read_sectors", target=main, value=lambda **_: bytes(header)
    )
    monkeypatch.setattr(name="partition_field", target=main, value=field)
    monkeypatch.setattr(name="adb_shell", target=main, value=shell)
    if error:
        with pytest.raises(SystemExit, match=error):
            main.restore_stock_table()
    else:
        main.restore_stock_table()
    assert commands == [
        (
            "sgdisk --set-alignment=1 --delete=18 --delete=17 --delete=16"
            " --new=16:5046272:7651294 --typecode=16:CODE16"
            " --partition-guid=16:UNIQUE16 --change-name=16:userdata"
            " --change-name=10:boot_a --change-name=11:boot_b /dev/block/mmcblk0"
        )
    ]


def test_the_v2_0_0_plan_comes_with_the_table_it_was_resolved_against(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    table = gpt_raw(names=[*OTHERS, "misc", "userdata"])
    monkeypatch.setattr(name="read_sectors", target=main, value=lambda **_: table)
    monkeypatch.setattr(name="resolve", target=main, value=lambda **_: V2_ACTIONS)
    monkeypatch.setattr(name="unpack", target=main, value=lambda **_: tmp_path)
    partitions, resolved = main.amonet_v2_0_0_plan(written="Nothing was written.")
    assert resolved == V2_ACTIONS
    assert partitions["misc"] == Partition(first=1334, number=14, sectors=100)
