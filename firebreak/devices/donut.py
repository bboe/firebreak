from __future__ import annotations

from firebreak.cache import Download
from firebreak.plugin import (
    BOOT0,
    Device,
    DeviceConfig,
    FastbootFlash,
    Feature,
    FireOs6,
    PayloadCommand,
    Reboot,
    Target,
    Unlock,
    Write,
)
from firebreak.states import State
from firebreak.targets import FIREOS6, STOCK
from firebreak.updates import cdn_ota

BOOTONCE_BOOTLOADER = b"bootonce-bootloader"
BOOT_RECOVERY = b"boot-recovery"
BUILDS = {
    "1895": cdn_ota(
        path="165f17697caca40d912478c045c5e156/update-kindle-donut-NS6529_user_1895_0002315741060.bin",
        sha256="4168fce8b6b18271ed71e18e015e2d4f88ee46df75aec8a2672edac9067e1d89",
        verified=True,
    ),
    "4655": cdn_ota(
        path="321b0118c190c0708bf4f740c78f4be8/update-kindle-donut_puffin-NS6559_user_4655_0009094442884.bin",
        sha256="b528859d7f626fdd758229fca4ec49098efb78fefb177e8a510bd7099a79fd87",
        verified=True,
    ),
    "4769": cdn_ota(
        path="5e8fa97b42c0c76430f453c10efeff68/update-kindle-donut_puffin-NS6560_user_4769_0009295798660.bin",
        sha256="46e408602c15c867311aa8317ca7e2ca90f7178225c48587b413e56d584a04a5",
        verified=True,
    ),
    "4774": cdn_ota(
        path="5a98571a500bda59aa7798c16e5c25ea/update-kindle-donut_puffin-NS6560_user_4774_0009295799940.bin",
        sha256="7455d138cc63a1bf02c0ec370bfc1372650e71addc31f8bd62b04d5d07a27260",
        verified=True,
    ),
    "4936": cdn_ota(
        path="d3a4343461ac931bbbeba6ad5e113073/update-kindle-donut_puffin-NS6561_user_4936_0009698494596.bin",
        sha256="9068555493bfac9c1d4affa92d80c5a61118166bd1e9c0e1e18e1b307e4e756f",
        verified=True,
    ),
    "5531": cdn_ota(
        path="2024/9/26/998a4fda-ac67-4c71-afe9-f554dc9e13c2/update-kindle-donut_puffin-NS6565_user_5531_0011040824196.bin",
        sha256="d341d2c571511f4b22abc3eb67766e8725d47769d8d363cd2dbbaf81e0d7eb3e",
        verified=True,
    ),
    "6009": cdn_ota(
        path="2025/7/24/a8307de8-3245-43fe-8a04-232b3fac96c7/update-kindle-donut_puffin-NS6569_user_6009_0011980470660.bin",
        sha256="325543e9efff561cba9cc3341ba0194514aba6501caa5fc1d67371f1a3cd5db5",
        verified=True,
    ),
    "6071": cdn_ota(
        path="2025/8/16/e9e5da87-55f2-4b3e-975e-cf60355a3843/update-kindle-donut_puffin-NS6570_user_6071_0012383139716.bin",
        sha256="12fb654a061dab589c6fb11747378ae7d9aa94ba5d1392e20ab3fe6cfef68e8c",
        verified=True,
    ),
    "6077": cdn_ota(
        path="2025/9/6/6a50a975-bcda-41bd-b05a-9c80e6c9396e/update-kindle-donut_puffin-NS6570_user_6077_0012383141252.bin",
        sha256="245822847cedf10ea3111bac297fedbc6f01aef494cf3a3cc443682b52807af1",
        verified=True,
    ),
    "6086": cdn_ota(
        path="2025/9/23/c071448f-da56-42bc-bbdc-d105d6a6045e/update-kindle-donut_puffin-NS6570_user_6086_0012383143556.bin",
        sha256="c4d3a0dff7fc07d60b6c5f3309fdd03565b89ab2ed769398565d32526bcfe118",
        verified=True,
    ),
    "6176": cdn_ota(
        path="2025/10/9/d8b09e56-0e6e-4aa0-b018-9cd4f1c81429/update-kindle-donut_puffin-NS6571_user_6176_0012584493188.bin",
        sha256="131f0bfdf5cfe1a1964f84da2e5d1128abbb5889a686d6771a4e7488ce939ffc",
        verified=True,
    ),
    "6193": cdn_ota(
        path="2025/10/26/cb26f9fd-10be-446f-9ff3-ce132e722a03/update-kindle-donut_puffin-NS6571_user_6193_0012584497540.bin",
        sha256="8e7010cbce0941752f8dc256961d6909e07889aeede60d2153ff371834b10c59",
        verified=True,
    ),
    "6199": cdn_ota(
        path="2025/11/8/8a40781b-3c93-44ae-8266-0d9dc97ed8c3/update-kindle-donut_puffin-NS6571_user_6199_0012584499076.bin",
        sha256="2d35567f1c1b75626e75fd47af1c0d0ac7fd5c57fc8d7f3817576819cc79c14f",
        verified=True,
    ),
    "6208": cdn_ota(
        path="2025/11/28/127a6c2e-5c62-4101-875c-77e29f330812/update-kindle-donut_puffin-NS6571_user_6208_0012584501380.bin",
        sha256="a112818c957733566a83259b7eba2a38116e85e6dace83c8862b55ba250b85f2",
        verified=True,
    ),
    "6220": cdn_ota(
        path="2026/1/17/af80af0f-ca64-4625-a040-82c423e6dbc0/update-kindle-donut_puffin-NS6571_user_6220_0012584504452.bin",
        sha256="664adcf15ee91aa05b9467e40a5149a7357cf980651dea6f1179289123d9705e",
        verified=True,
    ),
    "6425": cdn_ota(
        path="2026/3/6/3824ae74-3a8f-4fdd-bc4f-59dfc8b5eb02/update-kindle-donut_puffin-NS6572_user_6425_0012718774660.bin",
        sha256="fba04b8191959603fe07e4d31aa59b1a0d8bca0a8c1942c58a92e99c12401d3c",
        verified=True,
    ),
    "6554": cdn_ota(
        path="2026/5/12/8ab1ca64-ad29-47e5-a9d8-97c7ba00437d/update-kindle-donut_puffin-NS6573_user_6554_0012853025412.bin",
        sha256="ceed9387b6385b3ced5360d34e2af08aa0d250b21f1bfd935ee021e1a0c35389",
        verified=True,
    ),
    "6562": cdn_ota(
        path="2026/5/22/61b55f8d-fd3e-406c-ade2-3643fe642423/update-kindle-donut_puffin-NS6573_user_6562_0012853027460.bin",
        sha256="5c6bd3b1bad7b14878c22f977ead2c79547d8efa088c99152299621b5183ac7c",
        verified=True,
    ),
    "6813": cdn_ota(
        path="2025/5/15/1450a8a3-5c82-4ba3-8f22-ce9f370fa7b5/update-kindle-donut_puffin-NS6566_user_6813_0011779349892.bin",
        sha256="a0906737a310cc557d5176096e0ba36d6410d01a3397f4d2eb833f7998a16c5d",
        verified=True,
    ),
    "8138": cdn_ota(
        path="2026/8/31/47af3c26-2d8c-4160-887a-4b58d4e05032/update-kindle-donut_puffin-NS65741_user_8138_0013222529668.bin",
        sha256="ac22b78cf94c2ebacfa90447b770b803d9f72f35858d5218975d97fea95a0245",
        verified=True,
    ),
    "8142": cdn_ota(
        path="2026/9/9/b4a35bf3-94b3-44e2-a709-677185a243a8/update-kindle-donut_puffin-NS65741_user_8142_0013222530692.bin",
        sha256="1c66ad7934d5623cd254bfcba8741442176925b68c3a09f6f10092df2ce9a593",
        verified=True,
    ),
    "8146": cdn_ota(
        path="2026/9/17/486923a2-9bfe-48cf-85f7-0cce5b02c99b/update-kindle-donut_puffin-NS65741_user_8146_0013222531716.bin",
        sha256="68e4e884d5a00226aa48add860f690a56974913c4f29b5f367561fc29360a4f5",
        verified=True,
    ),
    "8149": cdn_ota(
        path="2026/9/29/6db1d3a7-8ce2-4bc5-b528-cacd6aa38a96/update-kindle-donut_puffin-NS65741_user_8149_0013222532484.bin",
        sha256="8ddf04884ee407f7ad3d96e164e1e3c06ee86cce9909ffde4de4db39d4e93e7c",
        verified=True,
    ),
    "8338": cdn_ota(
        path="2026/10/14/8639d501-83ed-489b-86c4-3b433ed8d82d/update-kindle-donut_puffin-NS6575_user_8338_0013323244164.bin",
        sha256="7c267ba703103fcc1f248e8a3b0f80b16b029da1e11eddf1203304d097fe93d8",
        verified=True,
    ),
    "8344": cdn_ota(
        path="2026/10/21/1882ec12-9120-4ba1-9f93-2ca5d8fd4cc1/update-kindle-donut_puffin-NS6575_user_8344_0013323245700.bin",
        sha256="5eef0cb98bef4bc6fbeed825c8b35d3a4a79635fe98c5de9c04bf96ef7ba1f57",
        verified=True,
    ),
    "8349": cdn_ota(
        path="2026/10/27/403ee71e-c316-4460-845b-3f50df862132/update-kindle-donut_puffin-NS6575_user_8349_0013323246980.bin",
        sha256="ecf40ee592c938a25a89d1205723d0beb898372f29cfd35c5f90df01cf6ac84f",
        verified=True,
    ),
}
BUTTON_GESTURE = (
    "Unplug it. Press and hold its action button, the circle on top, before you"
    " plug the cable in. Keep holding while you plug it in, until the run says"
    " the bootrom answered."
)
DEFAULT_BUILD = "8349"
FASTBOOT_MODE = (
    "Unplug the USB cable and plug it back in, then press and hold the action"
    " button, the circle on top, a second or two later, until the ring turns"
    " green. A hold from the moment the cable goes in reaches this Echo's"
    " bootrom instead: a run that says the bootrom answered means this one needs"
    " starting again, with the hold later."
)
DONUT = Device(
    device_type_id="A32DOYMUN6DTXA",
    fastboot_command=BOOTONCE_BOOTLOADER,
    fastboot_mode=FASTBOOT_MODE,
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    hardware_code=0x8167,
    models=frozenset({"AEODN"}),
    name="donut",
    named_by_bootloader=False,
    product="DONUT",
    recovery_command=BOOT_RECOVERY,
    short_gesture=BUTTON_GESTURE,
    thread="https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-3rd-gen-2018-donut.4801400/",
    title="Echo Dot (3rd Generation)",
    unlock_keeps_misc=True,
)
SET_FASTBOOT_FLAG = 0x6000
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
        PayloadCommand(
            command=SET_FASTBOOT_FLAG, label="set the fastboot flag", settle=5.0
        ),
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
CONFIG = DeviceConfig(
    adb_off_builds=frozenset({"1895"}),
    builds=BUILDS,
    default_build=DEFAULT_BUILD,
    default_target=FIREOS6,
    device=DONUT,
    kamakiri_unlock=KAMAKIRI_V1_0_0,
    lk_values=frozenset({
        "0d18cf4-20181206_233555",
        "0db8914-20221005_072344",
        "6f7225e-20230407_013816",
    }),
    targets=(
        Target(
            device=DONUT,
            goal=State.STOCK_BOOTED,
            installs=FireOs6(build=None),
            name=STOCK,
            summary=f"Amazon's Fire OS BUILD, {DEFAULT_BUILD} when left out,"
            " which erases the whole Echo and locks it again.",
            unlock=None,
        ),
        Target(
            device=DONUT,
            goal=State.UNLOCKED_BOOTED,
            installs=FireOs6(build=DEFAULT_BUILD),
            name=FIREOS6,
            summary=f"boot-root.zip's root adb on Fire OS 6 {DEFAULT_BUILD}, installed"
            " over an older Fire OS 6 if need be, which keeps the Echo's setup;"
            " with --factory-reset, Fire OS 6"
            f" {DEFAULT_BUILD}, with the Echo erased.",
            unlock=KAMAKIRI_V1_0_0,
        ),
    ),
)
