from __future__ import annotations

from firebreak.devices import BISCUIT, RADAR, State
from firebreak.plugin import FireOs5, FireOs6, Target
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import (
    AMONET_BISCUIT_V1_1_0_BBOE,
    TWRP_VERSION,
)
from firebreak.unlocks.amonet_biscuit_v2_0_0 import AMONET_BISCUIT_V2_0_0
from firebreak.unlocks.amonet_radar_v1_0_0 import AMONET_RADAR_V1_0_0
from firebreak.updates import BUILDS, DEFAULT_BUILDS

AMONET_BISCUIT_V2_0_0_BUILD = "8146"
DEFAULTS = {
    BISCUIT: AMONET_BISCUIT_V1_1_0_BBOE.name,
    RADAR: AMONET_RADAR_V1_0_0.name,
}
FASTBRICKS = {BISCUIT: AMONET_BISCUIT_V2_0_0, RADAR: AMONET_RADAR_V1_0_0}
STOCK = "stock"
TARGETS = {
    BISCUIT: {
        target.name: target
        for target in (
            Target(
                device=BISCUIT,
                goal=State.STOCK_BOOTED,
                installs=FireOs6(build=None),
                name=STOCK,
                summary=f"Amazon's Fire OS BUILD, {DEFAULT_BUILDS[BISCUIT]} when"
                " left out, which erases the whole Dot.",
                unlock=None,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V1_1_0_BOOTED,
                installs=FireOs5(package=BUILDS[BISCUIT]["5.5.5.4"]),
                name=AMONET_BISCUIT_V1_1_0.name,
                summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with amonet"
                " v1.1.0's own TWRP 3.2.3.",
                unlock=AMONET_BISCUIT_V1_1_0,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V1_1_0_BBOE_BOOTED,
                installs=FireOs5(package=BUILDS[BISCUIT]["5.5.5.4"]),
                name=AMONET_BISCUIT_V1_1_0_BBOE.name,
                summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP"
                f" {TWRP_VERSION}.",
                unlock=AMONET_BISCUIT_V1_1_0_BBOE,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V2_0_0_BOOTED,
                installs=FireOs6(build=AMONET_BISCUIT_V2_0_0_BUILD),
                name=AMONET_BISCUIT_V2_0_0.name,
                summary="boot-root.zip's root adb on the Fire OS 6 already"
                " installed, which keeps the Dot's setup; with --reset, amonet"
                f" v2.0.0's own procedure: Fire OS 6 {AMONET_BISCUIT_V2_0_0_BUILD},"
                " with the Dot erased.",
                unlock=AMONET_BISCUIT_V2_0_0,
            ),
        )
    },
    RADAR: {
        target.name: target
        for target in (
            Target(
                device=RADAR,
                goal=State.STOCK_BOOTED,
                installs=FireOs6(build=None),
                name=STOCK,
                summary=f"Amazon's Fire OS {DEFAULT_BUILDS[RADAR]}, which erases"
                " the whole Echo.",
                unlock=None,
            ),
            Target(
                device=RADAR,
                goal=State.AMONET_V2_0_0_BOOTED,
                installs=FireOs6(build=DEFAULT_BUILDS[RADAR]),
                name=AMONET_RADAR_V1_0_0.name,
                summary="boot-root.zip's root adb on the Fire OS 6 already"
                " installed, which keeps the Echo's setup; with --reset,"
                " amonet-radar v1.0.0's own procedure: Fire OS 6"
                f" {DEFAULT_BUILDS[RADAR]}, with the Echo erased.",
                unlock=AMONET_RADAR_V1_0_0,
            ),
        )
    },
}
