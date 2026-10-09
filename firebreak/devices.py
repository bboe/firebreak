from __future__ import annotations

from firebreak.layouts import BootMovedLayout, StockLayout
from firebreak.plugin import Device, Feature

BOOT_MOVED_LAYOUT = BootMovedLayout(
    align=0x400, sectors=0x37000, targets=("boot_a", "boot_b")
)
STOCK_LAYOUT = StockLayout(partitions=16)
BISCUIT = Device(
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    layouts=(BOOT_MOVED_LAYOUT, STOCK_LAYOUT),
    name="biscuit",
)
