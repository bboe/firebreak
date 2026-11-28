from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING

from firebreak.android.gpt import ENTRIES_SIZE, SECTOR_SIZE, partition_map
from firebreak.cache import CACHE, SYSTEM_SLICE_BYTES, digest, gzip_intact
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    PUSH_TRIES,
    adb_shell,
    command,
    last_line,
    md5_mismatch,
    push_checked,
    reconnect,
    run,
    stream,
)
from firebreak.plan import TABLE_SECTORS
from firebreak.ui import (
    PROGRESS,
    SESSION,
    FatalError,
    again,
    asked_for,
    replug,
    reseat,
    say,
    title,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from firebreak.plugin import Device

BCB = "misc"
BCB_COMMAND_SIZE = 32
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
FLUSHED = "flushed"
GUNZIP_FAILED = "gunzip-failed"
HASH_RATE = 5 << 20
HASH_WAIT = 30
HEAD_CHECK = 1 << 20
MD5_LENGTH = 32
MD5_OK = "md5-ok"
NODES = (
    "b=; for p in {pairs}; do n=${{p%:*}}; s=${{p#*:}};"
    ' g=$([ -b "$n" ] && blockdev --getsize64 "$n" || echo no);'
    ' [ "$g" = "$s" ] || b="$b $n=$g"; done; echo "$b nodes-ok"'
)
SLICE_OK = "slice-ok"
START_OK = "start-ok"
STDIN_PROBE_BYTES = 1024
STREAM_OK = "stream-ok"
SYSTEM_SLICE = (
    "rm -f /tmp/gunzip-failed;"
    " ( gunzip -c {held} || touch /tmp/gunzip-failed )"
    " | {dd} of={system} bs=1048576 seek={seek}{no_truncate} || exit 9;"
    " rm -f {held};"
    " [ -f /tmp/gunzip-failed ] && echo gunzip-failed || echo slice-ok"
)
SYSTEM_STREAM = (
    "rm -f /tmp/gunzip-failed;"
    " ( gunzip -c || touch /tmp/gunzip-failed )"
    " | {dd} of={system} bs=1048576{no_truncate} || exit 9;"
    " [ -f /tmp/gunzip-failed ] && echo gunzip-failed || echo stream-ok"
)
SYSTEM_TIMEOUT = 1800
TABLE_FIELDS = 6
TABLE_OK = "table-ok"
TOYBOX_DD = "toybox dd"
TOYBOX_DD_PROBE = f"{TOYBOX_DD} --help >/dev/null 2>&1 && echo yes"
TWRP_START_WAIT = 30
UNMOUNT = (
    'for m in $(grep "^/dev/block" /proc/mounts | cut -d" " -f2); do umount "$m";'
    ' done; echo "left:$(grep "^/dev/block" /proc/mounts | cut -d" " -f2'
    ' | tr "\\n" " ")"'
)


def answered(
    *,
    accept: Callable[[list[str]], bool],
    command: str,
    remote: str,
    timeout: float = 60,
) -> tuple[bool, list[str]]:
    said: list[str] = []
    for attempt in range(PUSH_TRIES):
        said = adb_shell(command=command, timeout=timeout).split(sep="\n")
        if accept(said):
            return True, said
        if attempt + 1 < PUSH_TRIES:
            reconnect(read=True, remote=remote)
    return False, said


def ask_fastboot(*, command: bytes, what: str = "fastboot") -> None:
    raw = read_sectors(count=TABLE_SECTORS, start=0)
    partition = partition_map(entries=raw[2 * SECTOR_SIZE :][:ENTRIES_SIZE]).get(BCB)
    if partition is None:
        raise FatalError(
            message=f"the {title()}'s partition table has no {BCB}, so nothing here"
            f" can ask its bootloader for {what}. Start the {title()}'s {what}"
            " by hand."
        )
    held = read_sectors(count=1, start=partition.first)
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        staged = pathlib.Path(temporary) / f"{BCB}.img"
        staged.write_bytes(
            command.ljust(BCB_COMMAND_SIZE, b"\0") + held[BCB_COMMAND_SIZE:]
        )
        write(
            estimate=5,
            label=f"asking the bootloader for {what}",
            number=partition.number,
            path=staged,
            sector=partition.first,
        )


def check_nodes(*, want: dict[str, int]) -> str:
    command = NODES.format(
        pairs=" ".join(f"{node}:{size}" for node, size in want.items())
    )

    def read(lines: list[str]) -> list[tuple[str, str, str]] | None:
        said = lines[-1]
        if not said.endswith("nodes-ok"):
            return None
        found = [token.partition("=") for token in said[: -len("nodes-ok")].split()]
        return found if all(node in want for node, _, _ in found) else None

    ok, lines = answered(
        accept=lambda lines: read(lines) is not None, command=command, remote=DISK
    )
    if ok:
        return ", ".join(
            f"{node} reads {got}, not {want[node]} bytes"
            for node, _, got in read(lines) or []
        )
    said = lines[-1]
    raise FatalError(
        message=f"the {title()} did not answer which of its partitions are block"
        f" devices: {said!r}. " + again()
    )


def clear_boot0() -> None:
    answer = last_line(said=adb_shell(command=CLEAR_BOOT0)).split()
    if answer == ["4096", "0"]:
        return
    read, *still_set = answer or [""]
    if read == "4096" and still_set:
        SESSION.boot0_erased = False
        raise FatalError(
            message="boot0's header did not clear, so a failure from here would brick"
            " rather than fall into the bootrom; nothing else was written",
        )
    raise FatalError(
        message="boot0 did not read back, so whether its header cleared is unknown;"
        " nothing else was written"
    )


def detect_dd(*, asked: Callable[..., str]) -> None:
    if last_line(said=asked(command=TOYBOX_DD_PROBE)) == "yes":
        SESSION.dd = TOYBOX_DD


def hashed(*, command: str, remote: str = DISK, size: int) -> str:
    ok, said = answered(
        accept=lambda said: (
            said[-1] == MD5_OK
            and len(said) > 1
            and len(said[-2].split(sep=" ")[0]) == MD5_LENGTH
        ),
        command=f"{command}; echo {MD5_OK}",
        remote=remote,
        timeout=HASH_WAIT + size / HASH_RATE,
    )
    return said[-2].split(sep=" ")[0] if ok else ""


def no_truncate() -> str:
    return " conv=notrunc" if SESSION.dd == TOYBOX_DD else ""


def partition_start(*, number: int) -> str:
    command = f'echo "$(cat /sys/class/block/mmcblk0p{number}/start) {START_OK}"'
    ok, lines = answered(
        accept=lambda lines: (
            lines[-1].split()[1:] == [START_OK] and lines[-1].split()[0].isdecimal()
        ),
        command=command,
        remote=f"{DISK}p{number}",
    )
    said = lines[-1].split()
    if ok:
        return said[0]
    raise FatalError(
        message=f"the {title()} did not answer where {DISK}p{number} starts:"
        f" {' '.join(said) or 'nothing'}. " + again()
    )


def partition_table() -> str:
    ok, said = answered(
        accept=lambda said: (
            said[-1] == TABLE_OK and any(" userdata" in line for line in said)
        ),
        command=f"sgdisk --print {DISK}; echo {TABLE_OK}",
        remote=DISK,
        timeout=30,
    )
    if ok:
        return "\n".join(said[:-1])
    raise FatalError(
        message=f"sgdisk did not print the {title()}'s partition table:\n"
        + "\n".join(said)
    )


def partitions() -> dict[str, tuple[int, int, int]]:
    found = {}
    for line in partition_table().split(sep="\n"):
        field = line.split()
        if len(field) >= TABLE_FIELDS and all(value.isdigit() for value in field[:3]):
            found[field[-1]] = (int(field[0]), int(field[1]), int(field[2]))
    if "userdata" not in found:
        raise FatalError(message=f"no userdata in the {title()}'s partition table")
    return found


def push_to_node(*, label: str, node: str, path: pathlib.Path) -> None:
    for attempt in range(PUSH_TRIES):
        pushed = run(arguments=["adb", "push", path, node], timeout=1800)
        if pushed.returncode == 0:
            return
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=node)
    raise FatalError(
        message=f"{label} failed {PUSH_TRIES} times; do not reboot:\n{pushed.stdout}"
    )


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
        raise FatalError(
            message=f"read {len(raw)} bytes from the {title()}'s eMMC, not"
            f" {count * 512}"
        )
    return raw


