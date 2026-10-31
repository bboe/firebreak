from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from firebreak.cache import CACHE, Download, fetch
from firebreak.ui import SESSION, passed

if TYPE_CHECKING:
    import pathlib


CDN = "https://d1s31zyz7dcc2d.cloudfront.net/"


def cdn_ota(*, no_way_back: bool = False, path: str, sha256: str) -> Download:
    return Download(
        name=path.rsplit(maxsplit=1, sep="/")[-1],
        no_way_back=no_way_back,
        sha256=sha256,
        url=CDN + path,
    )


def download(*, build: str, builds: dict[str, Download]) -> pathlib.Path:
    update = CACHE / builds[build].name
    if update in SESSION.verified:
        return update
    update = fetch(download=builds[build])
    if threading.current_thread() is threading.main_thread():
        passed(message=f"OTA {build} verified")
    return update
