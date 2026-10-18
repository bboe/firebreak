from __future__ import annotations

from firebreak.cache import Download
from firebreak.devices import BISCUIT, LK, STOCK_LAYOUT
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
    directory="v2",
    name="amonet-biscuit-v2.0.0.zip",
    sha256="98297293701082bc7272efe077f941c56fc7b6e1f27ef6f2e93b6e4c6fc7b62d",
    url="https://github.com/hkfuertes/amazon_device_biscuit/releases/download/none"
    "/amonet-biscuit-v2.0.0.zip",
)
WRITE_KAERU = Write(image="bin/biscuit-kaeru.bin", label="write kaeru", target="expdb")
AMONET_BISCUIT_V2_0_0 = Unlock(
    device=BISCUIT,
    family="amonet",
    fastbricks=dict.fromkeys(
        (LK.FIREOS6.value, LK.FIREOS6_4315.value), "bin/fastbrick-20221007.img"
    )
    | dict.fromkeys(
        (
            LK.FIREOS5.value,
            "0e1d0d9-20161018_220224",
            "a828f29-20210822_210511",
            "beb022a-20211202_231918",
        ),
        "bin/fastbrick.img",
    ),
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
    version="2.0.0",
)
