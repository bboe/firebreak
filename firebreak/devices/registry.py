from __future__ import annotations

import re
from typing import TYPE_CHECKING

from firebreak.devices import biscuit, crown, donut, radar

if TYPE_CHECKING:
    from firebreak.cache import Download
    from firebreak.plugin import Device, FireOs5Chain, Target, Unlock

BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
LITTLE_KERNEL_DESCRIPTION = re.compile(pattern=r"[0-9a-f]{7,8}-\d{8}_\d{6}")
SUPPORTED = (biscuit.CONFIG, crown.CONFIG, donut.CONFIG, radar.CONFIG)
ADB_OFF_BUILDS: dict[Device, frozenset[str]] = {
    config.device: config.adb_off_builds for config in SUPPORTED
}
BOOTROM_UNLOCKS: dict[Device, Unlock] = {
    config.device: config.bootrom_unlock
    for config in SUPPORTED
    if config.bootrom_unlock is not None
}
BUILDS: dict[Device, dict[str, Download]] = {
    config.device: config.builds for config in SUPPORTED if config.builds
}
DEFAULTS: dict[Device, str] = {
    config.device: config.default_target
    for config in SUPPORTED
    if config.default_target is not None
}
DEFAULT_BUILDS: dict[Device, str] = {
    config.device: config.default_build
    for config in SUPPORTED
    if config.builds and config.default_build is not None
}
DEVICES = tuple(config.device for config in SUPPORTED)
FASTBRICKS: dict[Device, Unlock] = {
    config.device: config.fastbrick
    for config in SUPPORTED
    if config.fastbrick is not None
}
FIREOS5_BUILDS: dict[Device, frozenset[str]] = {
    config.device: config.fireos5_builds for config in SUPPORTED
}
FIREOS5_CHAINS: dict[Device, FireOs5Chain] = {
    config.device: config.fireos5_chain
    for config in SUPPORTED
    if config.fireos5_chain is not None
}
KAMAKIRI_UNLOCKS: dict[Device, Unlock] = {
    config.device: config.kamakiri_unlock
    for config in SUPPORTED
    if config.kamakiri_unlock is not None
}
LK_VALUES: dict[Device, frozenset[str]] = {
    config.device: config.lk_values for config in SUPPORTED
}
TARGETS: dict[Device, dict[str, Target]] = {
    config.device: {target.name: target for target in config.targets}
    for config in SUPPORTED
    if config.targets
}
