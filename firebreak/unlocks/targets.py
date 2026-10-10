from __future__ import annotations

from firebreak.cache import Download
from firebreak.devices import State
from firebreak.plugin import FireOs5, FireOs6, Target
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import AMONET_BISCUIT_V1_1_0_BBOE
from firebreak.unlocks.amonet_biscuit_v2_0_0 import AMONET_BISCUIT_V2_0_0

FIREOS = Download(
    name="update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
    sha256="6ababc517529938f0d1e836c3410a91df19683ae62d7fca9e2ca57320d5d2faa",
    url="https://d1s31zyz7dcc2d.cloudfront.net/47a1457e0802980eb32f63cd3ce355c0/"
    "update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
)
TARGETS = {
    target.name: target
    for target in (
        Target(
            goal=State.STOCK_BOOTED,
            installs=FireOs6(build=None),
            name="stock",
            unlock=None,
        ),
        Target(
            goal=State.ROOTED_AMONET_V1_1_0,
            installs=FireOs5(package=FIREOS),
            name=AMONET_BISCUIT_V1_1_0.name,
            unlock=AMONET_BISCUIT_V1_1_0,
        ),
        Target(
            goal=State.ROOTED_AMONET_V1_1_0_BBOE,
            installs=FireOs5(package=FIREOS),
            name=AMONET_BISCUIT_V1_1_0_BBOE.name,
            unlock=AMONET_BISCUIT_V1_1_0_BBOE,
        ),
        Target(
            goal=State.AMONET_V2_0_0_BOOTED,
            installs=FireOs6(build="8146"),
            name=AMONET_BISCUIT_V2_0_0.name,
            unlock=AMONET_BISCUIT_V2_0_0,
        ),
    )
}
