from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import subprocess
from typing import TYPE_CHECKING

import pytest
from test_gpt import OTHERS
from test_gpt import raw as gpt_raw

from firebreak import plan, recovery
from firebreak.android.gpt import Partition, partition_map
from firebreak.plan import Action
from firebreak.plugin import BOOT0
from firebreak.unlocks import amonet_biscuit_v1_1_0, amonet_biscuit_v2_0_0

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
DD = re.compile(
    r"\$d if=(?P<source>\S+)(?: of=(?P<target>\S+))? bs=512"
    r" (?:skip|seek)=(?P<first>\d+)(?: count=(?P<count>\d+))?"
)
MD5SUM = (
    'exec python3 -c "import hashlib, sys; print(hashlib.md5('
    "sys.stdin.buffer.read()).hexdigest() + '  -')\""
)
MISC = Partition(first=2, number=8, sectors=4)
MISC_NODE = recovery.DISK + "p8"
TABLE = gpt_raw(names=[*OTHERS, "misc", "userdata"])

LIVE = partition_map(entries=TABLE[1024:])
LK_WRITE = Action(
    data=b"l",
    kind="Write",
    label="lk",
    length=1,
    offset=LIVE["part3"].first * 512,
    partition=LIVE["part3"],
    target="part3",
)
TABLE_WRITES = (
    Action(data=b"p", kind="Repartition", label="table", length=1, offset=0),
    Action(data=b"b", kind="Repartition", label="table", length=1, offset=9999 * 512),
    Action(
        data=b"w",
        kind="Repartition",
        label="wipe userdata",
        length=1,
        offset=LIVE["userdata"].first * 512,
        partition=LIVE["userdata"],
        target="userdata",
    ),
)
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


class FakeDot:
    def __init__(self) -> None:
        self.asked: list[str] = []
        self.blocks = {recovery.DISK: True, recovery.BOOT0_NODE: True, MISC_NODE: True}
        self.media = {
            recovery.BOOT0_NODE: bytearray(b"P" * 4096),
            recovery.DISK: bytearray(b"\x11" * 8192),
            MISC_NODE: bytearray(b"\x22" * 2048),
        }
        self.pushed: dict[str, bytes] = {}
        self.reconnects = 0
        self.short = 0
        self.lost = 0
        self.unwritten = 0

    def adb_shell(self, *, command: str, timeout: float = 300) -> str:
        del timeout
        self.asked.append(command)
        node = re.search(r"\[ -b (\S+) \]", command).group(1)
        if not self.blocks[node]:
            return ""
        if "blockdev --getsize64" in command:
            return f"block {len(self.media[node])}"
        found = DD.search(command)
        first = int(found.group("first"))
        if found.group("target"):
            if self.unwritten:
                self.unwritten -= 1
                return ""
            data = self.pushed.pop(found.group("source"))
            if self.lost:
                self.lost -= 1
            else:
                self.media[node][first * 512 : first * 512 + len(data)] = data
            return "written"
        count = int(found.group("count"))
        data = bytes(self.media[node][first * 512 : (first + count) * 512])
        if self.short:
            self.short -= 1
            return f"{hashlib.md5(data[:-512], usedforsecurity=False).hexdigest()}  -"
        return f"{hashlib.md5(data, usedforsecurity=False).hexdigest()}  -\nwhole"

    def command(
        self, *, arguments: list[str], **_: object
    ) -> subprocess.CompletedProcess:
        found = DD.search(arguments[-1])
        first, count = int(found.group("first")), int(found.group("count"))
        node = re.search(r"\[ -b (\S+) \]", arguments[-1]).group(1)
        data = bytes(self.media[node][first * 512 : (first + count) * 512])
        return subprocess.CompletedProcess(args=arguments, returncode=0, stdout=data)

    def push_checked(self, *, local: pathlib.Path, remote: object) -> None:
        self.pushed[str(remote)] = local.read_bytes()

    def reconnect(self, *, remote: object) -> None:
        del remote
        self.reconnects += 1


