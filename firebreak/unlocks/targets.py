from __future__ import annotations

import typing

from firebreak.devices import BISCUIT, State
from firebreak.plugin import Device, FireOs5, FireOs6, Target
from firebreak.unlocks import amonet_biscuit_v2_0_1
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import (
    AMONET_BISCUIT_V1_1_0_BBOE,
    TWRP_VERSION,
)
from firebreak.updates import BUILDS, DEFAULT_BUILD

DEFAULTS = {BISCUIT: "fireos6"}
FIREOS5 = "fireos5"
FIREOS6 = "fireos6"
FIREOS6_BUILD = "8146"
REMOVED_IN = "1.0"


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
                goal=State.AMONET_V1_1_0_BBOE_BOOTED,
                installs=FireOs5(package=BUILDS["5.5.5.4"]),
                name=FIREOS5,
                summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP"
                f" {TWRP_VERSION}.",
                unlock=AMONET_BISCUIT_V1_1_0_BBOE,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V2_BOOTED,
                installs=FireOs6(build=FIREOS6_BUILD),
                name=FIREOS6,
                summary=f"rooted Fire OS 6 {FIREOS6_BUILD} on amonet v2.0.1,"
                f" with TWRP {amonet_biscuit_v2_0_1.TWRP_VERSION}.",
                unlock=amonet_biscuit_v2_0_1.AMONET_BISCUIT_V2_0_1,
            ),
        )
    }
}


class Deprecated(typing.NamedTuple):
    device: Device
    name: str
    note: str = ""


DEPRECATED = {
    "amonet-biscuit-v1.1.0": Deprecated(
        device=BISCUIT,
        name=FIREOS5,
        note=f"It now installs TWRP {TWRP_VERSION} rather than amonet's own"
        " TWRP 3.2.3.",
    ),
    "amonet-biscuit-v1.1.0-bboe": Deprecated(device=BISCUIT, name=FIREOS5),
    "amonet-biscuit-v2.0.0": Deprecated(
        device=BISCUIT,
        name=FIREOS6,
        note="It now writes amonet v2.0.1, whose kaeru boots the active slot.",
    ),
}
