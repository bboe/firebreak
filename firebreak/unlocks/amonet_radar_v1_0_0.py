from __future__ import annotations

import dataclasses

from firebreak.cache import Download
from firebreak.devices import RADAR
from firebreak.unlocks.amonet_biscuit_v2_0_1 import AMONET_BISCUIT_V2_0_1, WRITE_KAERU

SOURCE = Download(
    directory="radar-v1.0.0",
    name="amonet-radar-v1.0.0.zip",
    sha256="ecdb07bc05a508532e5ffed77121592d492b1a91572839e0f17545421f398f1a",
    url="https://github.com/hkfuertes/amazon_device_radar/releases/download"
    "/radar-backup-20260918/amonet-radar-v1.0.0.zip",
)
AMONET_RADAR_V1_0_0 = dataclasses.replace(
    AMONET_BISCUIT_V2_0_1,
    device=RADAR,
    plan=tuple(
        dataclasses.replace(WRITE_KAERU, image="bin/radar-kaeru.bin")
        if step == WRITE_KAERU
        else step
        for step in AMONET_BISCUIT_V2_0_1.plan
    ),
    source=SOURCE,
    version="1.0.0",
)
