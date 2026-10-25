from __future__ import annotations

import dataclasses
import enum

from firebreak.cache import Download
from firebreak.layouts import BootMovedLayout, StockLayout
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    Device,
    FastbootFlash,
    Feature,
    FireOs5,
    FireOs6,
    ForceFastboot,
    Reboot,
    Repartition,
    ResetBcb,
    Target,
    Unlock,
    Write,
    ZeroRpmb,
)
from firebreak.states import State
from firebreak.targets import FIREOS5, FIREOS6, STOCK, Deprecated
from firebreak.updates import cdn_ota

BBOE_TWRP_VERSION = "3.7.0_9-bboe2"
BBOE_RECOVERY = Download(
    name=f"twrp-{BBOE_TWRP_VERSION}-biscuit.img",
    sha256="f59052713a6580a1477490b2f9cad80e9b31d22408861b18fd442129a71f2ad9",
    size=13953024,
    url="https://github.com/bboe/twrp_device_amazon_echo-mt8163/releases/download/"
    f"v{BBOE_TWRP_VERSION}/twrp-v{BBOE_TWRP_VERSION}-biscuit.img",
)
BOOTROM_BUILDS = frozenset({"5.5.0.3"})
BOOT_MOVED_LAYOUT = BootMovedLayout(
    align=0x400, sectors=0x37000, targets=("boot_a", "boot_b")
)
BUILDS = {
    "4315": cdn_ota(
        path="6277b5d592ff79ff4ca2c84082a88bbf/update-kindle-biscuit_puffin-NS6555_user_4315M_0008087722874.bin",
        sha256="c1ca33efd975cb8491ea9438eff95af559c632dd7ca75ff3b73facacce5f758a",
    ),
    "4405": cdn_ota(
        path="2e17a264c416806ff7d3d984e1b6fcb7/update-kindle-biscuit_puffin-NS6556_user_4405_0008289072516.bin",
        sha256="6839b0a1e5c4f6aa57f89ea7ca67c85aa69f8fe32e5ddc252764b0d96be5bf69",
    ),
    "5.5.0.3": cdn_ota(
        path="1b9718ec2da663bb299676df977055c9/update-kindle-full_biscuit-272.5.6.4_user_564196920.bin",
        sha256="5458cd2d49b4549310d17ea9fb390db0733a633df4187fcdccabc38a980f8bea",
    ),
    "5.5.3.1": cdn_ota(
        path="8811a0fc982bf3331dc54f5aec45d936/update-kindle-full_biscuit-272.6.4.1_user_641575220.bin",
        sha256="28bc050e4a2af79c9ca66e251de7bf04c42ce8d7934dd97673d3d04f5fa0917b",
    ),
    "5.5.4.6": cdn_ota(
        path="0cdf0a5782c43290ba9a598e1ede98e6/update-kindle-csm_biscuit-272.6.6.6_user_666694320.bin",
        sha256="f6ed07177d98930a84db271d036a8a0d2d82dfc0bfde93f96151143de1dc9026",
    ),
    "5.5.4.9": cdn_ota(
        path="60556d35239d902637f0fc503411b791/update-kindle-csm_biscuit-272.6.7.2_user_672720020.bin",
        sha256="ec6d1a694a46dcaee1ec8b1130131e994e99ab80547dc17dd79e504d23b4bedb",
    ),
    "5.5.5.0": cdn_ota(
        path="f4994d8b2b10442d42e07b8c5d996a91/update-kindle-csm_biscuit-272.6.7.3_user_673726720.bin",
        sha256="6bda9ebc976fc8c8a2dffdb88ab3c27ca0f73882c47812d9b90fe30d39bb6244",
    ),
    "5.5.5.4": cdn_ota(
        path="47a1457e0802980eb32f63cd3ce355c0/update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
        sha256="6ababc517529938f0d1e836c3410a91df19683ae62d7fca9e2ca57320d5d2faa",
    ),
    "5041": cdn_ota(
        path="b221e0c9947ee49842251cc89c7b74ce/update-kindle-biscuit_puffin-NS6505_user_5041_0008960323972.bin",
        sha256="80d98d3b57bc654d435b384f096dea46edd2b86e9f8adaaf91a7b0c3001e9716",
    ),
    "6302": cdn_ota(
        path="2025/4/13/06eb800d-de9a-4a1c-a5ea-25d297190fc7/update-kindle-biscuit_puffin-NS6466_user_6302_0011712110212.bin",
        sha256="6d395345b1d1db373f9d714172c2ac5de4b5dd3e52d1ed1c3f37c2f007537667",
    ),
    "8138": cdn_ota(
        path="2026/8/31/9314fd65-d6e4-4a1a-8089-9f90ea835c77/update-kindle-biscuit_puffin-NS65741_user_8138_0013222529668.bin",
        sha256="d2a61dd2af1d322e9ecfb4643670fbe416bc2442410f1aebe9748e2438f6d55f",
    ),
    "8142": cdn_ota(
        path="2026/9/9/b8de99f9-4a75-4513-b159-b44fd0316553/update-kindle-biscuit_puffin-NS65741_user_8142_0013222530692.bin",
        sha256="ed4ddb01cd53e38751bb6274ad1a8255043e0795843d6ac2d44cc2803b2179a0",
    ),
    "8146": cdn_ota(
        path="2026/9/17/566d9028-8c3d-45a2-b5a8-4c4439ba2126/update-kindle-biscuit_puffin-NS65741_user_8146_0013222531716.bin",
        sha256="90832e86498c5e803974c30359aea71c1129757be0ddc59d831a94b27f81487f",
    ),
    "8149": cdn_ota(
        path="2026/9/29/9a45cfba-a9ee-4f8f-ba00-fcbffd59e3f1/update-kindle-biscuit_puffin-NS65741_user_8149_0013222532484.bin",
        sha256="4e00fc6d6e2bcf5146e502c7d14e67d2ab47b43c3dcca4e1e9439d24730a6c0b",
    ),
    "8338": cdn_ota(
        path="2026/10/14/e5a2c4cb-7834-4c0f-95b1-301a3ab72194/update-kindle-biscuit_puffin-NS6575_user_8338_0013323244164.bin",
        sha256="c8ea0061e2d117d78c7f9a507dfd435505c324eac7a6ee03499276d9a982ccf0",
    ),
}
DEFAULT_BUILD = "8149"
DEFAULT_TARGET = FIREOS6
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green. A"
    " ring that stays solid blue can mean a bad USB connection: unplug, then"
    " try again or try another port."
)
FIREOS5_BUILDS = frozenset({
    "5.5.0.3",
    "5.5.3.1",
    "5.5.4.6",
    "5.5.4.9",
    "5.5.5.0",
    "5.5.5.4",
})
FIREOS6_BUILD = "8146"
FLASH_AMONET_TWRP = FastbootFlash(
    image="bin/twrp.img", label="write TWRP", target="recovery"
)
FLASH_BBOE_TWRP = FastbootFlash(
    image="twrp", label="write TWRP " + BBOE_TWRP_VERSION, target="recovery"
)
PAYLOAD_SEEK = 223207


