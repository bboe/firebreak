from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from firebreak.twrp import DISK, TABLE_FIELDS, TABLE_OK

if TYPE_CHECKING:
    from collections.abc import Callable

BOOT_LINE = 'dmesg | grep "MMC card at address" | head -1'
BOOT_OK = "boot-ok"
EMMC_FIELDS = ("name", "manfid", "oemid", "prv", "life_time", "pre_eol_info")
GUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
LEFT_IN_RECOVERY = "The Dot stays in its recovery: adb reboot starts it again."
LISTING_OK = "listing-ok"
LOG_OK = "log-ok"
MMC_LOG = 'dmesg | grep -iE "mmc|msdc" | tail -60'
MMC_LOG_REACHES_BOOT = "MMC card at address"
PARTITIONS_OK = "partitions-ok"
PARTITION_FIELDS = 4
PROPERTIES = (
    "ro.product.device",
    "ro.build.version.name",
    "ro.build.version.number",
    "ro.build.type",
    "ro.twrp.version",
    "ro.boot.lk_build_desc",
)
RECORD_FIELDS = 2


def dot_details(*, asked: Callable[..., str]) -> list[str]:
    said = [
        labelled(label=name, value=asked(command=f"getprop {name}"))
        for name in PROPERTIES
    ]
    for name in EMMC_FIELDS:
        where = f"/sys/block/{node_held(target=DISK)}/device/{name}"
        said.append(
            labelled(
                label=f"eMMC {name}",
                value=asked(command=f"cat {where} 2>/dev/null || echo '<absent>'"),
            )
        )
    window = asked(command="dmesg | head -1 | sed -e 's/^\\[ *//' -e 's/\\].*//'")
    held = asked(command="cut -d' ' -f1 /proc/uptime")
    said.append(labelled(label="uptime", value=f"{held} s, dmesg from {window} s"))
    return said


def labelled(*, label: str, value: object) -> str:
    return f"{label:<24} {value}"


def masked(*, text: str) -> str:
    text = re.sub(flags=re.IGNORECASE, pattern=GUID, repl="<guid>", string=text)
    serial = os.environ.get("ANDROID_SERIAL", "")
    return text.replace(serial, "<serial>") if serial else text


def mmc_said(*, asked: Callable[..., str]) -> list[str]:
    raw = asked(command=f"{MMC_LOG}; echo {LOG_OK}")
    logged = whole(marker=LOG_OK, said=raw)
    first = whole(marker=BOOT_OK, said=asked(command=f"{BOOT_LINE}; echo {BOOT_OK}"))
    if logged is None or first is None:
        return [raw, "\nThat log did not arrive whole, so it says nothing either way."]
    first = first.strip()
    if MMC_LOG_REACHES_BOOT in logged:
        return [logged]
    if MMC_LOG_REACHES_BOOT in first:
        return [first, "...", logged]
    if not any(word in logged.lower() for word in ("mmc", "msdc")):
        unread = "\nThat is not the kernel's log, so it says nothing either way."
        return [logged, unread]
    gone = (
        "\nThat log no longer reaches the boot, so the card's own lines are gone."
        " They come back from a restart into this recovery, which is safe only"
        " when a run is not part-way through writing. Restart it yourself and"
        " run this again if they are wanted."
    )
    return [logged, gone]


def node_held(*, target: str) -> str:
    return target.rsplit(maxsplit=1, sep="/")[-1]


def node_names(*, listing: str) -> dict[str, str]:
    found = {}
    for row in listing.split(sep="\n"):
        name, arrow, target = row.partition(" -> ")
        if arrow:
            found[name.split()[-1]] = target.strip()
    for name, target in tuple(found.items()):
        if not node_order(node=target):
            found[name] = found.get(node_held(target=target), target)
    return found


def node_order(*, node: str) -> int:
    disk, _, number = node_held(target=node).partition("p")
    return int(number) if disk.startswith("mmcblk") and number.isdigit() else 0


def node_sizes(*, partitions: str) -> dict[str, int]:
    return {
        field[-1]: int(field[2]) * 1024
        for field in (row.split() for row in partitions.split(sep="\n"))
        if len(field) == PARTITION_FIELDS and field[2].isdigit()
    }


def partition_row(*, row: str) -> int:
    field = row.split()
    if not field or not field[0].isdigit():
        return 0
    return int(field[0]) if len(field) >= TABLE_FIELDS else 0


def partition_rows(*, names: dict[str, str] | None, printed: str) -> list[str]:
    said = [row.rstrip() for row in printed.split(sep="\n")]
    if said[-1:] != [TABLE_OK] or not any(partition_row(row=row) for row in said):
        return [*said, "", "That is not a whole table, so no name was matched to it."]
    said = said[:-1]
    if names is None:
        return [*said, "", "The Dot's names did not arrive whole, so none was matched."]
    held: dict[str, list[str]] = {}
    for name, target in sorted(names.items()):
        key = node_held(target=target) if node_order(node=target) else target
        held.setdefault(key, []).append(name)
    header = next((row for row in said if row.lstrip().startswith("Number ")), None)
    width = max(len(row) for row in said if partition_row(row=row) or row == header)
    rows = []
    for row in said:
        number = partition_row(row=row)
        if not number:
            rows.append(
                f"{row:<{width}}  {'node':<10}  alias" if row == header else row
            )
            continue
        node = f"{node_held(target=DISK)}p{number}"
        linked = held.pop(node, [])
        called = [name for name in linked if name != row.split()[-1]]
        alias = ", ".join(called) if called else "" if linked else "<no name>"
        rows.append(f"{row:<{width}}  {node:<10}  {alias}".rstrip())
    return rows + unreal_rows(held=held)


def system_a_rows(
    *, names: dict[str, str] | None, needs: int, partitions: str | None
) -> list[tuple[str, str]]:
    if names is None or partitions is None:
        return [("system_a", "unknown: the Dot's partition lists did not arrive whole")]
    holds = node_sizes(partitions=partitions).get(
        node_held(target=names.get("system_a", "")), 0
    )
    rows = [("system_a", f"{names.get('system_a') or '<unknown>'}, {holds} bytes")]
    if holds and needs:
        rows.append(("system_a spare", f"{holds - needs} bytes"))
    return rows


def system_record(*, text: str) -> tuple[str, int]:
    recorded = text.split()
    if len(recorded) >= RECORD_FIELDS and recorded[1].isdigit():
        return recorded[0], int(recorded[1]) * 4096
    return "", 0


def unreal_rows(*, held: dict[str, list[str]]) -> list[str]:
    if not held:
        return []
    pairs = sorted((", ".join(called), target) for target, called in held.items())
    width = max(len(called) for called, _ in pairs)
    return ["", "names that point outside the partition table"] + [
        f"{called:<{width}}  {target}" for called, target in pairs
    ]


def whole(*, marker: str, said: str) -> str | None:
    rows = said.rstrip().split(sep="\n")
    return "\n".join(rows[:-1]) if rows[-1].strip() == marker else None
