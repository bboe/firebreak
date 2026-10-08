from __future__ import annotations

from firebreak import emmc


def test_areas_are_numbered_as_the_payload_switches_them() -> None:
    assert [(area.name, int(area)) for area in emmc.EmmcArea] == [
        ("USER", 0),
        ("BOOT0", 1),
    ]


def test_rpmb_carries_256_bytes() -> None:
    assert emmc.RPMB_SIZE == 0x100
