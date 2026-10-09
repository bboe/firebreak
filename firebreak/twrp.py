from __future__ import annotations

import subprocess
import time
from typing import TYPE_CHECKING, NoReturn

from firebreak.cache import ERASED, digest
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    PUSH_TRIES,
    adb_shell,
    command,
    md5_mismatch,
    reconnect,
    run,
)
from firebreak.ui import PROGRESS, SESSION, _die, again

if TYPE_CHECKING:
    import pathlib

CLEAR_BOOT0 = (
    "d=dd; toybox dd --help >/dev/null 2>&1 && d='toybox dd'; "
    "echo 0 > /sys/block/mmcblk0boot0/force_ro; "
    "$d if=/dev/zero of=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null; "
    "echo 1 > /sys/block/mmcblk0boot0/force_ro; sync; "
    "echo 3 > /proc/sys/vm/drop_caches; "
    'echo "$($d if=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null | wc -c)'
    " $($d if=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null"
    " | tr -d '\\0' | wc -c)\""
)
DISK = "/dev/block/mmcblk0"
FLUSH = "sync && echo 3 > /proc/sys/vm/drop_caches && echo flushed"
HEAD_CHECK = 1 << 20
NODES = (
    "b=; for p in {pairs}; do n=${{p%:*}}; s=${{p#*:}};"
    ' g=$([ -b "$n" ] && blockdev --getsize64 "$n" || echo no);'
    ' [ "$g" = "$s" ] || b="$b $n=$g"; done; echo "$b nodes-ok"'
)
TABLE_FIELDS = 6
UNMOUNT = (
    'for m in $(grep "^/dev/block" /proc/mounts | cut -d" " -f2); do umount "$m";'
    ' done; echo "left:$(grep "^/dev/block" /proc/mounts | cut -d" " -f2'
    ' | tr "\\n" " ")"'
)


def check_nodes(*, want: dict[str, int]) -> str:
    command = NODES.format(
        pairs=" ".join(f"{node}:{size}" for node, size in want.items())
    )
    for attempt in range(PUSH_TRIES):
        said = adb_shell(command=command, timeout=60).split(sep="\n")[-1]
        if said.endswith("nodes-ok"):
            read = [token.partition("=") for token in said[: -len("nodes-ok")].split()]
            if all(node in want for node, _, _ in read):
                return ", ".join(
                    f"{node} reads {got}, not {want[node]} bytes"
                    for node, _, got in read
                )
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(
        message="the Dot did not answer which of its partitions are block"
        f" devices: {said!r}. " + again()
    )
    return ""


def clear_boot0() -> None:
    answer = adb_shell(command=CLEAR_BOOT0).split(sep="\n")[-1].split()
    if answer == ["4096", "0"]:
        return
    read, *still_set = answer or [""]
    if read == "4096" and still_set:
        ERASED.unlink(missing_ok=True)
        restore_failed(
            bootable=True,
            message="boot0's header did not clear, so a failure from here would brick"
            " rather than fall into the bootrom; nothing else was written",
        )
    restore_failed(
        message="boot0 did not read back, so whether its header cleared is unknown;"
        " nothing else was written"
    )


def partition_field(*, name: str, number: int) -> str:
    command = f"sgdisk --info={number} {DISK}; echo field-ok"
    for attempt in range(PUSH_TRIES):
        output = adb_shell(command=command, timeout=30)
        if output.split(sep="\n")[-1] == "field-ok":
            for line in output.split(sep="\n"):
                if line.startswith(name + ":"):
                    return (
                        line.split(maxsplit=1, sep=":")[1].strip().strip("'").split()[0]
                    )
            _die(message=f"sgdisk --info={number} printed no {name}:\n{output}")
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(message=f"sgdisk --info={number} did not answer in full. " + again())
    return ""


def partition_table() -> str:
    command = f"sgdisk --print {DISK}; echo table-ok"
    for attempt in range(PUSH_TRIES):
        said = adb_shell(command=command, timeout=30).split(sep="\n")
        if said[-1] == "table-ok" and any(" userdata" in line for line in said):
            return "\n".join(said[:-1])
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(message="sgdisk did not print the Dot's partition table:\n" + "\n".join(said))
    return ""


def partitions() -> dict[str, tuple[int, int, int]]:
    found = {}
    for line in partition_table().split(sep="\n"):
        field = line.split()
        if len(field) >= TABLE_FIELDS and all(value.isdigit() for value in field[:3]):
            found[field[-1]] = (int(field[0]), int(field[1]), int(field[2]))
    if "userdata" not in found:
        _die(message="no userdata in the Dot's partition table")
    return found


def read_sectors(*, count: int, start: int) -> bytes:
    raw = command(
        arguments=[
            "adb",
            "exec-out",
            f"{SESSION.dd} if={DISK} bs=512 skip={start} count={count} 2>/dev/null",
        ],
        standard_input=subprocess.DEVNULL,
        standard_output=subprocess.PIPE,
        timeout=60,
    ).stdout
    if len(raw) != count * 512:
        _die(
            message=f"read {len(raw)} bytes of the Dot's partition table,"
            f" not {count * 512}"
        )
    return raw


def restore_failed(*, bootable: bool = False, message: str) -> NoReturn:
    if not bootable and ERASED.exists():
        message = message.rstrip(".") + (
            ". boot0 has no preloader until the last step, so the Dot will not"
            " start at all until this run finishes"
        )
    _die(message=message)