def reboot(*, estimate: int = 40, into: str = "recovery", label: str) -> None:
    run(arguments=["adb", "reboot", *([into] if into else [])], check=True, timeout=60)
    PROGRESS.begin(estimate=estimate, label=label)


def restart_into_twrp(*, device: Device) -> None:
    if not device.recovery_command:
        reboot(label="restarting into TWRP")
        return
    ask_fastboot(command=device.recovery_command, what="TWRP")
    reboot(into="", label="restarting into TWRP")


def sliced_system(*, slices: list[pathlib.Path], system: str) -> str:
    held = DOT_TEMPORARY_DIRECTORY / "system-slice.gz"
    for index, piece in enumerate(slices):
        push_checked(advice=reseat() + " ", local=piece, remote=held)
        result = run(
            arguments=[
                "adb",
                "shell",
                "-n",
                SYSTEM_SLICE.format(
                    dd=SESSION.dd,
                    held=held,
                    no_truncate=no_truncate(),
                    seek=index * (SYSTEM_SLICE_BYTES >> 20),
                    system=system,
                ),
            ],
            timeout=900,
        )
        said = result.stdout.strip()
        if last_line(said=said) == GUNZIP_FAILED:
            piece.unlink(missing_ok=True)
            return (
                f"{piece.name} arrived intact but did not unpack on the {title()},"
                " so the cached image was discarded and the next run rebuilds it"
            )
        if result.returncode:
            return said or f"it exited with {result.returncode}"
        if last_line(said=said) != SLICE_OK:
            return said or f"the {title()} said nothing about {piece.name}"
    return ""


