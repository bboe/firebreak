from __future__ import annotations

import dataclasses

from firebreak.cache import Download
from firebreak.devices.authors import RORTIZ2
from firebreak.layouts import BootMovedLayout, StockLayout
from firebreak.plugin import (
    BOOT0,
    ClearBoot0Header,
    Device,
    DeviceConfig,
    FastbootFlash,
    Feature,
    FireOs5,
    FireOs5Chain,
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
from firebreak.targets import FIREOS5, FIREOS6, STOCK
from firebreak.updates import cdn_ota

AMONET_V1_1_0_LK = "f379dba-20170906_000423"


AMONET_V2_LK = "63cb91b-20221007_072309"
BBOE_TWRP_VERSION = "3.7.0_9-bboe2"
BBOE_RECOVERY = Download(
    name=f"twrp-{BBOE_TWRP_VERSION}-biscuit.img",
    sha256="f59052713a6580a1477490b2f9cad80e9b31d22408861b18fd442129a71f2ad9",
    size=13953024,
    url="https://github.com/bboe/twrp_device_amazon_echo-mt8163/releases/download/"
    f"v{BBOE_TWRP_VERSION}/twrp-v{BBOE_TWRP_VERSION}-biscuit.img",
)
BOOTROM_BUILDS = frozenset({"5.5.0.3", "5.5.0.3-1973"})
BOOT_MOVED_LAYOUT = BootMovedLayout(
    align=0x400, sectors=0x37000, targets=("boot_a", "boot_b")
)
BUILDS = {
    "4310": cdn_ota(
        path="4c4fd21537a97548236e9a88cd835030/update-kindle-biscuit_puffin-NS6555_user_4310M_0008087721594.bin",
        sha256="c0839bc1b8bd25746e3bc86dc716ce0ba25022f2b862be0c484187957fbc649d",
        verified=True,
    ),
    "4313": cdn_ota(
        path="994407ac6e55e2fb381de6f514555484/update-kindle-biscuit_puffin-NS6555_user_4313M_0008087722362.bin",
        sha256="5d76a4089bb388cbd56113078f10fc87d148f42337795e87c9f04e7dfd395dfb",
        verified=True,
    ),
    "4315": cdn_ota(
        path="6277b5d592ff79ff4ca2c84082a88bbf/update-kindle-biscuit_puffin-NS6555_user_4315M_0008087722874.bin",
        sha256="c1ca33efd975cb8491ea9438eff95af559c632dd7ca75ff3b73facacce5f758a",
        verified=True,
    ),
    "4405": cdn_ota(
        path="2e17a264c416806ff7d3d984e1b6fcb7/update-kindle-biscuit_puffin-NS6556_user_4405_0008289072516.bin",
        sha256="6839b0a1e5c4f6aa57f89ea7ca67c85aa69f8fe32e5ddc252764b0d96be5bf69",
        verified=True,
    ),
    "4521": cdn_ota(
        path="019175adb3adbdbd157f948fb74a471c/update-kindle-biscuit_puffin-NS6558_user_4521_0008624646532.bin",
        sha256="7b7a3c55121c913b04a1cc57497d9bda2cd8551cef63765e6e310099bfcac5bd",
        verified=True,
    ),
    "4657": cdn_ota(
        path="61d2a62fa9d58c3184a13d23bb1b912c/update-kindle-biscuit_puffin-NS6559_user_4657_0009094443396.bin",
        sha256="f976390a536e700956cf2f60fc06a39af0a6ebe44b9e12d71673d16368487cd1",
        verified=True,
    ),
    "4660": cdn_ota(
        path="cd5c2a08fa0de682af56c9f7f14512b2/update-kindle-biscuit_puffin-NS6559_user_4660_0009094444164.bin",
        sha256="b98b30ec4c8091c0ae34c110a0d2223ab2c0c1e1e0ee45f776af6968fcbce727",
        verified=True,
    ),
    "4774": cdn_ota(
        path="6c94643670d218ad54d242c6ff16bc94/update-kindle-biscuit_puffin-NS6560_user_4774_0009295799940.bin",
        sha256="814157284a2e5a9cdfa16fc4d21b694193e45326725d1f338304d39785917e82",
        verified=True,
    ),
    "4779": cdn_ota(
        path="a0db7929e0d3490e4762a79f3c08f09c/update-kindle-biscuit_puffin-NS6560_user_4779_0009295801220.bin",
        sha256="0c0ae4009d787c33b1a51905acb8f34caa9f3caf74564955d2efc674ee7f3c6d",
        verified=True,
    ),
    "4781": cdn_ota(
        path="55b25c2b40df952ceda06ed1cae3aa94/update-kindle-biscuit_puffin-NS6560_user_4781_0009295801732.bin",
        sha256="e3d72708b76b9c55f86576399d70b307dc021e7e0efb06b7481c9f46e2355ffa",
        verified=True,
    ),
    "4929": cdn_ota(
        path="6ce1a526b4763bc85917dd89dd0bd3be/update-kindle-biscuit_puffin-NS6561_user_4929_0009698492804.bin",
        sha256="b2972d5a417eca4a1227ad69883f0fea092f2e832c95f43efaaac6133eb248d1",
        verified=True,
    ),
    "4936": cdn_ota(
        path="20f71463b25560a395bd375bd92356ea/update-kindle-biscuit_puffin-NS6561_user_4936_0009698494596.bin",
        sha256="4fcc534cdc0bec295880a7f03f23349f4729bde2186e33db7005464b28e13577",
        verified=True,
    ),
    "5.4.2.7": cdn_ota(
        path="d10066e01b433e0bf5a012d91a1cc873/update-kindle-full_biscuit-272.6.2.8_user_628538320.bin",
        sha256="b5244c9808648d64eea2dd0ae9717b956ba161031ed3924387ae82e58f697ee4",
        verified=True,
    ),
    "5.5.0.3": cdn_ota(
        path="1b9718ec2da663bb299676df977055c9/update-kindle-full_biscuit-272.5.6.4_user_564196920.bin",
        sha256="5458cd2d49b4549310d17ea9fb390db0733a633df4187fcdccabc38a980f8bea",
        verified=True,
    ),
    "5.5.0.3-1973": cdn_ota(
        path="2cdcb34bd838de6d18a8983579ef7c0d/update-kindle-full_biscuit-272.5.6.4_user_564197320.bin",
        sha256="6a837e9d03af66e7f2a19458fb1ceed80b7b1824d325290f887d1de9d5ec71df",
        verified=True,
    ),
    "5.5.3.1": cdn_ota(
        path="8811a0fc982bf3331dc54f5aec45d936/update-kindle-full_biscuit-272.6.4.1_user_641575220.bin",
        sha256="28bc050e4a2af79c9ca66e251de7bf04c42ce8d7934dd97673d3d04f5fa0917b",
        verified=True,
    ),
    "5.5.3.3": cdn_ota(
        path="8cbe02aeb18d77ee57ab3a7b53fa87ce/update-kindle-csm_biscuit-272.6.4.5_user_645584020.bin",
        sha256="c3536a5a6abebfb253c562714c533f182c89e696817261c52e98d9f734b4855b",
        verified=True,
    ),
    "5.5.3.6": cdn_ota(
        path="192c4dbb3ffe5ea85c8b012cba89d713/update-kindle-csm_biscuit-272.6.5.1_user_651614420.bin",
        sha256="637f62157129ac32654a0c07bdefb64b756e7fb747a13a5fcd451dda7d8b41f2",
        verified=True,
    ),
    "5.5.4.6": cdn_ota(
        path="0cdf0a5782c43290ba9a598e1ede98e6/update-kindle-csm_biscuit-272.6.6.6_user_666694320.bin",
        sha256="f6ed07177d98930a84db271d036a8a0d2d82dfc0bfde93f96151143de1dc9026",
        verified=True,
    ),
    "5.5.4.9": cdn_ota(
        path="60556d35239d902637f0fc503411b791/update-kindle-csm_biscuit-272.6.7.2_user_672720020.bin",
        sha256="ec6d1a694a46dcaee1ec8b1130131e994e99ab80547dc17dd79e504d23b4bedb",
        verified=True,
    ),
    "5.5.5.0": cdn_ota(
        path="f4994d8b2b10442d42e07b8c5d996a91/update-kindle-csm_biscuit-272.6.7.3_user_673726720.bin",
        sha256="6bda9ebc976fc8c8a2dffdb88ab3c27ca0f73882c47812d9b90fe30d39bb6244",
        verified=True,
    ),
    "5.5.5.4": cdn_ota(
        path="47a1457e0802980eb32f63cd3ce355c0/update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
        sha256="6ababc517529938f0d1e836c3410a91df19683ae62d7fca9e2ca57320d5d2faa",
        verified=True,
    ),
    "5041": cdn_ota(
        path="b221e0c9947ee49842251cc89c7b74ce/update-kindle-biscuit_puffin-NS6505_user_5041_0008960323972.bin",
        sha256="80d98d3b57bc654d435b384f096dea46edd2b86e9f8adaaf91a7b0c3001e9716",
        verified=True,
    ),
    "5160": cdn_ota(
        path="2024/4/26/9ed9d91b-2bb8-417f-9eb1-7b0a61e510bd/update-kindle-biscuit_puffin-NS6562_user_5160_0010101205124.bin",
        sha256="faa32119a21d775fd0a773591a3797c0512a70a93bfbec494848bd861515b6ff",
        verified=True,
    ),
    "5295": cdn_ota(
        path="2024/6/15/a29a940a-a9e2-439d-924b-0a4620c205c0/update-kindle-biscuit_puffin-NS6563_user_5295_0010369675140.bin",
        sha256="44b2b9bd5326e98ded8ccb4cdfd4c3efcf6c98b74bf4e13d2f8fb8f27a7121ca",
        verified=True,
    ),
    "5403": cdn_ota(
        path="2024/7/21/d420d3bf-9ca8-40ab-99f4-7b6d291169f7/update-kindle-biscuit_puffin-NS6564_user_5403_0010705247108.bin",
        sha256="c6f0abf5c3e439d0c29281d007322df63662eaffd91ad1057d69065bf5274553",
        verified=True,
    ),
    "5531": cdn_ota(
        path="2024/9/26/a11e7086-e143-4fe2-963a-08dc0954c45b/update-kindle-biscuit_puffin-NS6565_user_5531_0011040824196.bin",
        sha256="4f3fe9ce162e895b4fb374de63431dac1f9398b148c8a7b5d23c92b1ff543184",
        verified=True,
    ),
    "5555": cdn_ota(
        path="2024/11/20/59cdc41b-6ce1-4d3c-9ff6-9881a4441cef/update-kindle-biscuit_puffin-NS6565_user_5555_0011040830340.bin",
        sha256="5e6acda2eda625dd2d08af48b9ff846cd95f5480ce92fabf953f2b808299c35c",
        verified=True,
    ),
    "6009": cdn_ota(
        path="2025/7/24/538ff3ab-007a-455d-91e2-27eb07101f72/update-kindle-biscuit_puffin-NS6569_user_6009_0011980470660.bin",
        sha256="c9792d4e7d0eacc6ca93604adcaa3a397700a6763127988b85270b11bfe654d5",
        verified=True,
    ),
    "6077": cdn_ota(
        path="2025/9/6/5a1dca5b-e5f5-43b2-b5d9-874a97664201/update-kindle-biscuit_puffin-NS6570_user_6077_0012383141252.bin",
        sha256="624cffef53eaeefc26026cbc900fc24a8db7cfad42f22bf301883af73c6b8bbb",
        verified=True,
    ),
    "6086": cdn_ota(
        path="2025/9/23/98b5d32f-85e2-4cda-a609-05576d9863d0/update-kindle-biscuit_puffin-NS6570_user_6086_0012383143556.bin",
        sha256="ddf055cd0c3f4515ed1f1820c2d718f5f2ea411d82ca9f201d4283cfdbe918be",
        verified=True,
    ),
    "6176": cdn_ota(
        path="2025/10/9/e27d65e8-7b79-4207-82e1-f7d8c8a72bea/update-kindle-biscuit_puffin-NS6571_user_6176_0012584493188.bin",
        sha256="0767c4fce3f797476c1fe534d44e3a5cac2b557f78e984461f385e7de61833e8",
        verified=True,
    ),
    "6193": cdn_ota(
        path="2025/10/26/a401e338-9075-4d9f-8f97-b5060ba1830a/update-kindle-biscuit_puffin-NS6571_user_6193_0012584497540.bin",
        sha256="bbd938d3def7974616743fcd39ef7836cf6259b84b217b22ce941de981dd998a",
        verified=True,
    ),
    "6199": cdn_ota(
        path="2025/11/8/38892155-15c4-4e86-92b0-ce87bb9dbc30/update-kindle-biscuit_puffin-NS6571_user_6199_0012584499076.bin",
        sha256="55ccafd2606aba325484c264ddcede26e27ca50df3dcb255cd2755beb6ff677e",
        verified=True,
    ),
    "6208": cdn_ota(
        path="2025/11/28/0b98824c-4529-46b2-bad3-5f7256e98ede/update-kindle-biscuit_puffin-NS6571_user_6208_0012584501380.bin",
        sha256="ee3feb9a6e1bc76e51f30ced6a42c453a8a1c5f452c7e914819f05a201930be0",
        verified=True,
    ),
    "6220": cdn_ota(
        path="2026/1/17/ec308665-9df5-49b9-997e-d4f058b33af4/update-kindle-biscuit_puffin-NS6571_user_6220_0012584504452.bin",
        sha256="6a399a35f12beec926b4a799c3ff3bac12d645c5bb270c95cd456613fcb671c8",
        verified=True,
    ),
    "6302": cdn_ota(
        path="2025/4/13/06eb800d-de9a-4a1c-a5ea-25d297190fc7/update-kindle-biscuit_puffin-NS6466_user_6302_0011712110212.bin",
        sha256="6d395345b1d1db373f9d714172c2ac5de4b5dd3e52d1ed1c3f37c2f007537667",
        verified=True,
    ),
    "6448": cdn_ota(
        path="2026/4/11/e326243a-8c73-4a2d-bdfe-287f66ea5ca6/update-kindle-biscuit_puffin-NS6572_user_6448_0012718780548.bin",
        sha256="f8f8da4485219b73278b831f62c9db17f03db295df342b5fcd70c798f09aa19b",
        verified=True,
    ),
    "6562": cdn_ota(
        path="2026/5/22/c86098a7-c25b-4bb4-8ef5-9fcd38763dae/update-kindle-biscuit_puffin-NS6573_user_6562_0012853027460.bin",
        sha256="bd394bb89e3caf8c4f28efa6193f27dc72396ddfc4bb133ff75771af9b971d8a",
        verified=True,
    ),
    "6813": cdn_ota(
        path="2025/5/15/a52a299d-58bc-4124-892c-ddd8a4bed4bd/update-kindle-biscuit_puffin-NS6566_user_6813_0011779349892.bin",
        sha256="e80a37f23e10ff18b8313a8a3ce0dbd7db6a065fc9b3b93cc63cb8aa050d7da4",
        verified=True,
    ),
    "7577": cdn_ota(
        path="2026/6/12/1a2a189d-f33e-4d7d-94a0-9d602c77a0e6/update-kindle-biscuit_puffin-NS6573_user_7577_0012920396164.bin",
        sha256="ae1405b14088d30279a1df9ea51d57886b7595a61bdbac6098e4567b00f0cf0f",
        verified=True,
    ),
    "7595": cdn_ota(
        path="2026/7/3/5518ca9f-2af7-4b12-a33f-12365be27a57/update-kindle-biscuit_puffin-NS6573_user_7595_0013054618500.bin",
        sha256="28ab1f3e6377277545e8bf7fa15c702c1e6a82900d96f371fb9629147605290d",
        verified=True,
    ),
    "7623": cdn_ota(
        path="2026/8/3/f49aaff7-dd63-4d9c-9e9a-c17498267de5/update-kindle-biscuit_puffin-NS6574_user_7623_0013121734532.bin",
        sha256="64ab6d2dd85f8093abdd62c275d229c7e9fdd68e4d46892b48bdbd1d100d46d8",
        verified=True,
    ),
    "8138": cdn_ota(
        path="2026/8/31/9314fd65-d6e4-4a1a-8089-9f90ea835c77/update-kindle-biscuit_puffin-NS65741_user_8138_0013222529668.bin",
        sha256="d2a61dd2af1d322e9ecfb4643670fbe416bc2442410f1aebe9748e2438f6d55f",
        verified=True,
    ),
    "8142": cdn_ota(
        path="2026/9/9/b8de99f9-4a75-4513-b159-b44fd0316553/update-kindle-biscuit_puffin-NS65741_user_8142_0013222530692.bin",
        sha256="ed4ddb01cd53e38751bb6274ad1a8255043e0795843d6ac2d44cc2803b2179a0",
        verified=True,
    ),
    "8146": cdn_ota(
        path="2026/9/17/566d9028-8c3d-45a2-b5a8-4c4439ba2126/update-kindle-biscuit_puffin-NS65741_user_8146_0013222531716.bin",
        sha256="90832e86498c5e803974c30359aea71c1129757be0ddc59d831a94b27f81487f",
        verified=True,
    ),
    "8149": cdn_ota(
        path="2026/9/29/9a45cfba-a9ee-4f8f-ba00-fcbffd59e3f1/update-kindle-biscuit_puffin-NS65741_user_8149_0013222532484.bin",
        sha256="4e00fc6d6e2bcf5146e502c7d14e67d2ab47b43c3dcca4e1e9439d24730a6c0b",
        verified=True,
    ),
    "8338": cdn_ota(
        path="2026/10/14/e5a2c4cb-7834-4c0f-95b1-301a3ab72194/update-kindle-biscuit_puffin-NS6575_user_8338_0013323244164.bin",
        sha256="c8ea0061e2d117d78c7f9a507dfd435505c324eac7a6ee03499276d9a982ccf0",
        verified=True,
    ),
    "8344": cdn_ota(
        path="2026/10/21/7b68e963-d690-4c24-8a7c-75bbcad855e3/update-kindle-biscuit_puffin-NS6575_user_8344_0013323245700.bin",
        sha256="a7849e192e0b4b885e48f57a216aadffb1227e7d7b6daa4c3003cd723c9ba995",
        verified=True,
    ),
    "8349": cdn_ota(
        path="2026/10/27/17ca785d-56f7-470f-8bd0-fe77776cba02/update-kindle-biscuit_puffin-NS6575_user_8349_0013323246980.bin",
        sha256="7603f0333a1683e56528debec1658a50c2fe0151338052af9f161f244ae7b64b",
        verified=True,
    ),
    "8888": cdn_ota(
        path="2026/11/25/27d3ea77-29b7-49b2-8b46-be581c9af0c6/update-kindle-biscuit_puffin-NS65751_user_8888_0013759592580.bin",
        sha256="9c6cda9fcad6dd5cc267bdcbf8fcb0b1db245fe34ef92b3f8b323a3f6cc44238",
        verified=True,
    ),
}
DEFAULT_BUILD = "8349"
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green. A"
    " ring that stays solid blue can mean a cable that carries power but no"
    " data, or a bad USB connection: try another cable, then another port."
)
FLASH_AMONET_TWRP = FastbootFlash(
    image="bin/twrp.img", label="write TWRP", target="recovery"
)
FLASH_BBOE_TWRP = FastbootFlash(
    image="twrp", label="write TWRP " + BBOE_TWRP_VERSION, target="recovery"
)
PAYLOAD_SEEK = 223207
SHORT_GESTURE = (
    "Open the base, as Andy Goetz's teardown shows, and lift the shield's lid"
    " off the eMMC. Short the passive between R60 and C52, beside the eMMC, to"
    " the shield frame, then plug the cable in with the short held. Do not use"
    " C52, which is a capacitor."
    " https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/"
)
STOCK_LAYOUT = StockLayout(partitions=16)