STOCK_LAYOUT = StockLayout(partitions=16)
BISCUIT = Device(
    fastboot_mode=FASTBOOT_MODE,
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    layouts=(BOOT_MOVED_LAYOUT, STOCK_LAYOUT),
    models=frozenset({"AEOBC", "Echo Dot (2nd Gen)", "Echo Dot 2nd Gen"}),
    name="biscuit",
    product="BISCUIT",
    title="Echo Dot (2nd Generation)",
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
UNLOCK_TO_FIREOS5 = Unlock(
    device=BISCUIT,
    family="amonet",
    files={"twrp": BBOE_RECOVERY},
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
        FLASH_BBOE_TWRP,
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=V1_1_0_SOURCE,
    version="1.1.0-bboe",
)
UNLOCK_FROM_BOOTROM = dataclasses.replace(
    UNLOCK_TO_FIREOS5,
    files={},
    plan=tuple(
        FLASH_AMONET_TWRP if step == FLASH_BBOE_TWRP else step
        for step in UNLOCK_TO_FIREOS5.plan
    ),
    version="1.1.0",
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
WAS_CALLED = {
    "amonet-biscuit-v1.1.0": Deprecated(
        device=BISCUIT,
        name=FIREOS5,
        note=f"It now installs TWRP {BBOE_TWRP_VERSION} rather than amonet's own"
        " TWRP 3.2.3.",
    ),
    "amonet-biscuit-v1.1.0-bboe": Deprecated(device=BISCUIT, name=FIREOS5),
    "amonet-biscuit-v2.0.0": Deprecated(
        device=BISCUIT,
        name=FIREOS6,
        note="It now writes amonet v2.0.1, whose kaeru boots the active slot.",
    ),
}
WRITE_KAERU = Write(image="bin/biscuit-kaeru.bin", label="write kaeru", target="expdb")


class LK(enum.Enum):
    FIREOS5 = "f379dba-20170906_000423"
    FIREOS6 = "63cb91b-20221007_072309"
    FIREOS6_4315 = "41fb3ce-20221007_151724"
    FIREOS6_8338 = "2c3569d-20260617_045829"


LK_VALUES = frozenset(member.value for member in LK)


UNLOCK_TO_FIREOS6 = Unlock(
    device=BISCUIT,
    family="amonet",
    fastbricks={
        LK.FIREOS6.value: "bin/fastbrick-20221007.img",
        LK.FIREOS6_4315.value: "bin/fastbrick-20221007.img",
        LK.FIREOS6_8338.value: "bin/fastbrick-20260617.img",
    },
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


FASTBRICK = UNLOCK_TO_FIREOS6
TARGETS = (
    Target(
        device=BISCUIT,
        goal=State.STOCK_BOOTED,
        installs=FireOs6(build=None),
        name=STOCK,
        summary=f"Amazon's Fire OS BUILD, {DEFAULT_BUILD} when left out,"
        " which erases the whole Dot.",
        unlock=None,
    ),
    Target(
        device=BISCUIT,
        goal=State.AMONET_V1_1_0_BBOE_BOOTED,
        installs=FireOs5(package=BUILDS["5.5.5.4"]),
        name=FIREOS5,
        summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP"
        f" {BBOE_TWRP_VERSION}.",
        unlock=UNLOCK_TO_FIREOS5,
    ),
    Target(
        device=BISCUIT,
        goal=State.AMONET_V2_BOOTED,
        installs=FireOs6(build=FIREOS6_BUILD),
        name=FIREOS6,
        summary=f"rooted Fire OS 6 {FIREOS6_BUILD} on amonet v2.0.1,"
        f" with TWRP {V2_0_1_TWRP_VERSION}.",
        unlock=UNLOCK_TO_FIREOS6,
    ),
)
