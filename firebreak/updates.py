from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from firebreak.cache import CACHE, Download, fetch
from firebreak.ui import SESSION, passed

if TYPE_CHECKING:
    import pathlib


BOOTROM_BUILDS = frozenset({"5.5.0.3"})
CDN = "https://d1s31zyz7dcc2d.cloudfront.net/"
DEFAULT_BUILD = "8149"
FIREOS5_BUILDS = frozenset({
    "5.5.0.3",
    "5.5.3.1",
    "5.5.4.6",
    "5.5.4.9",
    "5.5.5.0",
    "5.5.5.4",
})


def cdn_ota(*, path: str, sha256: str) -> Download:
    return Download(
        name=path.rsplit(maxsplit=1, sep="/")[-1], sha256=sha256, url=CDN + path
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


def download(*, build: str) -> pathlib.Path:
    update = CACHE / BUILDS[build].name
    if update in SESSION.verified:
        return update
    update = fetch(download=BUILDS[build])
    if threading.current_thread() is threading.main_thread():
        passed(message=f"OTA {build} verified")
    return update
