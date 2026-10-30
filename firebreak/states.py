from __future__ import annotations

import enum


class State(enum.Enum):
    AMONET_BOOTED = "amonet-booted"
    AMONET_FASTBOOT = "amonet-fastboot"
    AMONET_FIREOS5_BBOE_BOOTED = "amonet-fireos5-bboe-booted"
    AMONET_FIREOS5_BBOE_TWRP = "amonet-fireos5-bboe-twrp"
    AMONET_FIREOS5_FASTBOOT = "amonet-fireos5-fastboot"
    AMONET_FIREOS5_TWRP = "amonet-fireos5-twrp"
    AMONET_TWRP = "amonet-twrp"
    AMONET_TWRP_BOOT_MOVED = "amonet-twrp-boot-moved"
    BOOTED = "booted"
    BOOTROM = "bootrom"
    EMOS = "emos"
    NONE = "none"
    NO_SYSTEM = "no-system"
    PRELOADER = "preloader"
    ROOTED = "rooted"
    STARTING = "starting"
    STOCK_BOOTED = "stock-booted"
    STOCK_FASTBOOT = "stock-fastboot"
    STOCK_FIREOS5_FASTBOOT = "stock-fireos5-fastboot"
