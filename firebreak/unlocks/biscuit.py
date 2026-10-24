from __future__ import annotations

import dataclasses

from firebreak.cache import Download
from firebreak.devices import BISCUIT, BOOT_MOVED_LAYOUT, STOCK_LAYOUT
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    FastbootFlash,
    Feature,
    ForceFastboot,
    Reboot,
    Repartition,
    ResetBcb,
    Unlock,
    Write,
    ZeroRpmb,
)

BBOE_TWRP_VERSION = "3.7.0_9-bboe2"
BBOE_RECOVERY = Download(
    name=f"twrp-{BBOE_TWRP_VERSION}-biscuit.img",
    sha256="f59052713a6580a1477490b2f9cad80e9b31d22408861b18fd442129a71f2ad9",
    size=13953024,
    url="https://github.com/bboe/twrp_device_amazon_echo-mt8163/releases/download/"
    f"v{BBOE_TWRP_VERSION}/twrp-v{BBOE_TWRP_VERSION}-biscuit.img",
)
PAYLOAD_SEEK = 223207


V1_1_0_FLASH_RECOVERY = FastbootFlash(
    image="bin/twrp.img", label="write TWRP", target="recovery"
)


V1_1_0_SOURCE = Download(
    browser=True,
    directory="v1",
    mirror=True,
    name="amonet-biscuit-v1.1.0.zip",
    sha256="bd4d3a18b6b6e9ff6e49a4739159a81020673202795cb3959f7c9ff24351b663",
    size=19233351,
    url="https://xdaforums.com/attachments/amonet-biscuit-v1-1-0-zip.6331296/",
)
AMONET_BISCUIT_V1_1_0 = Unlock(
    device=BISCUIT,
    family="amonet",
    layout=BOOT_MOVED_LAYOUT,
    plan=(
        ClearBoot0Header(),
        Repartition(),
        ZeroRpmb(expect=b"AMZN"),
        Write(image="bin/boot.hdr", label="inject boot_a", target="boot_a"),
        Write(
            image="bin/boot.payload",
            label="inject boot_a",
            sector_offset=PAYLOAD_SEEK,
            target="boot_a",
        ),
        Write(image="bin/boot.hdr", label="inject boot_b", target="boot_b"),
        Write(
            image="bin/boot.payload",
            label="inject boot_b",
            sector_offset=PAYLOAD_SEEK,
            target="boot_b",
        ),
        Write(image="bin/tz.img", label="write the TEE", target="tee1"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_a"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk_b"),
        ForceFastboot(target="expdb"),
        ResetBcb(target="misc"),
        Write(
            image="bin/preloader.img",
            label="write the preloader",
            target=BOOT0,
            unrecoverable=True,
        ),
        Reboot(),
        FastbootFlash(image="bin/tz.img", label="write the TEE", target="tee2"),
        V1_1_0_FLASH_RECOVERY,
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=V1_1_0_SOURCE,
    version="1.1.0",
)
AMONET_BISCUIT_V1_1_0_BBOE = dataclasses.replace(
    AMONET_BISCUIT_V1_1_0,
    files={"twrp": BBOE_RECOVERY},
    plan=tuple(
        FastbootFlash(
            image="twrp", label="write TWRP " + BBOE_TWRP_VERSION, target="recovery"
        )
        if step == V1_1_0_FLASH_RECOVERY
        else step
        for step in AMONET_BISCUIT_V1_1_0.plan
    ),
    version="1.1.0-bboe",
)


V2_0_1_SOURCE = Download(
    browser=True,
    directory="v2.0.1-2",
    mirror=True,
    name="amonet-biscuit-v2.0.1.zip",
    sha256="ea9cada067783a0d83f025bdd669fd5689148f555054475c7c70c634c542f3b5",
    size=73550504,
    url="https://xdaforums.com/attachments/amonet-biscuit-v2-0-1-zip.6400450/",
)
V2_0_1_TWRP_VERSION = "3.7.0"
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
    source=V2_0_1_SOURCE,
    version="2.0.1",
)
