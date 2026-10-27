from __future__ import annotations

import enum


class State(enum.Enum):
    AMONET_V1_1_0_BBOE_BOOTED = "amonet-v1.1.0-bboe-booted"
    AMONET_V1_1_0_BBOE_TWRP = "amonet-v1.1.0-bboe-twrp"
    AMONET_V1_1_0_FASTBOOT = "amonet-v1.1.0-fastboot"
    AMONET_V1_1_0_TWRP = "amonet-v1.1.0-twrp"
    AMONET_V2_BOOTED = "amonet-v2-booted"
    AMONET_V2_FASTBOOT = "amonet-v2-fastboot"
    AMONET_V2_TWRP = "amonet-v2-twrp"
    AMONET_V2_TWRP_V1_1_0_TABLE = "amonet-v2-twrp-v1.1.0-table"
    BOOTED = "booted"
    EMOS = "emos"
    NONE = "none"
    NO_SYSTEM = "no-system"
    ROOTED = "rooted"
    STARTING = "starting"
    STOCK_BOOTED = "stock-booted"
    STOCK_FASTBOOT = "stock-fastboot"
    STOCK_FIREOS5_FASTBOOT = "stock-fireos5-fastboot"