@pytest.fixture
def dot(*, monkeypatch: pytest.MonkeyPatch) -> FakeDot:
    fake = FakeDot()
    for name in ("adb_shell", "command", "push_checked", "reconnect"):
        monkeypatch.setattr(name=name, target=recovery, value=getattr(fake, name))
    recovery.CACHE.mkdir(exist_ok=True, parents=True)
    return fake


def carry(
    *,
    actions: tuple[Action, ...],
    boot0: str = "4096 0",
    calls: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
    wrong: str = "",
) -> list[Action]:
    checked: list[Action] = []
    recovery.ERASED.parent.mkdir(exist_ok=True, parents=True)

    def record(name: str) -> object:
        def called(**options: object) -> None:
            done = options.pop("actions", ())
            if name == "check":
                checked.extend(done)
            labels = tuple(action.label for action in done)
            calls.append((name, labels, recovery.ERASED.exists(), options))

        return called

    def shell(**_: object) -> str:
        calls.append(("boot0", recovery.ERASED.exists()))
        return boot0

    def nodes(*, want: dict[str, int]) -> str:
        calls.append(("nodes", tuple(sorted(want.items()))))
        return wrong

    for name in ("check", "execute", "reboot", "run"):
        monkeypatch.setattr(name=name, target=recovery, value=record(name))
    monkeypatch.setattr(name="adb_shell", target=recovery, value=shell)
    monkeypatch.setattr(name="reaches", target=recovery, value=lambda **_: True)
    monkeypatch.setattr(name="check_nodes", target=recovery, value=nodes)
    monkeypatch.setattr(name="read_sectors", target=recovery, value=lambda **_: TABLE)
    monkeypatch.setattr(name="resolve", target=recovery, value=lambda **_: actions)
    monkeypatch.setattr(name="unpack", target=recovery, value=lambda **_: None)
    return checked


def carry_v1(*, calls: list[tuple]) -> bool:
    return recovery.carry_out(
        after=lambda: calls.append(("after", recovery.ERASED.exists())),
        before_preloader=lambda: calls.append(("install", recovery.ERASED.exists())),
        guard=lambda: calls.append(("guard",)),
        unlock=amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0,
    )


def carry_v2(*, calls: list[tuple]) -> bool:
    return recovery.carry_out(
        after=lambda: calls.append(("after", recovery.ERASED.exists())),
        guard=lambda: calls.append(("guard",)),
        unlock=amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0,
        zero=("misc",),
    )


def shell(*, command: str, tmp_path: pathlib.Path) -> str:
    tools = tmp_path / "tools"
    tools.mkdir(exist_ok=True)
    for name, body in (
        (
            "md5sum",
            MD5SUM,
        ),
        ("toybox", "exit 1"),
    ):
        (tools / name).write_text(f"#!/bin/sh\n{body}\n")
        (tools / name).chmod(0o755)
    return subprocess.run(
        args=[
            "sh",
            "-c",
            command.replace("[ -b ", "[ -f ").replace(
                recovery.DD_LOG, str(tmp_path / "dd.log")
            ),
        ],
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}"},
        text=True,
    ).stdout


def test_a_byte_patch_lands_inside_its_sector(*, dot: FakeDot) -> None:
    action = Action(
        data=b"ABB",
        kind="ResetBcb",
        label="bcb",
        length=3,
        offset=(2 + 1) * 512 + 5,
        partition=MISC,
        target="misc",
    )
    recovery.execute(actions=(action,))
    assert dot.media[MISC_NODE][512:520] == b"\x22" * 5 + b"ABB"
    assert dot.media[MISC_NODE][520:1024] == b"\x22" * 504
    assert dot.media[recovery.DISK] == b"\x11" * 8192
    assert len(writes(dot)) == 1


