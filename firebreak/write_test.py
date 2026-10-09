from __future__ import annotations

import hashlib
import re
import subprocess
import time
from typing import TYPE_CHECKING

from firebreak.cache import CACHE
from firebreak.host import DOT_TEMPORARY_DIRECTORY, run
from firebreak.report import masked
from firebreak.ui import PROGRESS, SESSION

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterator

CARD_WRITE_FAILED = "card-write-failed"
EMMC = (
    "umount /cache 2>/dev/null;"
    " if mountpoint -q /cache; then echo cache is still mounted; exit 8; fi;"
    " if [ ! -b {node} ]; then echo {node} is not a block device; exit 7; fi;"
    " mke2fs -q -t ext4 -b 4096 -O ^sparse_super,^resize_inode"
    " -E packed_meta_blocks=1 -J size=4 -N 8192 {node} || exit 6;"
    " i=0;"
    " while [ $i -lt {rounds} ]; do"
    " {dd} if={source} of={node} bs=1048576"
    " seek=$(( {spare} + i * {chunk} )){no_truncate}"
    " || {{ echo card-write-failed; exit 9; }}; i=$(( i + 1 )); done;"
    " sync; echo 3 > /proc/sys/vm/drop_caches;"
    " echo card:$({dd} if={node} bs=1048576 skip={spare} count={blocks}"
    " 2>/dev/null | md5sum)"
)
EMMC_FORMAT = (
    "mke2fs -q -t ext4 -b 4096 {node}"
    " $(( $(blockdev --getsize64 {node}) / 4096 - 256 )) && echo formatted"
)
EMMC_SPARE = 16
EMMC_TARGET = "cache"
MEBIBYTE = 1 << 20
PATTERN = bytes(range(256)) + b"firebreak"
TIMEOUT = 1800
USB_BLOCKS = 128
USB_COLUMN = 3
USB_LEAST = 16
USB_SPARE = 32
USB_TEST = DOT_TEMPORARY_DIRECTORY / "usb-test"


def emmc_leg(
    *,
    asked: Callable[..., str],
    blocks: int,
    chunk: int,
    line: Callable[[str, object], None],
    node: str,
) -> None:
    if not blocks:
        line("over the eMMC", f"skipped: this Dot has no {EMMC_TARGET} partition")
        return
    if not chunk:
        line("over the eMMC", "skipped: nothing verified in RAM to write from")
        return
    rounds = max(blocks - EMMC_SPARE, 0) // chunk
    if not rounds:
        line(
            "over the eMMC",
            f"skipped: {EMMC_TARGET} holds under {chunk + EMMC_SPARE} MiB",
        )
        return
    written = rounds * chunk
    line(
        "writing over",
        f"{EMMC_TARGET}, {node}, {written} MiB behind a fresh filesystem"
        f" whose own blocks end by {EMMC_SPARE} MiB",
    )
    started = time.monotonic()
    PROGRESS.begin(
        estimate=f"{written // 3} s", label=f"writing and reading {EMMC_TARGET}"
    )
    said = asked(
        command=EMMC.format(
            blocks=written,
            chunk=chunk,
            dd=SESSION.dd,
            no_truncate=" conv=notrunc" if SESSION.dd == "toybox dd" else "",
            node=node,
            rounds=rounds,
            source=USB_TEST,
            spare=EMMC_SPARE,
        ),
        timeout=TIMEOUT,
    )
    PROGRESS.end()
    took = time.monotonic() - started
    if said == "<timed out>":
        line(
            "the test did not finish",
            f"no answer in {TIMEOUT} s. dd may still be writing {EMMC_TARGET},"
            " so it is left as it is: its own filesystem ends before the pattern"
            " starts. Wait a few minutes, then run this again, which formats it"
            " first.",
        )
        return
    answer = said.strip().split(sep="\n")[-1]
    read = (
        answer[len("card:") :].split(sep=" ")[0] if answer.startswith("card:") else ""
    )
    want = repeat_md5(blocks=chunk, times=rounds)
    line("md5 read back", read or "<nothing>")
    line("md5 of what was written", want)
    line(
        "moved",
        f"{2 * written} MiB written and read in {took:.0f} s,"
        f" {2 * written / max(took, 1):.0f} MiB a second",
    )
    if answer == CARD_WRITE_FAILED:
        line(
            "verdict",
            "THE eMMC REFUSED A WRITE. Nothing crossed USB, so the card or its"
            " driver is at fault, not the cable",
        )
    elif not read:
        line("the test did not run", masked(text=said) or "<nothing>")
    else:
        line(
            "verdict",
            f"the eMMC took {written} MiB and gave it back unchanged, with nothing"
            " crossing USB, so the card is not at fault"
            if read == want
            else "THE eMMC DID NOT GIVE BACK WHAT IT TOOK. Nothing crossed USB,"
            " so the card or its driver is at fault, not the cable",
        )
    formatted = asked(command=EMMC_FORMAT.format(node=node))
    line(
        "fresh filesystem",
        "yes"
        if formatted.strip().split(sep="\n")[-1] == "formatted"
        else f"NO: {masked(text=formatted) or '<nothing>'}. A Dot whose"
        f" {EMMC_TARGET} holds no filesystem does not finish booting, so run this"
        " again before restarting it: it formats cache first.",
    )


