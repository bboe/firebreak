from __future__ import annotations

import dataclasses
import enum
import hashlib
from typing import TYPE_CHECKING, Protocol

from firebreak.states import State

if TYPE_CHECKING:
    from collections.abc import Callable

    from firebreak.cache import Download
    from firebreak.plan import Action

BOOT0 = "boot0"


@dataclasses.dataclass(frozen=True)
class Author:
    home: str
    name: str
    short_name: str
    support: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ClearBoot0Header:
    label: str = "clear the preloader header (boot0)"


@dataclasses.dataclass(frozen=True)
class Device:
    features: frozenset[Feature]
    name: str
    product: str
    title: str
    device_type_id: str = ""
    fastboot_command: bytes = b""
    fastboot_mode: str = ""
    hardware_code: int | None = None
    layouts: tuple[Layout, ...] = ()
    models: frozenset[str] = frozenset()
    named_by_bootloader: bool = True
    recovery_command: bytes = b""
    short_gesture: str = ""
    thread: str = ""
    twrp_models: frozenset[str] = frozenset()
    unlock_keeps_misc: bool = False


@dataclasses.dataclass(frozen=True)
class DeviceConfig:
    device: Device
    adb_off_builds: frozenset[str] = frozenset()
    bootrom_unlock: Unlock | None = None
    builds: dict[str, Download] = dataclasses.field(default_factory=dict)
    default_build: str | None = None
    default_target: str | None = None
    fastbrick: Unlock | None = None
    fireos5_builds: frozenset[str] = frozenset()
    fireos5_chain: FireOs5Chain | None = None
    kamakiri_unlock: Unlock | None = None
    lk_values: frozenset[str] = frozenset()
    targets: tuple[Target, ...] = ()


@dataclasses.dataclass(frozen=True)
class FastbootFlash:
    image: str
    target: str
    label: str = "flash over fastboot"


class Feature(enum.Enum):
    AB_SLOTS = "ab-slots"
    BOOT0 = "boot0"
    RPMB = "rpmb"


@dataclasses.dataclass(frozen=True)
class FireOs5:
    package: Download


@dataclasses.dataclass(frozen=True)
class FireOs5Chain:
    little_kernel: str
    recovery: Download
    twrp_version: str
    unlock: Unlock

    def booted(self, *, read: Callable[..., bytes]) -> State | None:
        data = read(size=self.recovery.size)
        if hashlib.sha256(data).hexdigest() != self.recovery.sha256:
            return None
        return State.AMONET_FIREOS5_BBOE_BOOTED

    def fastboot(self, *, little_kernel: str, unlocked: bool) -> State | None:
        if little_kernel != self.little_kernel:
            return None
        if unlocked:
            return State.AMONET_FIREOS5_FASTBOOT
        return State.STOCK_FIREOS5_FASTBOOT

    def twrp(self, *, little_kernel: str, version: str) -> State | None:
        if little_kernel != self.little_kernel:
            return None
        if version != self.twrp_version:
            return State.AMONET_FIREOS5_TWRP
        return State.AMONET_FIREOS5_BBOE_TWRP


@dataclasses.dataclass(frozen=True)
class FireOs6:
    build: str | None


@dataclasses.dataclass(frozen=True)
class ForceFastboot:
    target: str
    label: str = "force fastboot"


class Layout(Protocol):
    def apply(self, *, raw: bytes) -> tuple[bytes, tuple[Action, ...]]: ...

    def describes(self, *, raw: bytes) -> bool: ...

    def revert(self, *, raw: bytes) -> tuple[bytes, tuple[Action, ...]]: ...


@dataclasses.dataclass(frozen=True)
class PayloadCommand:
    command: int
    label: str
    settle: float = 0.0


@dataclasses.dataclass(frozen=True)
class Reboot:
    into: str | None = None
    label: str = "reboot"


@dataclasses.dataclass(frozen=True)
class Repartition:
    label: str = "repartition"


@dataclasses.dataclass(frozen=True)
class ResetBcb:
    target: str
    label: str = "reset the bootloader control block"


@dataclasses.dataclass(frozen=True)
class Target:
    device: Device
    goal: enum.Enum
    installs: FireOs5 | FireOs6
    name: str
    summary: str
    unlock: Unlock | None


@dataclasses.dataclass(frozen=True)
class Unlock:
    device: Device
    family: str
    plan: tuple[Step, ...]
    requires: frozenset[Feature]
    source: Download
    version: str
    author: Author | None = None
    fastbricks: dict[str, str] = dataclasses.field(default_factory=dict)
    files: dict[str, Download] = dataclasses.field(default_factory=dict)
    layout: Layout | None = None
    little_kernel: str = ""
    payloads: dict[str, Download] = dataclasses.field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.family}-{self.device.name}-v{self.version}"

    def unmet(self) -> frozenset[Feature]:
        return self.requires - self.device.features


@dataclasses.dataclass(frozen=True)
class Write:
    image: str
    target: str
    label: str = "write"
    sector_offset: int = 0
    unrecoverable: bool = False


@dataclasses.dataclass(frozen=True)
class ZeroRpmb:
    expect: bytes
    label: str = "zero the RPMB"


type Step = (
    ClearBoot0Header
    | FastbootFlash
    | ForceFastboot
    | PayloadCommand
    | Reboot
    | Repartition
    | ResetBcb
    | Write
    | ZeroRpmb
)