def test_a_hash_needs_every_record(*, tmp_path: pathlib.Path) -> None:
    disk = tmp_path / "disk"
    disk.write_bytes(b"A" * 512 + b"B" * 1024 + b"C" * 512)
    said = shell(
        command=recovery.HASH.format(count=2, first=1, node=disk), tmp_path=tmp_path
    ).split()
    assert said == [
        hashlib.md5(b"B" * 1024, usedforsecurity=False).hexdigest(),
        "-",
        "whole",
    ]
    said = shell(
        command=recovery.HASH.format(count=2, first=3, node=disk), tmp_path=tmp_path
    ).split()
    assert said[-1] != "whole"


def test_a_kernel_that_holds_another_table_restarts_recovery_and_writes_nothing(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    carry(
        actions=(LK_WRITE, *V2_ACTIONS),
        calls=calls,
        monkeypatch=monkeypatch,
        wrong="/dev/block/mmcblk0p4 reads no, not 51200 bytes",
    )
    with pytest.raises(SystemExit, match="does not hold the table that is on the disk"):
        carry_v2(calls=calls)
    assert [call[0] for call in calls] == ["guard", "nodes", "run"]
    assert calls[-1][3]["arguments"] == ["adb", "reboot", "recovery"]
    assert not recovery.ERASED.exists()


def test_a_node_that_is_not_a_block_device_stops_it(*, dot: FakeDot) -> None:
    dot.blocks[recovery.BOOT0_NODE] = False
    write = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target=BOOT0
    )
    with pytest.raises(SystemExit, match=r"describes: nothing\. Nothing was written"):
        recovery.execute(actions=(write,))
    assert writes(dot) == []


def test_a_partition_whose_node_has_another_size_stops_it(*, dot: FakeDot) -> None:
    dot.media[MISC_NODE] = bytearray(1024)
    action = Action(
        data=b"x" * 512,
        kind="Write",
        label="w",
        length=512,
        offset=1024,
        partition=MISC,
        target="misc",
    )
    with pytest.raises(SystemExit, match=r"block 1024\. Nothing was written"):
        recovery.execute(actions=(action,))
    assert writes(dot) == []


def test_a_patch_at_the_start_of_a_partition_keeps_the_rest_of_its_sector(
    *, dot: FakeDot
) -> None:
    action = Action(
        data=b"FASTBOOT_PLEASE\0",
        kind="ForceFastboot",
        label="fastboot",
        length=16,
        offset=2 * 512,
        partition=MISC,
        target="misc",
    )
    recovery.execute(actions=(action,))
    assert dot.media[MISC_NODE][:512] == b"FASTBOOT_PLEASE\0" + b"\x22" * 496
    assert "bs=512 seek=0" in writes(dot)[0]


def test_a_patch_read_that_comes_back_short_stops_it(
    *, dot: FakeDot, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="command",
        target=recovery,
        value=lambda **_: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b""
        ),
    )
    action = Action(
        data=b"ABB", kind="ResetBcb", label="bcb", length=3, offset=5, target="misc"
    )
    with pytest.raises(SystemExit, match="read 0 bytes"):
        recovery.execute(actions=(action,))
    assert writes(dot) == []


def test_a_patch_read_that_fails_stops_it(
    *, dot: FakeDot, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**_: object) -> None:
        raise subprocess.TimeoutExpired(cmd="adb", timeout=60)

    monkeypatch.setattr(name="command", target=recovery, value=broken)
    action = Action(
        data=b"ABB", kind="ResetBcb", label="bcb", length=3, offset=5, target="misc"
    )
    with pytest.raises(SystemExit, match="could not be read"):
        recovery.execute(actions=(action,))
    assert writes(dot) == []


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

    monkeypatch.setattr(name="read_sectors", target=recovery, value=lambda **_: b"")
    monkeypatch.setattr(name="resolve", target=recovery, value=unresolvable)
    monkeypatch.setattr(name="unpack", target=recovery, value=lambda **_: tmp_path)
    with pytest.raises(SystemExit, match="does not fit this Dot: biscuit has no"):
        carry_v1(calls=[])
    assert not recovery.ERASED.exists()


