"""Print a simulator trace as one normalized command per line, for diffing.

python3 simulator/trace.py TRACE.jsonl [--keep-polls] [--commands]
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re

DOWNLOADS = pathlib.Path.home() / ".cache" / "firebreak"
POLLS = (
    "adb devices",
    "adb get-state",
    "fastboot devices",
)
REPEATED_POLL = re.compile(
    r"adb shell -n getprop [\w.]+|adb wait-for-[a-z-]+|fastboot getvar [\w.-]+"
)
SIM_CACHE = pathlib.Path(
    os.environ.get("FIREBREAK_SIM_CACHE")
    or pathlib.Path.home() / ".cache" / "firebreak-sim-cache"
)
CACHE_PATTERN = re.compile(
    re.escape(str(SIM_CACHE))
    + "/(?:firebreak|overdub-firmware)/|"
    + re.escape(str(DOWNLOADS))
    + "/"
)


def event(*, entry: dict) -> str | None:
    if entry.get("event") == "boot":
        return f"# boot {entry['into']}: {entry['outcome']['mode']}"
    if entry.get("event") == "cut":
        return f"# cut by the USB switch: {normalized(entry=entry['call'])}"
    if entry.get("event") == "stdin" and entry["bytes"]:
        received = entry.get("received")
        seen = f"{received['bytes']}:{received['md5']}" if received else "unknown"
        return (
            f"# stdin sent {entry['bytes']}:{entry['md5']} received {seen}:"
            f" {normalized(entry=entry['call'])}"
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--commands", action="store_true")
    parser.add_argument("--keep-polls", action="store_true")
    options = parser.parse_args()
    printed = None
    for line in options.trace.read_text().splitlines():
        text = shown(entry=json.loads(line), options=options)
        if text is None or (text == printed and REPEATED_POLL.fullmatch(text)):
            continue
        print(text)
        printed = text


def normalized(*, entry: dict) -> str:
    text = " ".join([entry["tool"], *entry["argv"]])
    text = CACHE_PATTERN.sub("$CACHE/", text)
    text = re.sub(r"\btmp[a-z0-9_]{8}\b", "$TMP", text)
    if "md5" in entry:
        text += f" md5={entry['md5']}"
    return text


def shown(*, entry: dict, options: argparse.Namespace) -> str | None:
    if "tool" not in entry:
        return event(entry=entry)
    if entry.get("loose") and not options.commands:
        return None
    text = normalized(entry=entry)
    if options.commands and "commands" in entry:
        text += " " + " ".join(
            f"{key}x{value}" for key, value in entry["commands"].items()
        )
    if not options.keep_polls and text.startswith(POLLS):
        return None
    return text


main()
