from __future__ import annotations

import re
from typing import TYPE_CHECKING

from firebreak.devices import biscuit, crown, radar
from firebreak.devices.biscuit import BISCUIT
from firebreak.devices.crown import CROWN
from firebreak.devices.radar import RADAR

if TYPE_CHECKING:
    from firebreak.cache import Download
    from firebreak.plugin import Device, Target, Unlock
    from firebreak.targets import Deprecated

BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
LITTLE_KERNEL_DESCRIPTION = re.compile(pattern=r"[0-9a-f]{7}-\d{8}_\d{6}")
SUPPORTED = ((BISCUIT, biscuit), (CROWN, crown), (RADAR, radar))
BOOTROM_UNLOCKS: dict[Device, Unlock] = {
    device: module.BOOTROM_UNLOCK
    for device, module in SUPPORTED
    if module.BOOTROM_UNLOCK is not None
}
BUILDS: dict[Device, dict[str, Download]] = {
    device: module.BUILDS for device, module in SUPPORTED if module.BUILDS
}
DEFAULTS: dict[Device, str] = {
    device: module.DEFAULT_TARGET
    for device, module in SUPPORTED
    if module.DEFAULT_TARGET is not None
}
DEFAULT_BUILDS: dict[Device, str] = {
    device: module.DEFAULT_BUILD for device, module in SUPPORTED if module.BUILDS
}
DEPRECATED: dict[str, Deprecated] = {
    name: was for _, module in SUPPORTED for name, was in module.WAS_CALLED.items()
}
DEVICES = tuple(device for device, _ in SUPPORTED)
FASTBRICKS: dict[Device, Unlock] = {
    device: module.FASTBRICK
    for device, module in SUPPORTED
    if module.FASTBRICK is not None
}
LK_VALUES: dict[Device, frozenset[str]] = {
    device: module.LK_VALUES for device, module in SUPPORTED
}
TARGETS: dict[Device, dict[str, Target]] = {
    device: {target.name: target for target in module.TARGETS}
    for device, module in SUPPORTED
    if module.TARGETS
}
