from __future__ import annotations

import typing

from firebreak.devices import BISCUIT, State
from firebreak.plugin import Device, FireOs5, FireOs6, Target
from firebreak.unlocks.biscuit import (
    BBOE_TWRP_VERSION,
    UNLOCK_TO_FIREOS5,
    UNLOCK_TO_FIREOS6,
    V2_0_1_TWRP_VERSION,
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
                f" {BBOE_TWRP_VERSION}.",
                unlock=UNLOCK_TO_FIREOS5,
            ),
            Target(
                device=BISCUIT,
                goal=State.AMONET_V2_BOOTED,
                installs=FireOs6(build=FIREOS6_BUILD),
                name=FIREOS6,
                summary=f"rooted Fire OS 6 {FIREOS6_BUILD} on amonet v2.0.1,"
                f" with TWRP {V2_0_1_TWRP_VERSION}.",
                unlock=UNLOCK_TO_FIREOS6,
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
        note=f"It now installs TWRP {BBOE_TWRP_VERSION} rather than amonet's own"
        " TWRP 3.2.3.",
    ),
    "amonet-biscuit-v1.1.0-bboe": Deprecated(device=BISCUIT, name=FIREOS5),
    "amonet-biscuit-v2.0.0": Deprecated(
        device=BISCUIT,
        name=FIREOS6,
        note="It now writes amonet v2.0.1, whose kaeru boots the active slot.",
    ),
}