def pattern_chunks(*, blocks: int) -> Iterator[bytes]:
    buffer = PATTERN * (MEBIBYTE // len(PATTERN) + 1)
    left = blocks * MEBIBYTE
    while left:
        chunk = buffer[: min(len(buffer), left)]
        yield chunk
        left -= len(chunk)


def pattern_file(*, blocks: int, path: pathlib.Path) -> str:
    checksum = hashlib.md5(usedforsecurity=False)
    with path.open(mode="wb") as file:
        for chunk in pattern_chunks(blocks=blocks):
            file.write(chunk)
            checksum.update(chunk)
    return checksum.hexdigest()


def repeat_md5(*, blocks: int, times: int) -> str:
    checksum = hashlib.md5(usedforsecurity=False)
    for _ in range(times):
        for chunk in pattern_chunks(blocks=blocks):
            checksum.update(chunk)
    return checksum.hexdigest()


def usb_leg(*, asked: Callable[..., str], line: Callable[[str, object], None]) -> int:
    free = asked(command=f"df -k {DOT_TEMPORARY_DIRECTORY}").split(sep="\n")[-1]
    fields = free.split()
    available = fields[USB_COLUMN] if len(fields) > USB_COLUMN else ""
    spare = int(available) // 1024 if available.isdigit() else 0
    blocks = min(USB_BLOCKS, spare - USB_SPARE)
    if blocks < USB_LEAST:
        line(
            "over USB", f"skipped: {DOT_TEMPORARY_DIRECTORY} has only {spare} MiB free"
        )
        return 0
    CACHE.mkdir(exist_ok=True, parents=True)
    local = CACHE / "usb-test.bin"
    try:
        want = pattern_file(blocks=blocks, path=local)
        started = time.monotonic()
        try:
            pushed = run(arguments=["adb", "push", local, USB_TEST], timeout=TIMEOUT)
            failed = pushed.stdout if pushed.returncode else ""
        except subprocess.TimeoutExpired:
            failed = f"it did not finish in {TIMEOUT} seconds"
        took = time.monotonic() - started
    finally:
        local.unlink(missing_ok=True)
    line(
        "over USB", f"{blocks} MiB pushed into {DOT_TEMPORARY_DIRECTORY}, which is RAM"
    )
    if failed:
        line("adb push said", masked(text=failed).strip().split(sep="\n")[-1])
        line(
            "verdict",
            "USB DID NOT CARRY IT. No eMMC was written, so the cable, the port or"
            " this computer is at fault",
        )
        return 0
    answer = asked(command=f"md5sum {USB_TEST}", timeout=300).strip()
    read = answer.split(sep="\n")[-1].split(sep=" ")[0]
    if not re.fullmatch(pattern="[0-9a-f]{32}", string=read):
        line(
            "the test did not run",
            f"md5sum answered {masked(text=answer) or '<nothing>'}",
        )
        return 0
    line("md5 read back", read)
    line("md5 pushed", want)
    line("rate", f"{blocks / max(took, 1):.0f} MiB a second, over {took:.0f} s")
    line(
        "verdict",
        "USB carried it intact, so the cable and this computer are not at fault"
        if read == want
        else "USB DID NOT CARRY IT. No eMMC was written, so the cable, the port or"
        " this computer is at fault",
    )
    return blocks if read == want else 0
