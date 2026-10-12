from __future__ import annotations

import dataclasses
import http.client
import re
import threading
import urllib.request
from typing import TYPE_CHECKING

from firebreak.cache import CACHE, digest, save
from firebreak.ui import SESSION, FatalError, again, passed

if TYPE_CHECKING:
    import pathlib


DEFAULT_BUILD = "8149"


FTVDB = "https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/"


@dataclasses.dataclass(frozen=True)
class Build:
    date: str
    ftvdb_version: str
    md5: str
    ns: str
    number: str
    sha256: str


BUILDS = {
    "4315": Build(
        date="2023-11-20",
        ftvdb_version="6-5-5-5",
        md5="03c7c4dc338a93635dda0f5e1cd4e451",
        ns="NS6555",
        number="8087722874",
        sha256="c1ca33efd975cb8491ea9438eff95af559c632dd7ca75ff3b73facacce5f758a",
    ),
    "4405": Build(
        date="2023-01-21",
        ftvdb_version="6-5-5-6",
        md5="570f3f6b28f94323e01e95561c87887f",
        ns="NS6556",
        number="8289072516",
        sha256="6839b0a1e5c4f6aa57f89ea7ca67c85aa69f8fe32e5ddc252764b0d96be5bf69",
    ),
    "5041": Build(
        date="2023-04-06",
        ftvdb_version="6-5-0-5",
        md5="1a25d21e0363158fe0c14cb4d41b843e",
        ns="NS6505",
        number="8960323972",
        sha256="80d98d3b57bc654d435b384f096dea46edd2b86e9f8adaaf91a7b0c3001e9716",
    ),
    "6302": Build(
        date="2025-04-13",
        ftvdb_version="6-4-6-6",
        md5="62da0c58f8c3e5c8094f302346da754f",
        ns="NS6466",
        number="11712110212",
        sha256="6d395345b1d1db373f9d714172c2ac5de4b5dd3e52d1ed1c3f37c2f007537667",
    ),
    "8138": Build(
        date="2026-08-31",
        ftvdb_version="6574-1",
        md5="723886117a7a4a8a543c2ec955dcd54e",
        ns="NS65741",
        number="13222529668",
        sha256="d2a61dd2af1d322e9ecfb4643670fbe416bc2442410f1aebe9748e2438f6d55f",
    ),
    "8142": Build(
        date="2026-09-09",
        ftvdb_version="6574-1",
        md5="ead2ea9a9ca2fa1c708381a07c605356",
        ns="NS65741",
        number="13222530692",
        sha256="ed4ddb01cd53e38751bb6274ad1a8255043e0795843d6ac2d44cc2803b2179a0",
    ),
    "8146": Build(
        date="2026-09-17",
        ftvdb_version="6574-1",
        md5="8ca06ee4ef2806c974d2944b7fadd543",
        ns="NS65741",
        number="13222531716",
        sha256="90832e86498c5e803974c30359aea71c1129757be0ddc59d831a94b27f81487f",
    ),
    "8149": Build(
        date="2026-09-29",
        ftvdb_version="6574-1",
        md5="a01de630f6d943dddc9b751ae74bbb52",
        ns="NS65741",
        number="13222532484",
        sha256="4e00fc6d6e2bcf5146e502c7d14e67d2ab47b43c3dcca4e1e9439d24730a6c0b",
    ),
}


def download(*, build: str) -> pathlib.Path:
    build_details = BUILDS[build]
    CACHE.mkdir(exist_ok=True, parents=True)
    update = (
        CACHE / f"update-kindle-biscuit_puffin-{build_details.ns}_user_{build}"
        f"_{build_details.number.zfill(13)}.bin"
    )
    if update in SESSION.verified:
        return update
    if (
        not update.is_file()
        or digest(kind="sha256", path=update) != build_details.sha256
    ):
        page = (
            f"{FTVDB}{build_details.md5}-{build_details.number}-fire-os-{build_details.ftvdb_version}-{build_details.ns.lower()}"
            f"-{build}-{build_details.date}/"
        )
        request = urllib.request.Request(
            headers={"User-Agent": "Mozilla/5.0"}, url=page
        )
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            with urllib.request.urlopen(timeout=60, url=request) as response:
                links = re.findall(
                    pattern=r'https://[^"<> ]+\.bin',
                    string=response.read().decode(errors="replace"),
                )
            if not links:
                raise FatalError(message="no download link on " + page)
            part = CACHE / (update.name + ".part")
            response = urllib.request.urlopen(timeout=60, url=links[0])
            with response, part.open(mode="wb") as part_file:
                done, total = save(
                    destination=part_file,
                    label=f"downloading OTA {build}",
                    response=response,
                )
        except (OSError, http.client.HTTPException) as error:
            raise FatalError(message=f"the download failed: {error!r}") from error
        if total and done != total:
            raise FatalError(
                message=f"the download stopped after {done} of {total} bytes. "
                + again()
            )
        part.replace(target=update)
    if digest(kind="sha256", path=update) != build_details.sha256:
        raise FatalError(message=f"{update} does not hash to {build_details.sha256}")
    SESSION.verified.add(update)
    if threading.current_thread() is threading.main_thread():
        passed(message=f"OTA {build} verified")
    return update
