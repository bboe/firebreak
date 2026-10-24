from __future__ import annotations

from firebreak.cache import Download
from firebreak.devices import BISCUIT, STOCK_LAYOUT
from firebreak.plugin import (
    BOOT0,
    FastbootFlash,
    Feature,
    ForceFastboot,
    Reboot,
    Repartition,
    Unlock,
    Write,
    ZeroRpmb,
)

SOURCE = Download(
    browser=True,
    directory="v2.0.1",
    name="amonet-biscuit-v2.0.1.zip",
    sha256="93ec0d8816857406c9d53d11378256f055da2d8b658fea016d3114a8bd6b19b6",
    size=73189204,
    url="https://xdaforums.com/attachments/amonet-biscuit-v2-0-1-zip.6400139/",
)
WRITE_KAERU = Write(image="bin/biscuit-kaeru.bin", label="write kaeru", target="expdb")
AMONET_BISCUIT_V2_0_1 = Unlock(
    device=BISCUIT,
    family="amonet",
    layout=STOCK_LAYOUT,
    plan=(
        Repartition(),
        ZeroRpmb(expect=b"AMZN"),
        Write(image="bin/tz.img", label="write the TEE", target="tee2"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_a"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_b"),
        WRITE_KAERU,
        Write(
            image="bin/tee-payload.bin", label="write the TEE payload", target="tee1"
        ),
        Write(
            image="bin/preloader.img",
            label="write the preloader",
            target=BOOT0,
            unrecoverable=True,
        ),
        ForceFastboot(target="misc"),
        Reboot(),
        FastbootFlash(image="bin/twrp.img", label="write TWRP", target="recovery"),
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=SOURCE,
    version="2.0.1",
)
