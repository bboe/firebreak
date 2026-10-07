from __future__ import annotations

import hashlib
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
    def __init__(self, body: bytes, length: str | None = None) -> None:
        super().__init__(body)
        self.headers = {} if length is None else {"Content-Length": length}


@pytest.fixture
def cached(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    folder = tmp_path / "cache"
    monkeypatch.setattr(cache, "CACHE", folder)
    return folder


def item(source: pathlib.Path, *, folder: str = "") -> cache.Download:
    return cache.Download(
        folder=folder,
        name=source.name,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        url=source.as_uri(),
    )


def test_cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert cache.cache_dir() == tmp_path / "firebreak"
    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cache.cache_dir() == tmp_path / ".cache" / "firebreak"


def test_cache_dir_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    windows = types.SimpleNamespace(environ={"LOCALAPPDATA": str(tmp_path)}, name="nt")
    monkeypatch.setattr(cache, "os", windows)
    assert cache.cache_dir() == tmp_path / "firebreak"


def test_cache_note(
    cached: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache.cache_note()
    assert capsys.readouterr().out == ""
    cached.mkdir()
    (cached / "big").write_bytes(bytes(3_000_000))
    monkeypatch.setenv("HOME", str(cached.parent))
    cache.cache_note()
    assert capsys.readouterr().out.startswith("~/cache holds 3 MB of downloads")


def test_digest(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(BODY)
    assert cache.digest(kind="md5", path=path) == hashlib.md5(BODY).hexdigest()  # ruff: ignore[hashlib-insecure-hash-function]
    assert cache.digest(kind="sha256", limit=8, path=path) == (
        hashlib.sha256(BODY[:8]).hexdigest()
    )
    assert cache.digest(kind="sha256", limit=len(BODY) + 5, path=path) == (
        hashlib.sha256(BODY).hexdigest()
    )


def test_fetch(cached: pathlib.Path, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "zip.bin"
    source.write_bytes(BODY)
    download = item(source)
    path = cache.fetch(download)
    assert path == cached / "zip.bin"
    assert path.read_bytes() == BODY
    assert not (cached / "zip.bin.part").exists()
    source.unlink()
    assert cache.fetch(download) == path
    cache.SESSION.verified.clear()
    assert cache.fetch(download) == path


@pytest.mark.usefixtures("cached")
def test_fetch_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "zip.bin"
    source.write_bytes(BODY)
    download = item(source)
    wrong = download._replace(sha256="0" * 64)
    with pytest.raises(SystemExit, match="does not hash to"):
        cache.fetch(wrong)
    source.unlink()
    with pytest.raises(SystemExit, match=r"downloading zip\.bin failed"):
        cache.fetch(download)
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda *_, **__: Response(BODY, "999999")
    )
    with pytest.raises(SystemExit, match="stopped after 8000 of 999999 bytes"):
        cache.fetch(download)


def test_hold() -> None:
    lock = threading.Lock()
    with cache.hold(lock):
        assert lock.locked()
    assert not lock.locked()


def test_lock_for() -> None:
    first = cache.lock_for("key")
    assert cache.lock_for("key") is first
    assert cache.lock_for("other") is not first


def test_lock_for_one_lock_across_threads() -> None:
    found = []
    threads = [
        threading.Thread(target=lambda: found.append(cache.lock_for("shared")))
        for _ in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(map(id, found))) == 1


def test_move_old_caches(cached: pathlib.Path) -> None:
    old = cached.parent / "overdub-root"
    old.mkdir()
    (old / "kept").write_text("old")
    (old / "moved").write_text("old")
    cached.mkdir()
    (cached / "kept").write_text("new")
    cache.move_old_caches()
    assert (cached / "kept").read_text() == "new"
    assert (cached / "moved").read_text() == "old"
    assert (old / "kept").exists()
    (old / "kept").unlink()
    cache.move_old_caches()
    assert not old.exists()


@pytest.mark.parametrize(
    ("length", "want"),
    [
        (None, "0.0 MB"),
        ("8000", "8.0 of 8.0 KB (100%)"),
        (str(2 * 10**6), "0.0 of 2.0 MB (0%)"),
    ],
)
def test_save(
    capsys: pytest.CaptureFixture[str],
    length: str | None,
    monkeypatch: pytest.MonkeyPatch,
    want: str,
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    out = io.BytesIO()
    label = "downloading " + "x" * 80
    done, total = cache.save(label=label, out=out, response=Response(BODY, length))
    assert out.getvalue() == BODY
    assert (done, total) == (8000, int(length or 0))
    shown = capsys.readouterr().out
    assert want in shown
    assert "..." in shown
    assert shown.endswith("\n")


def test_save_quiet_off_a_tty(capsys: pytest.CaptureFixture[str]) -> None:
    out = io.BytesIO()
    assert cache.save(label="x", out=out, response=Response(BODY)) == (8000, 0)
    assert capsys.readouterr().out == ""


def test_unpack(cached: pathlib.Path, tmp_path: pathlib.Path) -> None:
    source = tmp_path / "amonet.zip"
    with zipfile.ZipFile(source, "w") as z:
        z.writestr("amonet/bin/lk.bin", b"lk")
    download = item(source, folder="v9")
    target = cache.unpack(download)
    assert target == cached / "v9" / "amonet"
    assert (target / "bin" / "lk.bin").read_bytes() == b"lk"
    (target / "bin" / "lk.bin").write_bytes(b"kept")
    assert cache.unpack(download) == target
    assert (target / "bin" / "lk.bin").read_bytes() == b"kept"
