from __future__ import annotations

from firebreak.sizes import padded


def test_padded_leaves_a_whole_multiple_alone() -> None:
    assert padded(length=512, unit=512) == 512
    assert padded(length=513, unit=512) == 1024


def test_padded_rounds_a_length_up_to_a_whole_unit() -> None:
    assert [padded(length=length, unit=4) for length in range(9)] == [
        0,
        4,
        4,
        4,
        4,
        8,
        8,
        8,
        8,
    ]
