from __future__ import annotations

from firebreak.devices import State
from firebreak.plugin import FireOs5, FireOs6
from firebreak.unlocks.amonet_biscuit_v1_1_0 import AMONET_BISCUIT_V1_1_0
from firebreak.unlocks.amonet_biscuit_v1_1_0_bboe import AMONET_BISCUIT_V1_1_0_BBOE
from firebreak.unlocks.amonet_biscuit_v2_0_0 import AMONET_BISCUIT_V2_0_0
from firebreak.unlocks.targets import FIREOS, TARGETS


def test_each_target_names_its_goal_its_install_and_its_unlock() -> None:
    assert {
        name: (target.goal, target.installs, target.unlock)
        for name, target in TARGETS.items()
    } == {
        "amonet-biscuit-v1.1.0": (
            State.ROOTED_AMONET_V1_1_0,
            FireOs5(package=FIREOS),
            AMONET_BISCUIT_V1_1_0,
        ),
        "amonet-biscuit-v1.1.0-bboe": (
            State.ROOTED_AMONET_V1_1_0_BBOE,
            FireOs5(package=FIREOS),
            AMONET_BISCUIT_V1_1_0_BBOE,
        ),
        "amonet-biscuit-v2.0.0": (
            State.AMONET_V2_0_0_BOOTED,
            FireOs6(build="8146"),
            AMONET_BISCUIT_V2_0_0,
        ),
        "stock": (State.STOCK_BOOTED, FireOs6(build=None), None),
    }
    assert all(target.name == name for name, target in TARGETS.items())
