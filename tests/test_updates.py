from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from firebreak import updates
from firebreak.devices import biscuit

if TYPE_CHECKING:
    import pathlib


@pytest.fixture
def fetched(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> list[updates.Download]:
    asked: list[updates.Download] = []

    def fetch(*, download: updates.Download) -> pathlib.Path:
        asked.append(download)
        updates.SESSION.verified.add(updates.CACHE / download.name)
        return updates.CACHE / download.name

    monkeypatch.setattr(name="CACHE", target=updates, value=tmp_path)
    monkeypatch.setattr(name="fetch", target=updates, value=fetch)
    return asked


def test_a_build_checked_off_the_main_thread_says_nothing(
    *, capsys: pytest.CaptureFixture[str], fetched: list[updates.Download]
) -> None:
    def fetch_it() -> None:
        updates.download(build="8146", builds=biscuit.BUILDS)

    worker = threading.Thread(target=fetch_it)
    worker.start()
    worker.join()
    assert capsys.readouterr().out == ""
    assert fetched == [biscuit.BUILDS["8146"]]


def test_a_build_is_fetched_by_its_pin_once_a_session(
    *, capsys: pytest.CaptureFixture[str], fetched: list[updates.Download]
) -> None:
    update = updates.download(build="5.5.5.4", builds=biscuit.BUILDS)
    assert update == updates.CACHE / biscuit.BUILDS["5.5.5.4"].name
    assert "OTA 5.5.5.4 verified" in capsys.readouterr().out
    assert updates.download(build="5.5.5.4", builds=biscuit.BUILDS) == update
    assert fetched == [biscuit.BUILDS["5.5.5.4"]]
    assert capsys.readouterr().out == ""


def test_every_build_has_a_whole_pin_on_amazon_s_cdn() -> None:
    for download in biscuit.BUILDS.values():
        assert download.url.startswith(updates.CDN)
        assert download.url.endswith("/" + download.name)
        assert len(download.sha256) == 64
    assert set(biscuit.FIREOS5_BUILDS) <= set(biscuit.BUILDS)
