"""Download what `dot.py create` reads for a device before firebreak runs.

python3 simulator/fetch.py biscuit|donut|radar
"""

from __future__ import annotations

import gc
import sys

import firebreak.devices  # ruff: ignore[unused-import]
from firebreak.cache import CACHE, Download, fetch

NEEDS = {
    "biscuit": (
        "amonet-biscuit-v1.1.0.zip",
        "amonet-biscuit-v2.0.0.zip",
        "amonet-biscuit-v2.0.1.zip",
        "twrp-3.7.0_9-bboe2-biscuit.img",
    ),
    "donut": ("kamakiri-donut-v1.0.0.zip",),
    "radar": ("amonet-radar-v1.0.1.zip",),
}


def main() -> int:
    CACHE.mkdir(exist_ok=True, parents=True)
    known = {item.name: item for item in gc.get_objects() if isinstance(item, Download)}
    for name in NEEDS[sys.argv[1]]:
        print(fetch(download=known[name]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
