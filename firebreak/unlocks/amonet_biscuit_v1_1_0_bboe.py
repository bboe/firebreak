from __future__ import annotations

import dataclasses

from firebreak.cache import Download
from firebreak.plugin import FastbootFlash
from firebreak.unlocks.amonet_biscuit_v1_1_0 import (
    AMONET_BISCUIT_V1_1_0,
    FLASH_RECOVERY,
)

TWRP_VERSION = "3.7.0_9-bboe2"
RECOVERY = Download(
    name=f"twrp-{TWRP_VERSION}-biscuit.img",
    sha256="f59052713a6580a1477490b2f9cad80e9b31d22408861b18fd442129a71f2ad9",
    size=13953024,
    url="https://github.com/bboe/twrp_device_amazon_echo-mt8163/releases/download/"
    f"v{TWRP_VERSION}/twrp-v{TWRP_VERSION}-biscuit.img",
)
AMONET_BISCUIT_V1_1_0_BBOE = dataclasses.replace(
    AMONET_BISCUIT_V1_1_0,
    files={"twrp": RECOVERY},
    plan=tuple(
        FastbootFlash(
            image="twrp", label="write TWRP " + TWRP_VERSION, target="recovery"
        )
        if step == FLASH_RECOVERY
        else step
        for step in AMONET_BISCUIT_V1_1_0.plan
    ),
    version="1.1.0-bboe",
)
