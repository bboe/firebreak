from __future__ import annotations

from firebreak.devices import BISCUIT, State
from firebreak.plugin import FireOs5, FireOs6, Target
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import (
    AMONET_BISCUIT_V1_1_0_BBOE,
    TWRP_VERSION,
)
from firebreak.unlocks.amonet_biscuit_v2_0_0 import AMONET_BISCUIT_V2_0_0
from firebreak.updates import BUILDS, DEFAULT_BUILD

AMONET_BISCUIT_V2_0_0_BUILD = "8146"
DEFAULTS = {BISCUIT: AMONET_BISCUIT_V1_1_0_BBOE.name}
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
                summary=f"Amazon's Fire OS BUILD, {DEFAULT_BUILD} when left out,"
                " which erases the whole Dot.",
                unlock=None,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V1_1_0_BOOTED,
                installs=FireOs5(package=BUILDS["5.5.5.4"]),
                name=AMONET_BISCUIT_V1_1_0.name,
                summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with amonet"
                " v1.1.0's own TWRP 3.2.3.",
                unlock=AMONET_BISCUIT_V1_1_0,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V1_1_0_BBOE_BOOTED,
                installs=FireOs5(package=BUILDS["5.5.5.4"]),
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
                summary="amonet v2.0.0's own procedure: Fire OS 6"
                f" {AMONET_BISCUIT_V2_0_0_BUILD} with boot-root.zip's root adb.",
                unlock=AMONET_BISCUIT_V2_0_0,
            ),
        )
    }
}
