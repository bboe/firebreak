from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from firebreak.cache import Download
from firebreak.devices.biscuit import BISCUIT, UNLOCK_TO_FIREOS6, WRITE_KAERU
from firebreak.plugin import FireOs6, Target
from firebreak.states import State
from firebreak.targets import FIREOS6, STOCK
from firebreak.updates import cdn_ota

if TYPE_CHECKING:
    from firebreak.targets import Deprecated

BUILDS = {
    "6436": cdn_ota(
        path="2026/3/21/22138e24-4af9-483b-8b47-0420835a92fd/update-kindle-radar_puffin-NS6572_user_6436_0012718777476.bin",
        sha256="976e2761c5bb9e5d3d9a2b1b9bc2f2296b89a5b37057ab1780743aa075f2df48",
    ),
}
DEFAULT_BUILD = "6436"
DEFAULT_TARGET = FIREOS6
FIREOS6_BUILD = "6436"
LK_VALUES = frozenset({
    "59779ca-20220524_183401",
    "63cb91b-20221007_073612",
    "41fb3ce-20221007_153017",
})
RADAR = dataclasses.replace(
    BISCUIT,
    models=frozenset({"AEORD", "Echo (2nd Gen)"}),
    name="radar",
    product="RADAR",
    title="Echo (2nd Generation)",
)


SOURCE = Download(
    browser=True,
    directory="radar-v1.0.0",
    mirror=True,
    name="amonet-radar-v1.0.0.zip",
    sha256="ecdb07bc05a508532e5ffed77121592d492b1a91572839e0f17545421f398f1a",
    size=58531162,
    url="https://xdaforums.com/attachments/amonet-radar-v1-0-0-zip.6384242/",
)


AMONET_V1_0_0 = dataclasses.replace(
    UNLOCK_TO_FIREOS6,
    device=RADAR,
    fastbricks={"59779ca-20220524_183401": "bin/fastbrick-20220524.img"},
    little_kernel="",
    plan=tuple(
        dataclasses.replace(WRITE_KAERU, image="bin/radar-kaeru.bin")
        if step == WRITE_KAERU
        else step
        for step in UNLOCK_TO_FIREOS6.plan
    ),
    source=SOURCE,
    version="1.0.0",
)
FASTBRICK = AMONET_V1_0_0
TARGETS = (
    Target(
        device=RADAR,
        goal=State.STOCK_BOOTED,
        installs=FireOs6(build=None),
        name=STOCK,
        summary=f"Amazon's Fire OS {DEFAULT_BUILD}, which erases the whole Echo.",
        unlock=None,
        unproven=True,
    ),
    Target(
        device=RADAR,
        goal=State.AMONET_V2_BOOTED,
        installs=FireOs6(build=FIREOS6_BUILD),
        name=FIREOS6,
        summary="boot-root.zip's root adb on the Fire OS 6 already installed,"
        " which keeps the Echo's setup; with --factory-reset, amonet-radar v1.0.0's own"
        f" procedure: Fire OS 6 {FIREOS6_BUILD}, with the Echo erased.",
        unlock=AMONET_V1_0_0,
        unproven=True,
    ),
)
WAS_CALLED: dict[str, Deprecated] = {}