def staged_write(
    *, block_size: int, label: str, offset: int, path: pathlib.Path
) -> None:
    staged = DOT_TEMPORARY_DIRECTORY / path.name
    for attempt in range(PUSH_TRIES):
        pushed = run(arguments=["adb", "push", path, staged], timeout=120)
        done = (
            adb_shell(
                command=f"{SESSION.dd} if={staged} of={DISK} bs={block_size}"
                f" seek={offset}{no_truncate()} && rm -f {staged} && echo written"
            )
            if pushed.returncode == 0
            else ""
        )
        if last_line(said=done) == "written":
            return
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=staged)
    if pushed.returncode != 0:
        raise FatalError(
            message=f"{label} did not reach the {title()}; do not reboot:"
            f"\n{pushed.stdout}"
        )
    raise FatalError(message=f"{label} failed; do not reboot:\n{done}")


def stdin_carries() -> bool:
    if SESSION.carries is None:
        probe = CACHE / "stdin-probe.bin"
        probe.write_bytes(data=b"\x1a" * 16 + os.urandom(STDIN_PROBE_BYTES - 16))
        remote = DOT_TEMPORARY_DIRECTORY / "stdin-probe"
        try:
            with probe.open(mode="rb") as file:
                sent = run(
                    arguments=["adb", "shell", f"cat > {remote}"],
                    standard_input=file,
                    timeout=60,
                )
            failed = sent.returncode != 0
            cut = bool(
                md5_mismatch(
                    command=f"md5sum {remote}; rm -f {remote}",
                    timeout=60,
                    want=digest(kind="md5", path=probe),
                )
            )
        except subprocess.TimeoutExpired:
            failed = cut = True
        finally:
            probe.unlink(missing_ok=True)
        SESSION.carries = not cut and not failed
        if failed:
            say(
                text="This computer's adb did not carry a 1 KiB probe either way,"
                " so the image goes over in pieces, which needs no stream."
            )
    return SESSION.carries


def streamed_system(*, slices: list[pathlib.Path], system: str) -> str:
    result = stream(
        arguments=[
            "adb",
            "shell",
            SYSTEM_STREAM.format(
                dd=SESSION.dd,
                no_truncate=no_truncate(),
                system=system,
            ),
        ],
        pieces=slices,
        timeout=SYSTEM_TIMEOUT,
    )
    said = result.stdout.strip()
    if last_line(said=said) == GUNZIP_FAILED:
        broken = [piece for piece in slices if not gzip_intact(path=piece)]
        for piece in broken:
            piece.unlink(missing_ok=True)
        if broken:
            return (
                f"{', '.join(piece.name for piece in broken)} did not unpack on"
                " this computer either, so the cached image was discarded and the"
                " next run rebuilds it"
            )
        return "gunzip could not read the stream"
    if result.returncode:
        return said or f"it exited with {result.returncode}"
    if last_line(said=said) != STREAM_OK:
        return said or f"the {title()} said nothing about the write"
    return ""


