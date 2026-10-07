from __future__ import annotations

from firebreak.plugin import Device, Feature

BISCUIT = Device(
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    name="biscuit",
)
