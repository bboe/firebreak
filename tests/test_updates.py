from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from firebreak import updates
from firebreak.devices import BUILDS, DEFAULT_BUILDS, biscuit

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
    for device, builds in BUILDS.items():
        for download in builds.values():
            assert download.url.startswith(updates.CDN)
            assert download.url.endswith("/" + download.name)
            assert device.name in download.name
            assert len(download.sha256) == 64
        assert DEFAULT_BUILDS[device] in builds
    assert set(biscuit.FIREOS5_BUILDS) <= set(biscuit.BUILDS)


def test_no_device_defaults_to_a_build_that_ends_in_the_bootrom() -> None:
    ends_there = {
        device.name
        for device, build in DEFAULT_BUILDS.items()
        if build in biscuit.BOOTROM_BUILDS
    }
    assert not ends_there, (
        f"{ends_there} now defaults to a build whose restore ends in the"
        " bootrom. The --fastboot refusal reads the build typed on the command"
        " line, not the one a run settles on once it knows the device, so that"
        " check has to move to where the build is settled before this holds."
    )


def test_nothing_keyed_by_build_alone_has_a_collision_yet() -> None:
    numbers = [build for builds in BUILDS.values() for build in builds]
    assert len(numbers) == len(set(numbers)), (
        "two devices now share a build number, which docs/rooting.md says they"
        " do. Nothing keyed by the build alone can tell them apart yet: the"
        " stock-<build> work folder, the lock a build download holds, and the"
        " one set of BUILD choices on the command line would each take one"
        " device's build for the other's. Key those by device first."
    )
