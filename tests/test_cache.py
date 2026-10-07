from __future__ import annotations

import dataclasses
import hashlib
import http.client
import io
import sys
import threading
import types
import urllib.request
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak import cache

if TYPE_CHECKING:
    import pathlib

BODY = b"firmware" * 1000


class Response(io.BytesIO):
    def __init__(self, *, body: bytes, length: str | None = None) -> None:
        super().__init__(initial_bytes=body)
        self.headers = http.client.HTTPMessage()
        if length is not None:
            self.headers["Content-Length"] = length


@pytest.fixture
def cached(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "cache"
    monkeypatch.setattr(name="CACHE", target=cache, value=folder)
    return folder


def item(*, folder: str = "", source: pathlib.Path) -> cache.Download:
    return cache.Download(
        folder=folder,
        name=source.name,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        url=source.as_uri(),
    )


def test_cache_dir(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setenv(name="XDG_CACHE_HOME", value=str(tmp_path))
    assert cache.cache_dir() == tmp_path / "firebreak"
    monkeypatch.delenv(name="XDG_CACHE_HOME")
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    assert cache.cache_dir() == tmp_path / ".cache" / "firebreak"


def test_cache_dir_windows(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    windows = types.SimpleNamespace(environ={"LOCALAPPDATA": str(tmp_path)}, name="nt")
    monkeypatch.setattr(name="os", target=cache, value=windows)
    assert cache.cache_dir() == tmp_path / "firebreak"


def test_cache_note(
    *,
    cached: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.cache_note()
    assert capsys.readouterr().out == ""
    cached.mkdir()
    (cached / "big").write_bytes(data=bytes(3_000_000))
    monkeypatch.setenv(name="HOME", value=str(cached.parent))
    cache.cache_note()
    assert capsys.readouterr().out.startswith("~/cache holds 3 MB of downloads")


def test_digest(*, tmp_path: pathlib.Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(data=BODY)
    assert cache.digest(kind="md5", path=path) == hashlib.md5(BODY).hexdigest()  # ruff: ignore[hashlib-insecure-hash-function]
    assert cache.digest(kind="sha256", limit=8, path=path) == (
        hashlib.sha256(BODY[:8]).hexdigest()
    )
    assert cache.digest(kind="sha256", limit=len(BODY) + 5, path=path) == (
        hashlib.sha256(BODY).hexdigest()
    )


def test_fetch(*, cached: pathlib.Path, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "zip.bin"
    source.write_bytes(data=BODY)
    download = item(source=source)
    path = cache.fetch(download=download)
    assert path == cached / "zip.bin"
    assert path.read_bytes() == BODY
    assert not (cached / "zip.bin.part").exists()
    source.unlink()
    assert cache.fetch(download=download) == path
    cache.SESSION.verified.clear()
    assert cache.fetch(download=download) == path


@pytest.mark.usefixtures("cached")
def test_fetch_fails(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "zip.bin"
    source.write_bytes(data=BODY)
    download = item(source=source)
    wrong = dataclasses.replace(download, sha256="0" * 64)
    with pytest.raises(expected_exception=SystemExit, match="does not hash to"):
        cache.fetch(download=wrong)
    source.unlink()
    with pytest.raises(
        expected_exception=SystemExit, match=r"downloading zip\.bin failed"
    ):
        cache.fetch(download=download)
    monkeypatch.setattr(
        name="urlopen",
        target=urllib.request,
        value=lambda *_, **__: Response(body=BODY, length="999999"),
    )
    with pytest.raises(
        expected_exception=SystemExit, match="stopped after 8000 of 999999 bytes"
    ):
        cache.fetch(download=download)


def test_fetch_replaces_a_corrupt_copy(
    *, cached: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "zip.bin"
    source.write_bytes(data=BODY)
    cached.mkdir()
    (cached / "zip.bin").write_bytes(data=b"corrupt")
    (cached / "zip.bin.part").write_bytes(data=b"stale")
    assert cache.fetch(download=item(source=source)).read_bytes() == BODY
    assert not (cached / "zip.bin.part").exists()


def test_hold() -> None:
    lock = threading.Lock()
    with cache.hold(lock=lock):
        assert lock.locked()
    assert not lock.locked()


def test_lock_for() -> None:
    first = cache.lock_for(key="key")
    assert cache.lock_for(key="key") is first
    assert cache.lock_for(key="other") is not first


def test_lock_for_one_lock_across_threads() -> None:
    found = []
    threads = [
        threading.Thread(target=lambda: found.append(cache.lock_for(key="shared")))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(map(id, found))) == 1


def test_move_old_caches(*, cached: pathlib.Path) -> None:
    old = cached.parent / "overdub-root"
    old.mkdir()
    (old / "kept").write_text(data="old")
    (old / "moved").write_text(data="old")
    cached.mkdir()
    (cached / "kept").write_text(data="new")
    cache.move_old_caches()
    assert (cached / "kept").read_text() == "new"
    assert (cached / "moved").read_text() == "old"
    assert (old / "kept").exists()
    (old / "kept").unlink()
    cache.move_old_caches()
    assert not old.exists()


@pytest.mark.parametrize(
    argnames=("length", "want"),
    argvalues=[
        (None, "0.0 MB"),
        ("8000", "8.0 of 8.0 KB (100%)"),
        (str(2 * 10**6), "0.0 of 2.0 MB (0%)"),
    ],
)
def test_save(
    *,
    capsys: pytest.CaptureFixture[str],
    length: str | None,
    monkeypatch: pytest.MonkeyPatch,
    want: str,
) -> None:
    monkeypatch.setattr(name="isatty", target=sys.stdout, value=lambda: True)
    destination = io.BytesIO()
    label = "downloading " + "x" * 80
    done, total = cache.save(
        destination=destination,
        label=label,
        response=Response(body=BODY, length=length),
    )
    assert destination.getvalue() == BODY
    assert (done, total) == (8000, int(length or 0))
    shown = capsys.readouterr().out
    assert want in shown
    assert "..." in shown
    assert shown.endswith("\n")


def test_save_quiet_off_a_tty(*, capsys: pytest.CaptureFixture[str]) -> None:
    destination = io.BytesIO()
    assert cache.save(
        destination=destination, label="x", response=Response(body=BODY)
    ) == (
        8000,
        0,
    )
    assert capsys.readouterr().out == ""


def test_unpack(*, cached: pathlib.Path, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "amonet.zip"
    with zipfile.ZipFile(file=source, mode="w") as archive:
        archive.writestr(data=b"lk", zinfo_or_arcname="amonet/bin/lk.bin")
    download = item(folder="v9", source=source)
    target = cache.unpack(download=download)
    assert target == cached / "v9" / "amonet"
    assert (target / "bin" / "lk.bin").read_bytes() == b"lk"
    (target / "bin" / "lk.bin").write_bytes(data=b"kept")
    assert cache.unpack(download=download) == target
    assert (target / "bin" / "lk.bin").read_bytes() == b"kept"


def test_unpack_replaces_a_partial_extract(
    *, cached: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    source = tmp_path / "amonet.zip"
    with zipfile.ZipFile(file=source, mode="w") as archive:
        archive.writestr(data=b"lk", zinfo_or_arcname="amonet/bin/lk.bin")
    (cached / "v9.part" / "amonet").mkdir(parents=True)
    (cached / "v9.part" / "amonet" / "junk").write_bytes(data=b"junk")
    target = cache.unpack(download=item(folder="v9", source=source))
    assert sorted(path.name for path in target.rglob("*")) == ["bin", "lk.bin"]
    assert not (cached / "v9.part").exists()
