from __future__ import annotations

from firebreak.devices import BISCUIT, DEFAULTS, FASTBRICKS, TARGETS
from firebreak.devices.biscuit import (
    BUILDS,
    UNLOCK_TO_FIREOS5,
    UNLOCK_TO_FIREOS6,
)
from firebreak.plugin import FireOs5, FireOs6
from firebreak.states import State


def test_each_device_s_default_is_one_of_its_targets() -> None:
    assert set(DEFAULTS) <= set(TARGETS)
    assert all(DEFAULTS[device] in TARGETS[device] for device in DEFAULTS)


def test_each_device_with_a_target_names_the_unlock_its_fastbricks_are_in() -> None:
    assert set(TARGETS) <= set(FASTBRICKS)
    assert all(FASTBRICKS[device].device == device for device in FASTBRICKS)


def test_each_target_is_named_by_its_key_and_is_for_its_device() -> None:
    assert all(
        target.device == device
        and target.name == name
        and (target.unlock is None or target.unlock.device == device)
        for device, targets in TARGETS.items()
        for name, target in targets.items()
    )


def test_each_target_names_its_goal_its_install_and_its_unlock() -> None:
    assert {
        name: (target.goal, target.installs, target.unlock)
        for name, target in TARGETS[BISCUIT].items()
    } == {
        "fireos5": (
            State.AMONET_FIREOS5_BBOE_BOOTED,
            FireOs5(package=BUILDS["5.5.5.4"]),
            UNLOCK_TO_FIREOS5,
        ),
        "fireos6": (
            State.AMONET_BOOTED,
            FireOs6(build="8149"),
            UNLOCK_TO_FIREOS6,
        ),
        "stock": (State.STOCK_BOOTED, FireOs6(build=None), None),
    }
