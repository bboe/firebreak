from __future__ import annotations

import dataclasses
import hashlib
import http.client
import io
import threading
import urllib.request
from typing import TYPE_CHECKING

import pytest

from firebreak import updates
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

BODY = b"OTA" * 1000
LINK = "https://cdn.example/update-kindle-biscuit.bin"


class Response(io.BytesIO):
    def __init__(self, *, body: bytes, length: str | None = None) -> None:
        super().__init__(initial_bytes=body)
        self.headers = http.client.HTTPMessage()
        if length is not None:
            self.headers["Content-Length"] = length


@pytest.fixture
def build(*, monkeypatch: pytest.MonkeyPatch) -> updates.Build:
    details = dataclasses.replace(
        updates.BUILDS["8146"], sha256=hashlib.sha256(BODY).hexdigest()
    )
    monkeypatch.setitem(updates.BUILDS, "8146", details)
    return details


def served(
    *,
    body: bytes = BODY,
    length: str | None = None,
    monkeypatch: pytest.MonkeyPatch,
    page: bytes,
) -> list[str]:
    asked: list[str] = []

    def urlopen(*, timeout: float, url: str | urllib.request.Request) -> Response:
        del timeout
        if isinstance(url, urllib.request.Request):
            asked.append(url.full_url)
            return Response(body=page)
        asked.append(url)
        return Response(body=body, length=length)

    monkeypatch.setattr(name="urlopen", target=urllib.request, value=urlopen)
    return asked


@pytest.mark.usefixtures("build")
def test_a_build_checked_off_the_main_thread_says_nothing(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    served(monkeypatch=monkeypatch, page=LINK.encode())
    worker = threading.Thread(target=lambda: updates.download(build="8146"))
    worker.start()
    worker.join()
    assert capsys.readouterr().out == ""
    assert updates.SESSION.verified


def test_a_build_is_fetched_from_its_ftvdb_page(
    *,
    build: updates.Build,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = served(monkeypatch=monkeypatch, page=f'<a href="{LINK}">'.encode())
    update = updates.download(build="8146")
    assert update.read_bytes() == BODY
    assert update.name == (
        f"update-kindle-biscuit_puffin-{build.ns}_user_8146_00{build.number}.bin"
    )
    assert asked[0].startswith(updates.FTVDB + build.md5)
    assert asked[0].endswith(f"-8146-{build.date}/")
    assert asked[1] == LINK
    assert "OTA 8146 verified" in capsys.readouterr().out
    assert not (update.parent / (update.name + ".part")).exists()
    monkeypatch.setattr(
        name="urlopen", target=urllib.request, value=lambda **_: pytest.fail("fetched")
    )
    hashed = updates.digest
    monkeypatch.setattr(
        name="digest", target=updates, value=lambda **_: pytest.fail("hashed")
    )
    assert updates.download(build="8146") == update
    monkeypatch.setattr(name="digest", target=updates, value=hashed)
    updates.SESSION.verified.clear()
    assert updates.download(build="8146") == update


@pytest.mark.usefixtures("build")
def test_a_cached_build_with_the_wrong_hash_is_fetched_again(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = served(monkeypatch=monkeypatch, page=LINK.encode())
    first = updates.download(build="8146")
    first.write_bytes(b"damaged")
    updates.SESSION.verified.clear()
    assert updates.download(build="8146").read_bytes() == BODY
    assert len(asked) == 4


@pytest.mark.usefixtures("build")
def test_a_download_cut_short_stops_the_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    served(length="999999", monkeypatch=monkeypatch, page=LINK.encode())
    with pytest.raises(FatalError, match="stopped after 3000 of 999999 bytes"):
        updates.download(build="8146")


@pytest.mark.usefixtures("build")
def test_a_download_with_the_wrong_hash_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    served(body=b"wrong", monkeypatch=monkeypatch, page=LINK.encode())
    with pytest.raises(FatalError, match="does not hash to"):
        updates.download(build="8146")
    assert not updates.SESSION.verified


@pytest.mark.usefixtures("build")
def test_a_failed_download_stops_the_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**_: object) -> Response:
        raise http.client.RemoteDisconnected

    monkeypatch.setattr(name="urlopen", target=urllib.request, value=refuse)
    with pytest.raises(FatalError, match=r"the download failed: RemoteDisconnected\("):
        updates.download(build="8146")


def test_a_fire_os_5_build_is_fetched_by_its_pin(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    fetched: list[updates.Download] = []

    def fetch(*, download: updates.Download) -> pathlib.Path:
        fetched.append(download)
        return tmp_path / download.name

    monkeypatch.setattr(name="fetch", target=updates, value=fetch)
    update = updates.download(build="5.5.5.4")
    assert fetched == [updates.FIREOS]
    assert update == tmp_path / updates.FIREOS.name


@pytest.mark.usefixtures("build")
def test_a_page_with_no_link_stops_the_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    served(monkeypatch=monkeypatch, page=b"<html>gone</html>")
    with pytest.raises(FatalError, match=r"no download link on https://ftvdb\.com/"):
        updates.download(build="8146")


def test_every_build_has_whole_pins() -> None:
    for name, details in updates.BUILDS.items():
        assert name.isdigit()
        assert len(details.md5) == 32
        assert len(details.sha256) == 64
        assert details.ns.startswith("NS")
    for name, download in updates.FIREOS5_BUILDS.items():
        assert name.startswith("5.5.")
        assert len(download.sha256) == 64
        assert download.url.endswith("/" + download.name)


@pytest.mark.usefixtures("build")
def test_the_cache_is_made_where_it_is_missing(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="CACHE", target=updates, value=tmp_path / "a" / "b")
    served(monkeypatch=monkeypatch, page=LINK.encode())
    assert updates.download(build="8146").parent == tmp_path / "a" / "b"
