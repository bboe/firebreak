from __future__ import annotations

import dataclasses

from firebreak.cache import Download
from firebreak.devices.biscuit import BISCUIT, UNLOCK_TO_FIREOS6, WRITE_KAERU
from firebreak.plugin import ClearBoot0Header, DeviceConfig, FireOs6, Target
from firebreak.states import State
from firebreak.targets import FIREOS6, STOCK
from firebreak.updates import cdn_ota

BUILDS = {
    "4305": cdn_ota(
        path="c94cf112b3d9e1a422b57df88eb07e8b/update-kindle-radar_puffin-NS6555_user_4305M_0008087720314.bin",
        sha256="ded26d993f149a31e298a0539a92a876f063912f1fe98b21c0176597e2197752",
        verified=True,
    ),
    "4315": cdn_ota(
        path="786582d551e9c8594a7eb5ebe0cb6987/update-kindle-radar_puffin-NS6555_user_4315M_0008087722874.bin",
        sha256="df77677f2d4fae47ded5a350cd71c89d514fdfca746f78934ac02245bd3b30d5",
        verified=True,
    ),
    "4929": cdn_ota(
        path="425712b2af06933df7100bc52f20086b/update-kindle-radar_puffin-NS6561_user_4929_0009698492804.bin",
        sha256="3899ca383d5c473bdf6a1aacd76c637a01f95116f1f14ad13fb612141087a431",
        verified=True,
    ),
    "4936": cdn_ota(
        path="683e4caa9a7fce0c9cb1e7105089ca51/update-kindle-radar_puffin-NS6561_user_4936_0009698494596.bin",
        sha256="7506b4b14f2f7a184ba566a657f22bf528c10459eeb7651e4fda8d0ff4c583b9",
        verified=True,
    ),
    "5.5.5.4": cdn_ota(
        path="b3a81477c5aebe779bc95b837e374311/update-kindle-csm_radar-288.6.8.0_user_680767620.bin",
        sha256="9acebcd78c6837d428ee7eff3c1f57a89f895f8968b4d7afe3e84986f01dcd52",
        verified=True,
    ),
    "5555": cdn_ota(
        path="2024/11/20/fd6a261b-ee99-4a93-bd9e-423c3fd4bc41/update-kindle-radar_puffin-NS6565_user_5555_0011040830340.bin",
        sha256="8961286d1ed86008e2b9e4ab5bce5e46163faa14abd1d3b3b012c87b8210481c",
        verified=True,
    ),
    "5571": cdn_ota(
        path="2025/3/12/46ea1f87-8f5b-42df-84b5-2f2310b0eaeb/update-kindle-radar_puffin-NS6565_user_5571_0011040834436.bin",
        sha256="5ec3631bbd3db6563533f46b4354340e4cc9697bb94c089182d8349a450e6b35",
        verified=True,
    ),
    "6009": cdn_ota(
        path="2025/7/24/279fbd03-211e-4f8a-b612-072ab64cf6d8/update-kindle-radar_puffin-NS6569_user_6009_0011980470660.bin",
        sha256="b714952a14ab8fea519ea9dba44ac4596f3566f064913686c0669af49c0b64c7",
        verified=True,
    ),
    "6071": cdn_ota(
        path="2025/8/16/53d23555-4d2d-4fba-af7e-6d51bb038949/update-kindle-radar_puffin-NS6570_user_6071_0012383139716.bin",
        sha256="5526257b78706875447ed136605913fb5d6681fca9c1073d48b49c0ac382b7a3",
        verified=True,
    ),
    "6199": cdn_ota(
        path="2025/11/8/d75268f0-a7d9-437b-b18d-ddad90dc53a1/update-kindle-radar_puffin-NS6571_user_6199_0012584499076.bin",
        sha256="e425074064a6b3e1af06e15139f2bd3a5d69e063f321b01be7726a408dcf02bf",
        verified=True,
    ),
    "6208": cdn_ota(
        path="2025/11/28/21618840-04ae-4d04-8124-ab6148dd0031/update-kindle-radar_puffin-NS6571_user_6208_0012584501380.bin",
        sha256="dacaf4996f1f48f1ac7e9353a1df44ddf7d47e816cb26deac2bd64297dcb39e9",
        verified=True,
    ),
    "6220": cdn_ota(
        path="2026/1/17/3467bda0-6332-4c07-950b-ed0106b7ec5d/update-kindle-radar_puffin-NS6571_user_6220_0012584504452.bin",
        sha256="54e2a35c4847044dcab0ea92d5b1fd03df6fab3aba69ef9fde0251643d0f3ede",
        verified=True,
    ),
    "6302": cdn_ota(
        path="2025/4/13/a36b9ebb-4b98-4788-ac82-e7a0f2432d14/update-kindle-radar_puffin-NS6466_user_6302_0011712110212.bin",
        sha256="11c76a9976cb31648659ca07d80698af51a1b071b0f5b7261e84e01c036ee598",
        verified=True,
    ),
    "6425": cdn_ota(
        path="2026/3/6/f0f2ea3e-ed49-474b-aee2-f81a86124516/update-kindle-radar_puffin-NS6572_user_6425_0012718774660.bin",
        sha256="993d8e7ab027f0e4f10180a12262ab78dfc442156992b3d12fbe93f5e4d5fcb9",
        verified=True,
    ),
    "6436": cdn_ota(
        path="2026/3/21/22138e24-4af9-483b-8b47-0420835a92fd/update-kindle-radar_puffin-NS6572_user_6436_0012718777476.bin",
        sha256="976e2761c5bb9e5d3d9a2b1b9bc2f2296b89a5b37057ab1780743aa075f2df48",
        verified=True,
    ),
    "6813": cdn_ota(
        path="2025/5/15/0f8045ed-9120-4f00-9a3b-39fcd5dd7c14/update-kindle-radar_puffin-NS6566_user_6813_0011779349892.bin",
        sha256="4d6a128ef5d4aa9a5f529a5359f3423a53265adabaa75e9c14dc2952af941bfd",
        verified=True,
    ),
    "7577": cdn_ota(
        path="2026/6/12/528ff4a1-b599-425b-b6d7-669bb3781c01/update-kindle-radar_puffin-NS6573_user_7577_0012920396164.bin",
        sha256="9bb682f023b8f1d58882d4164f36f4206a01405d34906cdcbff023240b98cc86",
        verified=True,
    ),
    "8149": cdn_ota(
        path="2026/9/29/54a9ed82-ce12-49e3-91da-b10f7f5b831f/update-kindle-radar_puffin-NS65741_user_8149_0013222532484.bin",
        sha256="5c001abc6b9a979bd3c536fa64c3b0567fe68dd05dbf092fbe96ddfb243abc6e",
        verified=True,
    ),
    "8338": cdn_ota(
        path="2026/10/14/467e4e4d-33f8-45c7-8d54-c4ab67fee6da/update-kindle-radar_puffin-NS6575_user_8338_0013323244164.bin",
        sha256="d187b0290e935fb2ab5df81155600decaa24057e86aefe3dcbee016f7164e2bc",
        verified=True,
    ),
    "8344": cdn_ota(
        path="2026/10/21/5c9ee383-4f5d-427f-ad31-5e2745f4bbd7/update-kindle-radar_puffin-NS6575_user_8344_0013323245700.bin",
        sha256="6a0bb41cb2f766f31c0ff5c6f4004a48ce87e140051d7e99cdafa42206a4e8e9",
        verified=True,
    ),
    "8349": cdn_ota(
        path="2026/10/27/bfb778eb-43bd-40c7-8310-e195d8fa91f4/update-kindle-radar_puffin-NS6575_user_8349_0013323246980.bin",
        sha256="af1269ebb5e892afc673a99d9dc322e254d5499454f29a9608ab1839a63c0736",
        verified=True,
    ),
}
DEFAULT_BUILD = "8349"