def test_a_read_that_never_completes_stops_it(*, dot: FakeDot) -> None:
    dot.short = recovery.PUSH_TRIES
    action = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    with pytest.raises(SystemExit, match="did not answer"):
        recovery.execute(actions=(action,))
    assert writes(dot) == []


@pytest.mark.parametrize(
    argnames=("said", "reached"),
    argvalues=[
        ("reaches", True),
        ("toybox: noise\nreaches", True),
        ("reaches\ndd: Invalid argument", False),
        ("dd: Invalid argument", False),
        ("", False),
    ],
)
def test_a_sector_is_reached_only_when_dd_reads_it_whole(
    *, monkeypatch: pytest.MonkeyPatch, reached: bool, said: str
) -> None:
    asked: list[tuple[str, float]] = []
    monkeypatch.setattr(
        name="adb_shell",
        target=recovery,
        value=lambda *, command, timeout: asked.append((command, timeout)) or said,
    )
    assert recovery.reaches(first=7651295) is reached
    ((command, timeout),) = asked
    assert timeout == 60
    assert command.startswith(recovery.DD)
    assert (
        f"[ -b {recovery.DISK} ] && $d if={recovery.DISK} bs=512 skip=7651295"
        " count=1 2>"
    ) in command
    assert command.endswith(
        f"grep -q '^1+0 records in' {recovery.DD_LOG} && echo reaches"
    )


def test_a_short_read_never_matches(*, dot: FakeDot) -> None:
    dot.short = 1
    action = Action(
        data=b"\x11" * 1024,
        kind="Write",
        label="same",
        length=1024,
        offset=0,
        target="a",
    )
    recovery.execute(actions=(action,))
    assert dot.reconnects == 1
    assert writes(dot) == []