BISCUIT = Device(
    fastboot_mode=FASTBOOT_MODE,
    features=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    layouts=(BOOT_MOVED_LAYOUT, STOCK_LAYOUT),
    models=frozenset({"AEOBC", "Echo Dot (2nd Gen)", "Echo Dot 2nd Gen"}),
    name="biscuit",
    product="BISCUIT",
    short_gesture=SHORT_GESTURE,
    thread="https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/",
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
    author=RORTIZ2,
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
        Reboot(label="restarting into amonet's fastboot"),
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
V2_0_0_SOURCE = Download(
    browser=True,
    directory="v2.0.0",
    mirror=True,
    name="amonet-biscuit-v2.0.0.zip",
    sha256="98297293701082bc7272efe077f941c56fc7b6e1f27ef6f2e93b6e4c6fc7b62d",
    size=55989416,
    url="https://xdaforums.com/attachments/amonet-biscuit-v2-0-0-zip.6383906/",
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


UNLOCK_TO_FIREOS6 = Unlock(
    author=RORTIZ2,
    device=BISCUIT,
    family="amonet",
    fastbricks={
        "2c3569d-20260617_045829": "bin/fastbrick-20260617.img",
        "41fb3ce-20221007_151724": "bin/fastbrick-20221007.img",
        AMONET_V2_LK: "bin/fastbrick-20221007.img",
    },
    layout=STOCK_LAYOUT,
    little_kernel=AMONET_V2_LK,
    payloads={"41fb3ce-20221007_151724": V2_0_0_SOURCE},
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
        Reboot(label="restarting into amonet's fastboot"),
        FastbootFlash(image="bin/twrp.img", label="write TWRP", target="recovery"),
        Reboot(into="recovery", label="reboot into recovery"),
    ),
    requires=frozenset({Feature.AB_SLOTS, Feature.BOOT0, Feature.RPMB}),
    source=V2_0_1_SOURCE,
    version="2.0.1",
)


UNLOCK_V2_FROM_BOOTROM = dataclasses.replace(
    UNLOCK_TO_FIREOS6, plan=(ClearBoot0Header(), *UNLOCK_TO_FIREOS6.plan)
)
CONFIG = DeviceConfig(
    bootrom_unlock=UNLOCK_V2_FROM_BOOTROM,
    builds=BUILDS,
    default_build=DEFAULT_BUILD,
    default_target=FIREOS6,
    device=BISCUIT,
    fastbrick=UNLOCK_TO_FIREOS6,
    fireos5_builds=frozenset({
        "5.4.2.7",
        "5.5.0.3",
        "5.5.0.3-1973",
        "5.5.3.1",
        "5.5.3.3",
        "5.5.3.6",
        "5.5.4.6",
        "5.5.4.9",
        "5.5.5.0",
        "5.5.5.4",
    }),
    fireos5_chain=FireOs5Chain(
        little_kernel=AMONET_V1_1_0_LK,
        recovery=BBOE_RECOVERY,
        twrp_version=BBOE_TWRP_VERSION,
        unlock=UNLOCK_FROM_BOOTROM,
    ),
    lk_values=frozenset({
        "0e1d0d9-20161018_220224",
        AMONET_V1_1_0_LK,
        "a828f29-20210822_210511",
        "beb022a-20211202_231918",
        "41fb3ce-20221007_151724",
        AMONET_V2_LK,
        "2c3569d-20260617_045829",
    }),
    targets=(
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
            goal=State.AMONET_FIREOS5_BBOE_BOOTED,
            installs=FireOs5(package=BUILDS["5.5.5.4"]),
            name=FIREOS5,
            summary="rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP"
            f" {BBOE_TWRP_VERSION}.",
            unlock=UNLOCK_TO_FIREOS5,
        ),
        Target(
            device=BISCUIT,
            goal=State.UNLOCKED_BOOTED,
            installs=FireOs6(build=DEFAULT_BUILD),
            name=FIREOS6,
            summary=f"boot-root.zip's root adb on Fire OS 6 {DEFAULT_BUILD}, installed"
            " over an older Fire OS 6, or over Fire OS 5.5.5.4 through Amazon's"
            " bridge build 4315, if need be, which keeps the Dot's setup;"
            " with --factory-reset, Fire OS 6"
            f" {DEFAULT_BUILD} with TWRP {V2_0_1_TWRP_VERSION}, with the Dot"
            " erased.",
            unlock=UNLOCK_TO_FIREOS6,
        ),
    ),
)
