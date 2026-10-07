from __future__ import annotations

import pytest
from test_gpt import DISK, OTHERS, raw

from firebreak.android import gpt
from firebreak.unlocks import amonet_biscuit_v1_1_0 as amonet


def test_shuffled_gpt_fails() -> None:
    identifiers = {"boot_a": b"A" * 16, "boot_b": b"B" * 16}
    stock = [*OTHERS, "boot_a", "boot_b", "userdata"]
    for names, align, sectors, match in (
        ([*OTHERS, "userdata", "boot_a", "boot_b"], 16, 100, "is boot_b, not userdata"),
        ([*OTHERS, "boot_a", "spare", "userdata"], 16, 100, "has no boot_b"),
        ([*OTHERS, "boot_a", "boot_b_x", "boot_b", "userdata"], 16, 100, "boot_b_x"),
        (stock, 16, 500, "cannot give up room for boot_a, boot_b"),
    ):
        with pytest.raises(expected_exception=ValueError, match=match):
            amonet.shuffled_gpt(
                align=align,
                identifiers=identifiers,
                raw=raw(names=names),
                sectors=sectors,
            )
    with pytest.raises(expected_exception=ValueError, match="not intact"):
        amonet.shuffled_gpt(
            align=16,
            identifiers=identifiers,
            raw=b"M" * 512 + b"X" * 512 + bytes(16384),
            sectors=100,
        )


def test_shuffled_gpt_makes_room_at_the_end_of_userdata() -> None:
    original = raw(names=[*OTHERS, "boot_a", "boot_b", "userdata"])
    table = amonet.shuffled_gpt(
        align=16,
        identifiers={"boot_a": b"A" * 16, "boot_b": b"B" * 16},
        raw=original,
        sectors=100,
    )
    primary, backup, parts = table.primary, table.backup, table.partitions
    assert primary[:512] == b"M" * 512
    assert gpt.gpt_intact(entries=primary[1024:], header=primary[512:1024])
    assert gpt.gpt_intact(entries=backup[:16384], header=backup[16384:])
    assert table.backup_sector == DISK - 33
    assert list(parts) == [
        *OTHERS,
        "boot_a_x",
        "boot_b_x",
        "userdata",
        "boot_a",
        "boot_b",
    ]
    assert parts["boot_a_x"] == gpt.Partition(first=1334, number=14, sectors=100)
    assert parts["userdata"] == gpt.Partition(first=1534, number=16, sectors=794)
    assert parts["boot_a"] == gpt.Partition(first=2328, number=17, sectors=100)
    assert parts["boot_b"] == gpt.Partition(first=2428, number=18, sectors=100)
    entries = primary[1024:]
    assert entries[16 * 128 : 16 * 128 + 32] == b"T" * 16 + b"A" * 16
    assert entries[17 * 128 : 17 * 128 + 32] == b"T" * 16 + b"B" * 16
    userdata = entries[15 * 128 : 16 * 128]
    for added in (entries[16 * 128 : 17 * 128], entries[17 * 128 : 18 * 128]):
        assert added[:16] == userdata[:16]
        assert added[48:56] == userdata[48:56]
    assert gpt.stock_gpt(raw=primary) == gpt.stock_gpt(raw=original)
