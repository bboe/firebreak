from __future__ import annotations

import dataclasses
import enum
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    from firebreak.cache import Download
    from firebreak.plan import Action

BOOT0 = "boot0"


@dataclasses.dataclass(frozen=True)
class ClearBoot0Header:
    label: str = "clear the preloader header (boot0)"


@dataclasses.dataclass(frozen=True)
class Device:
    features: frozenset[Feature]
    name: str
    layouts: tuple[Layout, ...] = ()


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
    goal: enum.Enum
    installs: FireOs5 | FireOs6
    name: str
    unlock: Unlock | None


@dataclasses.dataclass(frozen=True)
class Unlock:
    device: Device
    family: str
    layout: Layout
    plan: tuple[Step, ...]
    requires: frozenset[Feature]
    source: Download
    version: str
    files: dict[str, Download] = dataclasses.field(default_factory=dict)

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


Step = Union[
    ClearBoot0Header,
    FastbootFlash,
    ForceFastboot,
    Reboot,
    Repartition,
    ResetBcb,
    Write,
    ZeroRpmb,
]
