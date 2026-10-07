from __future__ import annotations

import hashlib
import os
import re
import subprocess
from typing import TYPE_CHECKING

import pytest

from firebreak import recovery
from firebreak.android.gpt import Partition
from firebreak.plan import Action
from firebreak.plugin import BOOT0

if TYPE_CHECKING:
    import pathlib

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


def test_a_read_that_never_completes_stops_it(*, dot: FakeDot) -> None:
    dot.short = recovery.PUSH_TRIES
    action = Action(
        data=b"x" * 512, kind="Write", label="w", length=512, offset=0, target="a"
    )
    with pytest.raises(SystemExit, match="did not answer"):
        recovery.execute(actions=(action,))
    assert writes(dot) == []


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


def test_an_action_with_nothing_to_write_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing to write"):
        recovery.contents(action=Action(kind="Reboot", label="reboot"))


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
    nothing = Action(kind="ShuffleGpt", label="room", length=0)
    recovery.execute(actions=(nothing, action))
    assert writes(dot) == []


def writes(dot: FakeDot) -> list[str]:
    return [asked for asked in dot.asked if " of=" in asked]
