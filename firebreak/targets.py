from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from firebreak.plugin import Device

FIREOS5 = "fireos5"
FIREOS6 = "fireos6"
REMOVED_IN = "1.0"
STOCK = "stock"


class Deprecated(typing.NamedTuple):
    device: Device
    name: str
    note: str = ""
