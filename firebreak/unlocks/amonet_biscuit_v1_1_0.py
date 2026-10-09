from __future__ import annotations

from firebreak.cache import Download
from firebreak.devices import BISCUIT, BOOT_MOVED_LAYOUT
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

FLASH_RECOVERY = FastbootFlash(
    image="bin/twrp.img", label="write TWRP", target="recovery"
)
PAYLOAD_SEEK = 223207
SOURCE = Download(
    directory="v1",
    name="amonet-biscuit-v1.1.0.zip",
    sha256="bd4d3a18b6b6e9ff6e49a4739159a81020673202795cb3959f7c9ff24351b663",
    url="https://github.com/hkfuertes/amazon_device_biscuit/releases/download/none"
    "/amonet-biscuit-v1.1.0.zip",
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
        FLASH_RECOVERY,
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=SOURCE,
    version="1.1.0",
)