RADAR = dataclasses.replace(
    BISCUIT,
    models=frozenset({"AEORD", "Echo (2nd Gen)"}),
    name="radar",
    product="RADAR",
    short_gesture=(
        "Open the Echo through step 8 of iFixit's main board guide, leaving the"
        " board in, and lift the shield's lid off the eMMC. Short the passive"
        " between R60 and C52, beside the eMMC, to the shield frame, then plug"
        " the cable in with the short held. Do not use C52, which is a"
        " capacitor."
        " https://www.ifixit.com/Guide/Amazon+Echo+2nd+Generation+MLB+Board+Replacement/114704"
    ),
    thread="https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-2nd-gen-2017-radar.4801290/",
    title="Echo (2nd Generation)",
)


SOURCE = Download(
    browser=True,
    directory="radar-v1.0.1",
    mirror=True,
    name="amonet-radar-v1.0.1.zip",
    sha256="22809bc44b9b7b71750c1955bb94a92c965b557d4f9055bb7bbc098b788188a9",
    size=94789047,
    url="https://xdaforums.com/attachments/amonet-radar-v1-0-1-zip.6403363/",
)
AMONET_V1_0_1 = dataclasses.replace(
    UNLOCK_TO_FIREOS6,
    device=RADAR,
    fastbricks={
        "2c3569d-20260617_051433": "bin/fastbrick-20260617.img",
        "59779ca-20220524_183401": "bin/fastbrick-20220524.img",
        "63cb91b-20221007_073612": "bin/fastbrick-20221007.img",
    },
    little_kernel="",
    plan=tuple(
        dataclasses.replace(WRITE_KAERU, image="bin/radar-kaeru.bin")
        if step == WRITE_KAERU
        else step
        for step in UNLOCK_TO_FIREOS6.plan
    ),
    source=SOURCE,
    version="1.0.1",
)
CONFIG = DeviceConfig(
    bootrom_unlock=dataclasses.replace(
        AMONET_V1_0_1, plan=(ClearBoot0Header(), *AMONET_V1_0_1.plan)
    ),
    builds=BUILDS,
    default_build=DEFAULT_BUILD,
    default_target=FIREOS6,
    device=RADAR,
    fastbrick=AMONET_V1_0_1,
    fireos5_builds=frozenset({"5.5.5.4"}),
    lk_values=frozenset({
        "59779ca-20220524_183401",
        "63cb91b-20221007_073612",
        "41fb3ce-20221007_153017",
        "2c3569d-20260617_051433",
    }),
    targets=(
        Target(
            device=RADAR,
            goal=State.STOCK_BOOTED,
            installs=FireOs6(build=None),
            name=STOCK,
            summary=f"Amazon's Fire OS BUILD, {DEFAULT_BUILD} when left out,"
            " which erases the whole Echo.",
            unlock=None,
        ),
        Target(
            device=RADAR,
            goal=State.UNLOCKED_BOOTED,
            installs=FireOs6(build=DEFAULT_BUILD),
            name=FIREOS6,
            summary=f"boot-root.zip's root adb on Fire OS 6 {DEFAULT_BUILD}, installed"
            " over an older Fire OS 6 if need be, which keeps the Echo's setup;"
            " with --factory-reset, Fire OS 6"
            f" {DEFAULT_BUILD}, with the Echo erased.",
            unlock=AMONET_V1_0_1,
        ),
    ),
)
