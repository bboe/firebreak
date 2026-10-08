from __future__ import annotations

import functools
import hashlib
import pathlib
import subprocess
import tempfile
from typing import TYPE_CHECKING

from firebreak.cache import CACHE
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    PUSH_TRIES,
    adb_shell,
    command,
    push_checked,
    reconnect,
)
from firebreak.plan import SECTOR_SIZE, whole_sectors
from firebreak.plugin import BOOT0
from firebreak.ui import PROGRESS, _die, again

if TYPE_CHECKING:
    from firebreak.plan import Action

BOOT0_NODE = "/dev/block/mmcblk0boot0"
DD = (
    "d=dd; n=; toybox dd --help >/dev/null 2>&1 && d='toybox dd' && n=' conv=notrunc'; "
)
DD_LOG = "/tmp/firebreak-dd.log"  # ruff: ignore[hardcoded-temp-file]
DISK = "/dev/block/mmcblk0"
FORCE_RO = "echo {lock} > /sys/block/mmcblk0boot0/force_ro; "
HASH = (
    DD + "[ -b {node} ] && $d if={node} bs=512 skip={first} count={count}"
    f" 2>{DD_LOG} | md5sum; grep -q '^{{count}}+0 records in' {DD_LOG}"
    " && echo whole"
)
MD5_DIGITS = 32
NODE = "[ -b {node} ] && echo block $(blockdev --getsize64 {node})"
READ = (
    DD + "[ -b {node} ] && $d if={node} bs=512 skip={first} count={count} 2>/dev/null"
)
WRITE = (
    DD + "[ -b {node} ] || exit 1; {unlock}$d if={source} of={node} bs=512"
    f" seek={{first}}$n 2>{DD_LOG}; s=$?; {{relock}}rm -f {{source}}; sync;"
    " echo 3 > /proc/sys/vm/drop_caches; [ $s = 0 ]"
    f" && grep -q '^{{count}}+0 records out' {DD_LOG} && echo written"
)


def check(*, actions: tuple[Action, ...]) -> tuple[Action, ...]:
    refused = sorted({
        action.kind
        for action in actions
        if action.length != 0
        and (action.offset is None or (action.data is None and action.image is None))
    })
    if refused:
        _die(
            message=f"recovery cannot carry out {', '.join(refused)}. Nothing was"
            " written. " + again()
        )
    writes = tuple(action for action in actions if action.length != 0)
    for node, partition in {
        place(action=action)[0]: action.partition for action in writes
    }.items():
        said = adb_shell(command=NODE.format(node=node)).split(sep="\n")[-1].split()
        if said[:1] != ["block"] or (
            partition is not None and said[1:] != [str(partition.sectors * SECTOR_SIZE)]
        ):
            _die(
                message=f"{node} is not the block device the partition table"
                f" describes: {' '.join(said) or 'nothing'}. Nothing was written. "
                + again()
            )
    return writes


def execute(*, actions: tuple[Action, ...]) -> None:
    writes = check(actions=actions)
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        for index, action in enumerate(writes):
            PROGRESS.begin(label=action.label)
            node, offset = place(action=action)
            first, data = whole_sectors(
                action=action,
                offset=offset,
                read=functools.partial(read_raw, node=node),
            )
            if read(count=len(data) // SECTOR_SIZE, first=first, node=node) == md5(
                data=data
            ):
                PROGRESS.end(skipped=True)
                continue
            staged = pathlib.Path(temporary) / f"{index}.img"
            staged.write_bytes(data=data)
            write(first=first, node=node, staged=staged)
            PROGRESS.end()


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def place(*, action: Action) -> tuple[str, int]:
    if action.target == BOOT0:
        return BOOT0_NODE, action.offset
    if action.partition is None:
        return DISK, action.offset
    return (
        f"{DISK}p{action.partition.number}",
        action.offset - action.partition.first * SECTOR_SIZE,
    )


def read(*, count: int, first: int, node: str) -> str:
    script = HASH.format(count=count, first=first, node=node)
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(remote=node)
        said = [*adb_shell(command=script, timeout=600).split(sep="\n")[-2:], "", ""]
        digest = said[0].split(sep=" ")[0]
        if said[1] == "whole" and len(digest) == MD5_DIGITS:
            break
    else:
        _die(
            message=f"{node} did not answer with an md5 of {count} sectors at"
            f" {first}. Do not restart the Dot. " + again()
        )
    return digest


def read_raw(*, count: int, first: int, node: str) -> bytes:
    try:
        block = command(
            arguments=[
                "adb",
                "exec-out",
                READ.format(count=count, first=first, node=node),
            ],
            standard_input=subprocess.DEVNULL,
            standard_output=subprocess.PIPE,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        _die(message=f"{node} could not be read at sector {first}: {error}. " + again())
    if len(block) != count * SECTOR_SIZE:
        _die(message=f"read {len(block)} bytes at sector {first} of {node}. " + again())
    return block


def write(*, first: int, node: str, staged: pathlib.Path) -> None:
    remote = DOT_TEMPORARY_DIRECTORY / staged.name
    push_checked(local=staged, remote=remote)
    unlock = relock = ""
    if node == BOOT0_NODE:
        unlock, relock = FORCE_RO.format(lock=0), FORCE_RO.format(lock=1)
    data = staged.read_bytes()
    count = len(data) // SECTOR_SIZE
    said = adb_shell(
        command=WRITE.format(
            count=count,
            first=first,
            node=node,
            relock=relock,
            source=remote,
            unlock=unlock,
        ),
        timeout=600,
    )
    if said.split(sep="\n")[-1] != "written" or read(
        count=count, first=first, node=node
    ) != md5(data=data):
        _die(
            message=f"{len(data)} bytes at sector {first} of {node} did not read"
            " back. Do not restart the Dot. " + again()
        )
