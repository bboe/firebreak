from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import pytest

from firebreak import __main__ as main
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
