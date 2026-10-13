from __future__ import annotations

import enum
import re

from firebreak.layouts import BootMovedLayout, StockLayout
from firebreak.plugin import Device, Feature

BOOT_MOVED_LAYOUT = BootMovedLayout(
    align=0x400, sectors=0x37000, targets=("boot_a", "boot_b")
)
BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green. A"
    " ring that stays solid blue can mean the USB port gives too little power:"
    " try another port."
)
LITTLE_KERNEL_DESCRIPTION = re.compile(pattern=r"[0-9a-f]{7}-\d{8}_\d{6}")
STOCK_LAYOUT = StockLayout(partitions=16)
BISCUIT = Device(
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    layouts=(BOOT_MOVED_LAYOUT, STOCK_LAYOUT),
    name="biscuit",
)


class LK(enum.Enum):
    FIREOS5 = "f379dba-20170906_000423"
    FIREOS6 = "63cb91b-20221007_072309"
    FIREOS6_4315 = "41fb3ce-20221007_151724"


class State(enum.Enum):
    AMONET_V1_1_0_BBOE_BOOTED = "amonet-v1.1.0-bboe-booted"
    AMONET_V1_1_0_BBOE_TWRP = "amonet-v1.1.0-bboe-twrp"
    AMONET_V1_1_0_BOOTED = "amonet-v1.1.0-booted"
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
    STARTING = "starting"
    STOCK_BOOTED = "stock-booted"
    STOCK_FASTBOOT = "stock-fastboot"
    STOCK_FIREOS5_FASTBOOT = "stock-fireos5-fastboot"
