from __future__ import annotations

import enum

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


class State(enum.Enum):
    AMONET_V1_1_0_BBOE_TWRP = "amonet-v1.1.0-bboe-twrp"
    AMONET_V1_1_0_FASTBOOT = "amonet-v1.1.0-fastboot"
    AMONET_V1_1_0_TWRP = "amonet-v1.1.0-twrp"
    AMONET_V2_0_0_BOOTED = "amonet-v2.0.0-booted"
    AMONET_V2_0_0_FASTBOOT = "amonet-v2.0.0-fastboot"
    AMONET_V2_0_0_TWRP = "amonet-v2.0.0-twrp"
    AMONET_V2_0_0_TWRP_V1_1_0_TABLE = "amonet-v2.0.0-twrp-v1.1.0-table"
    BOOTED = "booted"
    EMOS = "emos"
    NONE = "none"
    ROOTED = "rooted"
    ROOTED_AMONET_V1_1_0 = "rooted-amonet-v1.1.0"
    ROOTED_AMONET_V1_1_0_BBOE = "rooted-amonet-v1.1.0-bboe"
    STARTING = "starting"
    STOCK_BOOTED = "stock-booted"
    STOCK_FASTBOOT = "stock-fastboot"
    STOCK_FIREOS5_FASTBOOT = "stock-fireos5-fastboot"
