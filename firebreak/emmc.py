from __future__ import annotations

import enum
from typing import Protocol

RPMB_SIZE = 0x100


class Emmc(Protocol):
    maximum_blocks: int

    def read_block(self, *, index: int) -> bytes: ...

    def read_blocks(self, *, count: int, index: int) -> bytes: ...

    def read_rpmb(self) -> bytes: ...

    def reboot(self) -> None: ...

    def switch_partition(self, *, partition: int) -> None: ...

    def write_blocks(self, *, data: bytes, index: int) -> None: ...

    def write_rpmb(self, *, data: bytes) -> None: ...


class EmmcArea(enum.IntEnum):
    USER = 0
    BOOT0 = 1
