from __future__ import annotations


def padded(*, length: int, unit: int) -> int:
    return length + -length % unit
