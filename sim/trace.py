"""Print a simulator trace as one normalized command per line, for diffing.

python3 sim/trace.py TRACE.jsonl [--keep-polls] [--commands]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

POLLS = (
    "adb devices",
    "adb get-state",
    "adb shell -n getprop",
    "fastboot devices",
    "fastboot getvar",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=pathlib.Path)
    parser.add_argument("--commands", action="store_true")
    parser.add_argument("--keep-polls", action="store_true")
    options = parser.parse_args()
    previous = None
    for line in options.trace.read_text().splitlines():
        entry = json.loads(line)
        if "tool" not in entry:
            if entry.get("event") == "boot":
                text = f"# boot {entry['into']}: {entry['outcome']['mode']}"
            else:
                continue
        else:
            text = normalized(entry)
            if options.commands and "commands" in entry:
                text += " " + " ".join(
                    f"{key}x{value}" for key, value in entry["commands"].items()
                )
            if not options.keep_polls and text.startswith(POLLS):
                continue
        if text != previous:
            print(text)
        previous = text


def normalized(entry: dict) -> str:
    text = " ".join([entry["tool"], *entry["argv"]])
    text = re.sub(r"/\S*?/(?:firebreak|overdub-firmware)/", "$CACHE/", text)
    return re.sub(r"\btmp[a-z0-9_]{8}\b", "$TMP", text)


main()
