from __future__ import annotations

from firebreak.devices import BISCUIT, State
from firebreak.plugin import FireOs5, FireOs6, Target
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import AMONET_BISCUIT_V1_1_0_BBOE
from firebreak.unlocks.amonet_biscuit_v2_0_0 import AMONET_BISCUIT_V2_0_0
from firebreak.updates import FIREOS

TARGETS = {
    target.name: target
    for target in (
        Target(
            device=BISCUIT,
            goal=State.STOCK_BOOTED,
            installs=FireOs6(build=None),
            name="stock",
            unlock=None,
        ),
        Target(
            device=BISCUIT,
            goal=State.AMONET_V1_1_0_BOOTED,
            installs=FireOs5(package=FIREOS),
            name=AMONET_BISCUIT_V1_1_0.name,
            unlock=AMONET_BISCUIT_V1_1_0,
        ),
        Target(
            device=BISCUIT,
            goal=State.AMONET_V1_1_0_BBOE_BOOTED,
            installs=FireOs5(package=FIREOS),
            name=AMONET_BISCUIT_V1_1_0_BBOE.name,
            unlock=AMONET_BISCUIT_V1_1_0_BBOE,
        ),
        Target(
            device=BISCUIT,
            goal=State.AMONET_V2_0_0_BOOTED,
            installs=FireOs6(build="8146"),
            name=AMONET_BISCUIT_V2_0_0.name,
            unlock=AMONET_BISCUIT_V2_0_0,
        ),
    )
}
