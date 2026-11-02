from __future__ import annotations

from typing import TYPE_CHECKING

from firebreak.cache import Download
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    Device,
    FastbootFlash,
    Feature,
    ForceFastboot,
    Reboot,
    ResetBcb,
    Unlock,
    Write,
    ZeroRpmb,
)

if TYPE_CHECKING:
    from firebreak.plugin import Target
    from firebreak.targets import Deprecated

BOOTROM_UNLOCK = None
BUILDS: dict[str, Download] = {}
DEFAULT_BUILD = None
DEFAULT_TARGET = None
DONUT = Device(
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    models=frozenset({"AEODN"}),
    name="donut",
    product="DONUT",
    title="Echo Dot (3rd Generation)",
)
FASTBRICK = None
FIREOS5_BUILDS: frozenset[str] = frozenset()
FIREOS5_CHAIN = None
LK_VALUES = frozenset({
    "0d18cf4-20181206_233555",
    "6f7225e-20230407_013816",
})
SOURCE = Download(
    browser=True,
    directory="donut-v1.0.0",
    mirror=True,
    name="kamakiri-donut-v1.0.0.zip",
    root="kamakiri",
    sha256="4d2bb52eaf661f6616aa4268584d44cf9155c1328c34bfcba01a6558f942b738",
    size=23442578,
    url="https://xdaforums.com/attachments/kamakiri-donut-v1-0-0-zip.6384586/",
)
KAMAKIRI_V1_0_0 = Unlock(
    device=DONUT,
    family="kamakiri",
    plan=(
        ClearBoot0Header(),
        ZeroRpmb(expect=b"AMZN"),
        ResetBcb(target="misc"),
        Write(image="bin/tee-donut.bin", label="write the TEE", target="tee2"),
        Write(image="bin/lk-donut.bin", label="write the bootloader", target="lk_a"),
        Write(image="bin/lk-donut.bin", label="write the bootloader", target="lk_b"),
        Write(image="bin/kaeru-donut.bin", label="write kaeru", target="expdb"),
        Write(
            image="bin/tee-donut-payload.bin",
            label="write the TEE payload",
            target="tee1",
        ),
        Write(
            image="bin/preloader-donut.bin",
            label="write the preloader",
            target=BOOT0,
            unrecoverable=True,
        ),
        ForceFastboot(target="misc"),
        Reboot(label="restarting into kamakiri's fastboot"),
        FastbootFlash(
            image="bin/twrp-donut.img", label="write TWRP", target="recovery"
        ),
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=SOURCE,
    version="1.0.0",
)
TARGETS: tuple[Target, ...] = ()
WAS_CALLED: dict[str, Deprecated] = {}