def test_a_table_that_goes_in_alone_is_refused_when_dd_cannot_reach_it(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    asked: list[int] = []
    moved = dataclasses.replace(
        LK_WRITE,
        partition=dataclasses.replace(LIVE["part3"], first=LIVE["part3"].first + 1),
    )
    carry(
        actions=(*TABLE_WRITES, moved, *ACTIONS),
        calls=calls,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(
        name="reaches",
        target=recovery,
        value=lambda *, first: asked.append(first) and False,
    )
    with pytest.raises(SystemExit, match="cannot read sector 9999") as stopped:
        carry_v1(calls=calls)
    assert "Nothing was written." in " ".join(str(stopped.value).split())
    assert asked == [9999]
    assert [call[0] for call in calls] == ["guard"]


def test_a_table_whose_backup_copy_dd_cannot_reach_writes_nothing(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    asked: list[int] = []
    carry(
        actions=(*TABLE_WRITES[:2], LK_WRITE, *V2_ACTIONS),
        calls=calls,
        monkeypatch=monkeypatch,
    )
    monkeypatch.setattr(
        name="reaches",
        target=recovery,
        value=lambda *, first: asked.append(first) and False,
    )
    with pytest.raises(SystemExit, match="cannot read sector 9999") as stopped:
        carry_v2(calls=calls)
    assert "Nothing was written." in " ".join(str(stopped.value).split())
    assert asked == [9999]
    assert [call[0] for call in calls] == ["guard"]
    assert not recovery.ERASED.exists()


@pytest.mark.parametrize(argnames="exit_status", argvalues=[0, 1])
def test_a_write_needs_every_record_and_a_clean_exit(
    *, exit_status: int, tmp_path: pathlib.Path
) -> None:
    disk, source = tmp_path / "disk", tmp_path / "source"
    disk.write_bytes(b"A" * 2048)
    source.write_bytes(b"N" * 1024)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "dd").write_text(f'#!/bin/sh\n/bin/dd "$@"\nexit {exit_status}\n')
    (tools / "dd").chmod(0o755)
    said = shell(
        command=recovery.WRITE.format(
            count=2, first=1, node=disk, relock="", source=source, unlock=""
        ),
        tmp_path=tmp_path,
    ).split()
    assert disk.read_bytes()[512:1536] == b"N" * 1024
    assert not source.exists()
    assert (said[-1:] == ["written"]) is (exit_status == 0)


def test_a_write_that_does_not_finish_stops_it(*, dot: FakeDot) -> None:
    dot.unwritten = 1
    action = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    with pytest.raises(SystemExit, match="did not read back"):
        recovery.execute(actions=(action,))


def test_a_write_that_does_not_land_stops_it(*, dot: FakeDot) -> None:
    dot.lost = 1
    action = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    with pytest.raises(SystemExit, match="did not read back"):
        recovery.execute(actions=(action,))
    assert dot.media[recovery.DISK][:512] == b"\x11" * 512


def test_amonet_v1_1_0_clears_boot0_then_writes_the_preloader_last(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    carry(
        actions=(*ACTIONS, LK_WRITE),
        calls=calls,
        monkeypatch=monkeypatch,
    )
    assert carry_v1(calls=calls) is True
    assert calls == [
        ("guard",),
        ("nodes", ((f"{recovery.DISK}p4", LIVE["part3"].size),)),
        ("check", ("lk", "preloader", "twrp", "lk"), False, {}),
        ("boot0", True),
        ("execute", ("lk", "twrp", "lk"), True, {}),
        ("install", True),
        ("execute", ("preloader",), True, {}),
        ("after", False),
    ]


@pytest.mark.parametrize(argnames="field", argvalues=["first", "number", "sectors"])
def test_amonet_v1_1_0_writes_a_table_that_moves_its_targets_alone(
    *, field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    partition = LIVE["part3"]
    moved = dataclasses.replace(
        LK_WRITE,
        partition=dataclasses.replace(
            partition, **{field: getattr(partition, field) + 1}
        ),
    )
    carry(
        actions=(*TABLE_WRITES, moved, *ACTIONS),
        calls=calls,
        monkeypatch=monkeypatch,
    )
    assert carry_v1(calls=calls) is False
    assert calls == [
        ("guard",),
        ("execute", ("table", "table"), False, {}),
        (
            "reboot",
            (),
            False,
            {"label": "waiting for recovery to read the new table"},
        ),
    ]


def test_amonet_v2_0_0_clears_boot0_then_writes_the_table_backup_first(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    checked = carry(
        actions=(*TABLE_WRITES[:2], LK_WRITE, *V2_ACTIONS),
        calls=calls,
        monkeypatch=monkeypatch,
    )
    assert carry_v2(calls=calls) is True
    assert calls == [
        ("guard",),
        (
            "nodes",
            (
                (f"{recovery.DISK}p14", LIVE["misc"].size),
                (f"{recovery.DISK}p4", LIVE["part3"].size),
            ),
        ),
        (
            "check",
            ("table", "table", "lk", "lk", "preloader", "twrp", "zero misc"),
            False,
            {},
        ),
        ("boot0", True),
        (
            "execute",
            ("table", "table", "lk", "lk", "twrp", "zero misc"),
            True,
            {},
        ),
        ("execute", ("preloader",), True, {}),
        ("after", False),
    ]
    assert [action.offset for action in checked[:2]] == [9999 * 512, 0]
    wipe, misc = checked[-1], LIVE["misc"]
    assert (wipe.offset, wipe.length, wipe.partition) == (
        misc.first * 512,
        misc.size,
        misc,
    )
    assert wipe.data == bytes(misc.size)


@pytest.mark.parametrize(
    argnames=("boot0", "marked"),
    argvalues=[("4096 12", False), ("0 0", True), ("12 0", True), ("", True)],
    ids=["still-set", "nothing-read", "short-read", "no-answer"],
)
def test_amonet_v2_0_0_stops_before_the_table_if_boot0_does_not_clear(
    *, boot0: str, marked: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    carry(
        actions=(*TABLE_WRITES[:2], *V2_ACTIONS),
        boot0=boot0,
        calls=calls,
        monkeypatch=monkeypatch,
    )
    with pytest.raises(SystemExit, match="did not read back as cleared"):
        carry_v2(calls=calls)
    assert "execute" not in [call[0] for call in calls]
    assert recovery.ERASED.exists() is marked


def test_amonet_v2_0_0_that_does_not_fit_writes_nothing(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    def unresolvable(**_: object) -> None:
        raise ValueError(("the partition table is in no layout",))

    monkeypatch.setattr(name="read_sectors", target=recovery, value=lambda **_: b"")
    monkeypatch.setattr(name="resolve", target=recovery, value=unresolvable)
    monkeypatch.setattr(name="unpack", target=recovery, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="adb_shell",
        target=recovery,
        value=lambda **_: pytest.fail("boot0 changed"),
    )
    with pytest.raises(SystemExit, match="does not fit this Dot") as stopped:
        carry_v2(calls=[])
    said = " ".join(str(stopped.value).split())
    assert "Nothing was written." in said
    assert "boot0 may hold no preloader" not in said


def test_an_action_with_nothing_to_write_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing to write"):
        plan.contents(action=Action(kind="Reboot", label="reboot"))


def test_an_image_is_padded_to_whole_sectors(
    *, dot: FakeDot, tmp_path: pathlib.Path
) -> None:
    image = tmp_path / "lk.bin"
    image.write_bytes(b"L" * 600)
    action = Action(
        image=image,
        kind="Write",
        label="lk",
        length=1024,
        offset=(2 + 2) * 512,
        partition=MISC,
        target="misc",
    )
    recovery.execute(actions=(action,))
    assert dot.media[MISC_NODE][1024:2048] == b"L" * 600 + b"\0" * 424
    assert "of=/dev/block/mmcblk0p8 bs=512 seek=2" in writes(dot)[0]


def test_boot0_is_unlocked_and_locked_again(*, dot: FakeDot) -> None:
    action = Action(
        data=b"\0" * 512, kind="Write", label="w", length=512, offset=0, target=BOOT0
    )
    recovery.execute(actions=(action,))
    assert dot.media[recovery.BOOT0_NODE][:512] == b"\0" * 512
    (written,) = writes(dot)
    assert "echo 0 > /sys/block/mmcblk0boot0/force_ro" in written
    assert written.index("force_ro; $d") < written.index("echo 1 > /sys/block")


def test_steps_recovery_cannot_run_stop_the_plan_first(*, dot: FakeDot) -> None:
    write = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    with pytest.raises(SystemExit, match="ZeroRpmb"):
        recovery.execute(actions=(write, Action(kind="ZeroRpmb", label="rpmb")))
    assert dot.asked == []


def test_toybox_writes_without_truncating(*, dot: FakeDot) -> None:
    action = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    recovery.execute(actions=(action,))
    (written,) = writes(dot)
    assert "d='toybox dd' && n=' conv=notrunc'" in written
    assert "seek=0$n " in written


def test_what_is_already_there_is_not_written(*, dot: FakeDot) -> None:
    action = Action(
        data=b"\x11" * 512,
        kind="Write",
        label="same",
        length=512,
        offset=0,
        target="tee1",
    )
    nothing = Action(kind="Repartition", label="room", length=0)
    recovery.execute(actions=(nothing, action))
    assert writes(dot) == []


def writes(dot: FakeDot) -> list[str]:
    return [asked for asked in dot.asked if " of=" in asked]
