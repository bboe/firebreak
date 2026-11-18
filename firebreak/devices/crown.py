from __future__ import annotations

from firebreak.cache import Download
from firebreak.devices.authors import RORTIZ2
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    Device,
    DeviceConfig,
    FastbootFlash,
    Feature,
    ForceFastboot,
    Reboot,
    Unlock,
    Write,
    ZeroRpmb,
)

CROWN = Device(
    features=frozenset({Feature.BOOT0, Feature.RPMB}),
    models=frozenset({"AEOCW"}),
    name="crown",
    product="CROWN",
    thread="https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-show-8-1st-gen-2019-crown.4766687/",
    title="Echo Show 8 (1st Generation)",
    twrp_models=frozenset({"Echo Show 8"}),
)
CONFIG = DeviceConfig(device=CROWN)
SOURCE = Download(
    browser=True,
    directory="crown-v2.0.1",
    mirror=True,
    name="amonet-crown-v2.0.1.zip",
    sha256="5db974c321ae2f4586f7c51c95b7bdffb61ef85bde05ce7e62f78196a984c24f",
    size=44233517,
    url="https://xdaforums.com/attachments/amonet-crown-v2-0-1-zip.6373841/",
)
AMONET_V2_0_1 = Unlock(
    author=RORTIZ2,
    device=CROWN,
    family="amonet",
    plan=(
        ClearBoot0Header(),
        ZeroRpmb(expect=b"AMZN"),
        Write(image="bin/tz.img", label="write the TEE", target="tee2"),
        Write(image="bin/lk.bin", label="write the bootloader", target="lk"),
        Write(image="bin/crown-kaeru.bin", label="write kaeru", target="expdb"),
        Write(
            image="bin/tee-payload.bin", label="write the TEE payload", target="tee1"
        ),
        Write(
            image="bin/preloader.img",
            label="write the preloader",
            target=BOOT0,
            unrecoverable=True,
        ),
        ForceFastboot(target="MISC"),
        Reboot(),
        FastbootFlash(image="bin/twrp.img", label="write TWRP", target="recovery"),
        FastbootFlash(image="bin/twrp.img", label="write TWRP", target="swdl"),
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.BOOT0, Feature.RPMB}),
    source=SOURCE,
    version="2.0.1",
)