def unmount(*, started: bool = False) -> None:
    left = last_line(said=adb_shell(command=UNMOUNT))
    if left.startswith("left:"):
        if not left[len("left:") :].strip():
            return
        message = "still mounted: " + left[len("left:") :].strip()
    else:
        message = f"the {title()} did not answer what is mounted: " + left
    if started:
        raise FatalError(message=message + "; do not reboot")
    raise FatalError(message=message + "; nothing was written")


def wait_for_twrp() -> None:
    time.sleep(15)
    try:
        run(arguments=["adb", "wait-for-recovery"], timeout=300)
    except subprocess.TimeoutExpired:
        raise FatalError(
            message=f"the {title()} did not reach recovery (TWRP) within 5"
            " minutes. A ring that keeps restarting there is a USB port that"
            " cannot power TWRP. To tell, a USB wall charger with the + button"
            f" held starts TWRP if the {title()} can run it at all. To retry,"
            f" {replug()}"
        ) from None
    wait_for_twrp_start(version_timeout=30)


def wait_for_twrp_start(
    *, accept: Callable[..., None] = lambda **_: None, version_timeout: float = 300
) -> None:
    deadline = time.monotonic() + TWRP_START_WAIT
    while True:
        version = adb_shell(command="getprop ro.twrp.version", timeout=version_timeout)
        if version[:1].isdigit():
            accept(version=version)
            if "mtp" in adb_shell(command="getprop sys.usb.config"):
                return
        if time.monotonic() > deadline:
            raise FatalError(
                message=f"TWRP did not finish starting within {TWRP_START_WAIT}"
                f" seconds. A USB port that cannot power the {title()} can cause"
                f" this. To retry, {replug()}"
            )
        time.sleep(1)


def write(
    *,
    estimate: int,
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
    same_head = head == size or hashed(
        command=f"{SESSION.dd} if={DISK} bs={block_size} skip={offset}"
        f" count={head // block_size} 2>/dev/null | md5sum",
        size=head,
    ) == digest(kind="md5", limit=head, path=path)
    if same_head and hashed(command=verify, size=size) == want:
        PROGRESS.end(skipped=True)
        return
    if number is not None:
        start = partition_start(number=number)
        if start != str(sector):
            raise FatalError(
                message=f"{DISK}p{number} starts at {start}, not {sector},"
                " so the running partition table is not the one this expects"
            )
        push_to_node(label=label, node=f"{DISK}p{number}", path=path)
    else:
        staged_write(block_size=block_size, label=label, offset=offset, path=path)
    flushed, _ = answered(
        accept=lambda said: said[-1] == FLUSHED, command=FLUSH, remote=DISK
    )
    if not flushed:
        raise FatalError(message=label + " could not be flushed; do not reboot")
    got = hashed(command=verify, size=size)
    if not got:
        raise FatalError(
            message=f"{label} could not be read back after {PUSH_TRIES} tries;"
            " do not reboot"
        )
    if got != want:
        raise FatalError(
            message=f"{label} did not verify: read {got}, expected {want};"
            " do not reboot"
        )
    PROGRESS.end()


def write_system(
    *, blocks: int, slices: list[pathlib.Path], system: str, want: str
) -> None:
    ready = adb_shell(
        command="umount /system_root /tmp/fireos-system 2>/dev/null;"
        f' d=$(readlink -f {system}); [ -b "$d" ]'
        f' && ! grep -q -e "^$d " -e "^{system} " /proc/mounts && echo ready'
    )
    if last_line(said=ready) != "ready":
        raise FatalError(
            message=f"{system} is not a block device, or it stayed mounted"
        )
    read_back = (
        "sync; echo 3 > /proc/sys/vm/drop_caches;"
        f" {SESSION.dd} if={system} bs=4096 count={blocks} 2>/dev/null | md5sum"
    )
    carry = streamed_system if stdin_carries() else sliced_system
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(remote=system)
        try:
            said = carry(slices=slices, system=system)
            if (
                not said
                and adb_shell(command=read_back, timeout=300).split(sep=" ")[0] != want
            ):
                said = "its md5 read back did not match"
        except subprocess.TimeoutExpired as error:
            said = (
                f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
        if not said:
            return
        if not all(path.exists() for path in slices):
            break
    if said == "its md5 read back did not match":
        slices[0].unlink(missing_ok=True)
        said += ". The cached image was discarded, so the next run rebuilds it"
    reseated = f" {reseat()}" if all(path.exists() for path in slices) else ""
    raise FatalError(
        message=f"{system} was not written intact after {PUSH_TRIES} tries;"
        f" the last: {said}.{reseated} " + asked_for()
    )
