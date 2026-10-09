from __future__ import annotations

import pytest
from test_gpt import DISK, LAST_USABLE, OTHERS, raw

from firebreak import layouts
from firebreak.android import gpt


def test_a_layout_with_only_some_targets_moved_is_refused() -> None:
    layout = layouts.BootMovedLayout(
        align=16, sectors=100, targets=("boot_a", "boot_b")
    )
    names = [*OTHERS, "boot_a_x", "boot_b", "userdata", "boot_a"]
    with pytest.raises(ValueError, match="has boot_a_x but not boot_b_x"):
        layout.describes(raw=raw(names=names))
    assert (
        layout.describes(raw=raw(names=[*OTHERS, "boot_a", "boot_b", "userdata"]))
        is False
    )


def test_a_stock_layout_describes_a_table_with_its_partition_count() -> None:
    layout = layouts.StockLayout(partitions=16)
    stock = raw(names=[*OTHERS, "boot_a", "boot_b", "userdata"])
    assert layout.describes(raw=stock) is True
    assert layout.describes(raw=raw(names=[*OTHERS, "userdata"])) is False
    more = raw(names=[*OTHERS, "boot_a", "boot_b", "userdata", "spare", "extra"])
    assert layout.describes(raw=more) is False
    assert layout.apply(raw=stock) == layout.revert(raw=stock) == (stock, ())


def test_a_table_with_half_its_shuffle_undone_is_refused() -> None:
    layout = layouts.BootMovedLayout(
        align=16, sectors=100, targets=("boot_a", "boot_b")
    )
    with pytest.raises(expected_exception=ValueError, match="no boot_b_x"):
        layout.revert(
            raw=raw(
                names=[*OTHERS, "boot_a_x", "boot_b", "userdata", "boot_a", "boot_b"]
            )
        )


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
            layouts.shuffled_gpt(
                align=align,
                identifiers=identifiers,
                raw=raw(names=names),
                sectors=sectors,
            )
    with pytest.raises(expected_exception=ValueError, match="not intact"):
        layouts.shuffled_gpt(
            align=16,
            identifiers=identifiers,
            raw=b"M" * 512 + b"X" * 512 + bytes(16384),
            sectors=100,
        )


def test_shuffled_gpt_makes_room_at_the_end_of_userdata() -> None:
    original = raw(names=[*OTHERS, "boot_a", "boot_b", "userdata"])
    table = layouts.shuffled_gpt(
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


def test_unshuffled_gpt_fails() -> None:
    targets = ("boot_a", "boot_b")
    for names, match in (
        (
            [*OTHERS, "boot_a", "boot_b", "userdata"],
            "are boot_a, boot_b, userdata, not",
        ),
        ([*OTHERS, "boot_a_x", "spare", "userdata", "boot_a", "boot_b"], "no boot_b_x"),
        (
            [*OTHERS, "boot_a_x", "boot_b_x", "userdata", "boot_b", "boot_a"],
            "are userdata, boot_b, boot_a, not",
        ),
        (["userdata"], "are userdata, not userdata, boot_a, boot_b"),
        (["userdata", "boot_b"], "are userdata, boot_b, not userdata, boot_a"),
    ):
        with pytest.raises(expected_exception=ValueError, match=match):
            layouts.unshuffled_gpt(raw=raw(names=names), targets=targets)
    with pytest.raises(expected_exception=ValueError, match="not intact"):
        layouts.unshuffled_gpt(
            raw=b"M" * 512 + b"X" * 512 + bytes(16384), targets=targets
        )


def test_unshuffled_gpt_undoes_shuffled_gpt() -> None:
    original = raw(names=[*OTHERS, "boot_a", "boot_b", "userdata"])
    shuffled = layouts.shuffled_gpt(
        align=16,
        identifiers={"boot_a": b"A" * 16, "boot_b": b"B" * 16},
        raw=original,
        sectors=100,
    )
    table = layouts.unshuffled_gpt(raw=shuffled.primary, targets=("boot_a", "boot_b"))
    stock = gpt.partition_map(entries=original[1024:])
    stock["userdata"] = gpt.Partition(
        first=1534, number=16, sectors=LAST_USABLE - 1534 + 1
    )
    assert table.partitions == stock
    assert table.primary[:512] == b"M" * 512
    assert gpt.gpt_intact(entries=table.backup[:16384], header=table.backup[16384:])