def unmount(*, started: bool = False) -> None:
    left = adb_shell(command=UNMOUNT).split(sep="\n")[-1]
    if left.startswith("left:"):
        if not left[len("left:") :].strip():
            return
        message = "still mounted: " + left[len("left:") :].strip()
    else:
        message = "the Dot did not answer what is mounted: " + left
    if started:
        restore_failed(message=message + "; do not reboot")
    _die(message=message + "; nothing was written")


def wait_for_twrp() -> None:
    time.sleep(15)
    try:
        run(arguments=["adb", "wait-for-recovery"], timeout=300)
    except subprocess.TimeoutExpired:
        _die(message="the Dot did not reach recovery (TWRP) within 5 minutes")
    deadline = time.monotonic() + 30
    while not adb_shell(command="getprop ro.twrp.version", timeout=30)[
        :1
    ].isdigit() or "mtp" not in adb_shell(command="getprop sys.usb.config"):
        if time.monotonic() > deadline:
            _die(message="TWRP did not finish starting within 30 seconds")
        time.sleep(1)


def write(
    *,
    estimate: str,
    label: str,
    number: int | None = None,
    path: pathlib.Path,
    sector: int,
) -> None:
    size = path.stat().st_size
    if sector % 8 == 0 and size % 4096 == 0:
        block_size, offset, count = 4096, sector // 8, size // 4096
    else:
        block_size, offset, count = 512, sector, size // 512
    verify = (
        f"{SESSION.dd} if={DISK} bs={block_size} skip={offset} count={count}"
        " 2>/dev/null | md5sum"
    )
    want = digest(kind="md5", path=path)
    head = min(size, HEAD_CHECK)
    PROGRESS.begin(estimate=estimate, label=label)
    same_head = head == size or not md5_mismatch(
        command=f"{SESSION.dd} if={DISK} bs={block_size} skip={offset}"
        f" count={head // block_size} 2>/dev/null | md5sum",
        want=digest(kind="md5", limit=head, path=path),
    )
    if same_head and not md5_mismatch(command=verify, want=want):
        PROGRESS.end(skipped=True)
        return
    if number is not None:
        start = adb_shell(command=f"cat /sys/class/block/mmcblk0p{number}/start")
        if start.split(sep="\n")[-1].strip() != str(sector):
            restore_failed(
                message=f"{DISK}p{number} starts at {start or 'nothing'}, not {sector},"
                " so the running partition table is not the one this expects"
            )
        pushed = run(arguments=["adb", "push", path, f"{DISK}p{number}"], timeout=1800)
        if pushed.returncode != 0:
            restore_failed(message=f"{label} failed; do not reboot:\n{pushed.stdout}")
    else:
        staged = DOT_TEMPORARY_DIRECTORY / path.name
        pushed = run(arguments=["adb", "push", path, staged], timeout=120)
        if pushed.returncode != 0:
            restore_failed(
                message=f"{label} did not reach the Dot; do not reboot:"
                f"\n{pushed.stdout}"
            )
        no_truncate = " conv=notrunc" if SESSION.dd == "toybox dd" else ""
        done = adb_shell(
            command=f"{SESSION.dd} if={staged} of={DISK} bs={block_size} seek={offset}"
            f"{no_truncate} && rm -f {staged} && echo written"
        )
        if done.split(sep="\n")[-1] != "written":
            restore_failed(message=f"{label} failed; do not reboot:\n{done}")
    if adb_shell(command=FLUSH).split(sep="\n")[-1] != "flushed":
        restore_failed(message=label + " could not be flushed; do not reboot")
    wrong = md5_mismatch(command=verify, want=want)
    if wrong:
        restore_failed(message=f"{label} did not verify{wrong}; do not reboot")
    PROGRESS.end()


def write_system(*, blocks: int, image: pathlib.Path, system: str, want: str) -> None:
    ready = adb_shell(
        command="umount /system_root /tmp/fireos-system 2>/dev/null;"
        f' d=$(readlink -f {system}); [ -b "$d" ]'
        f' && ! grep -q -e "^$d " -e "^{system} " /proc/mounts && echo ready'
    )
    if ready.split(sep="\n")[-1] != "ready":
        _die(message=f"{system} is not a block device, or it stayed mounted")
    stream = f"gunzip -c | dd of={system} bs=1048576 2>/dev/null"
    read_back = (
        "sync; echo 3 > /proc/sys/vm/drop_caches;"
        f" dd if={system} bs=4096 count={blocks} 2>/dev/null | md5sum"
    )
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(remote=system)
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            with image.open(mode="rb") as file:
                result = run(
                    arguments=["adb", "shell", stream], standard_input=file, timeout=600
                )
            if result.returncode != 0:
                said = result.stdout or f"it exited with {result.returncode}"
                continue
            if adb_shell(command=read_back, timeout=300).split(sep=" ")[0] == want:
                return
            said = "its md5 read back did not match"
        except subprocess.TimeoutExpired as error:
            said = (
                f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
    if said == "its md5 read back did not match":
        (image.parent / "md5").unlink(missing_ok=True)
        said += ". The cached image was discarded, so the next run rebuilds it"
    _die(
        message=f"{system} was not written intact after {PUSH_TRIES} tries;"
        f" the last: {said}"
    )
