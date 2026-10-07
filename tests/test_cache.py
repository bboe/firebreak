from __future__ import annotations

import dataclasses
import hashlib
import http.client
import io
import os
import pathlib
import plistlib
import re
import subprocess
import sys
import threading
import types
import urllib.request
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak import cache

if TYPE_CHECKING:
    from collections.abc import Callable

BODY = b"firmware" * 1000
ROOT = pathlib.Path(__file__).resolve().parent.parent


XDA = "https://xdaforums.com/attachments/boot-root-zip.1/"


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


def archived(*, path: pathlib.Path) -> pathlib.Path:
    with zipfile.ZipFile(file=path, mode="w") as archive:
        archive.writestr(data=b"", zinfo_or_arcname="empty/")
        archive.writestr(data=b"script", zinfo_or_arcname="META-INF/update-binary")
        archive.writestr(data=b"rules", zinfo_or_arcname="patch/sepolicy.rules")
    return path


def browser_item() -> cache.Download:
    return cache.Download(
        browser=True,
        name="boot-root.zip",
        sha256=hashlib.sha256(BODY).hexdigest(),
        size=len(BODY),
        url=XDA,
    )


def item(*, folder: str = "", source: pathlib.Path) -> cache.Download:
    return cache.Download(
        folder=folder,
        name=source.name,
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        url=source.as_uri(),
    )


def quiet_browser() -> types.SimpleNamespace:
    return types.SimpleNamespace(name="firefox", open=lambda **_: True)


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


@pytest.mark.parametrize(
    argnames=("platform", "searched"), argvalues=[("darwin", True), ("linux", False)]
)
def test_copies_looks_in_the_trash_on_macos(
    *,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    searched: bool,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value=platform)
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    trash = tmp_path / ".Trash"
    trash.mkdir()
    (trash / "boot-root.zip 12-19-07-221.zip").write_bytes(data=BODY)
    found = cache.copies(checked=set(), download=browser_item())
    assert found == ([trash / "boot-root.zip 12-19-07-221.zip"] if searched else [])


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


def test_discard_skips_what_it_cannot_remove(
    *, capsys: pytest.CaptureFixture[str], tmp_path: pathlib.Path
) -> None:
    cache.discard(paths=[tmp_path / "gone.zip"])
    assert capsys.readouterr().out == ""


def test_discard_unpacked_reports_what_it_cannot_remove(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    (tmp_path / "boot-root").mkdir()
    monkeypatch.setattr(name="holds_only", target=cache, value=lambda **_: True)

    def rmtree(path: pathlib.Path) -> None:
        raise PermissionError(path)

    monkeypatch.setattr(name="rmtree", target=cache.shutil, value=rmtree)
    cache.discard_unpacked(archive=tmp_path / "x.zip", before=set(), directory=tmp_path)
    out = " ".join(capsys.readouterr().out.split())
    assert f"could not remove {tmp_path / 'boot-root'}" in out


def test_download_origin_on_linux(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="linux")
    attributes = {str(tmp_path / "a.zip"): b"https://xdaforums.com/a/"}

    def getxattr(path: pathlib.Path, attribute: str) -> bytes:
        assert attribute == "user.xdg.origin.url"
        try:
            return attributes[str(path)]
        except KeyError:
            raise OSError from None

    monkeypatch.setattr(
        name="os",
        target=cache,
        value=types.SimpleNamespace(getxattr=getxattr, name="posix"),
    )
    assert cache.download_origin(path=tmp_path / "a.zip") == "https://xdaforums.com/a/"
    assert cache.download_origin(path=tmp_path / "b.zip") is None
    monkeypatch.setattr(
        name="os", target=cache, value=types.SimpleNamespace(name="posix")
    )
    assert cache.download_origin(path=tmp_path / "a.zip") is None


def test_download_origin_on_macos(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    dumps = {
        "a.zip": plistlib.dumps(
            ["https://xdaforums.com/a/", "https://xdaforums.com/t/"],
            fmt=plistlib.FMT_BINARY,
        ).hex(" "),
        "broken-xml.zip": b"<?xml version='1.0'?><plist><array><string>x</arr".hex(),
        "list-of-numbers.zip": plistlib.dumps([1], fmt=plistlib.FMT_BINARY).hex(),
        "not-a-plist.zip": "00ff",
    }
    calls = []

    def run(*, args: list[str], **options: object) -> types.SimpleNamespace:
        calls.append((args, options))
        name = pathlib.Path(args[-1]).name
        if name not in dumps:
            raise subprocess.CalledProcessError(cmd=args, returncode=1)
        return types.SimpleNamespace(stdout=dumps[name])

    monkeypatch.setattr(name="run", target=cache.subprocess, value=run)
    assert cache.download_origin(path=tmp_path / "a.zip") == "https://xdaforums.com/a/"
    assert calls[0][0][:3] == ["/usr/bin/xattr", "-px", cache.WHERE_FROMS]
    for name in (
        "broken-xml.zip",
        "list-of-numbers.zip",
        "missing.zip",
        "not-a-plist.zip",
    ):
        assert cache.download_origin(path=tmp_path / name) is None


def test_download_origin_on_windows(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="win32")
    monkeypatch.setattr(name="os", target=cache, value=types.SimpleNamespace(name="nt"))
    (tmp_path / "a.zip:Zone.Identifier").write_text(
        data="[ZoneTransfer]\nZoneId=3\nHostUrl=https://xdaforums.com/a/\n"
    )
    (tmp_path / "b.zip:Zone.Identifier").write_text(data="[ZoneTransfer]\nZoneId=3\n")
    assert cache.download_origin(path=tmp_path / "a.zip") == "https://xdaforums.com/a/"
    assert cache.download_origin(path=tmp_path / "b.zip") is None
    assert cache.download_origin(path=tmp_path / "c.zip") is None


def test_downloaded_skips_a_directory_it_cannot_list(*, tmp_path: pathlib.Path) -> None:
    (tmp_path / "a-file").write_bytes(data=BODY)
    for directory in (tmp_path / "missing", tmp_path / "a-file"):
        assert (
            cache.downloaded(
                checked=set(), directory=directory, download=browser_item()
            )
            == []
        )


def test_downloaded_skips_what_it_cannot_read(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    (tmp_path / "locked.zip").write_bytes(data=BODY)
    (tmp_path / "open.zip").write_bytes(data=BODY)
    real_digest = cache.digest

    def digest(*, path: pathlib.Path, **options: object) -> str:
        if path.name == "locked.zip":
            raise PermissionError(path)
        return real_digest(path=path, **options)

    monkeypatch.setattr(name="digest", target=cache, value=digest)
    found = cache.downloaded(checked=set(), directory=tmp_path, download=browser_item())
    assert found == [tmp_path / "open.zip"]


def test_downloads_dir(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    assert cache.downloads_dir() == tmp_path / "Downloads"


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
    assert list(cache.CACHE.iterdir()) == []
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
    assert list(cache.CACHE.iterdir()) == []


def test_fetch_from_the_browser(
    *,
    cached: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    downloads = tmp_path / "Downloads"
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(name="download_origin", target=cache, value=lambda **_: None)
    opened = []
    monkeypatch.setattr(
        name="get",
        target=cache.webbrowser,
        value=lambda: types.SimpleNamespace(
            name="windows-default",
            open=lambda **options: opened.append(options) or True,
        ),
    )
    arrivals = iter((
        downloads.mkdir,
        lambda: (
            (downloads / "boot-root.zip.crdownload").write_bytes(data=BODY),
            (downloads / "284ee1de.tmp").write_bytes(data=BODY),
        ),
        lambda: (downloads / "boot-root(1).zip").write_bytes(data=BODY[:-1] + b"x"),
        lambda: (downloads / "boot-root(1).zip").write_bytes(data=BODY),
    ))
    monkeypatch.setattr(
        name="sleep", target=cache.time, value=lambda _: next(arrivals)()
    )
    path = cache.fetch(download=browser_item())
    assert path == cached / "boot-root.zip"
    assert path.read_bytes() == BODY
    assert not (cached / "boot-root.zip.part").exists()
    assert opened == [{"url": "https://xdaforums.com/attachments/boot-root-zip.1/"}]
    assert next(arrivals, None) is None
    assert sorted(child.name for child in downloads.iterdir()) == [
        "284ee1de.tmp",
        "boot-root.zip.crdownload",
    ]
    out = capsys.readouterr().out
    assert "boot-root.zip is an XDA attachment" in out
    assert hashlib.sha256(BODY).hexdigest() in out
    assert "https://xdaforums.com/attachments/boot-root-zip.1/" in out
    assert "boot-root.zip verified" in out
    assert f"removed {downloads / 'boot-root(1).zip'}" in out


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_checks_its_copy(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "boot-root.zip").write_bytes(data=BODY)
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(
        name="copyfile",
        target=cache.shutil,
        value=lambda *, dst, **_: dst.write_bytes(data=b"short"),
    )
    with pytest.raises(expected_exception=SystemExit, match="does not hash to the pin"):
        cache.fetch(download=browser_item())
    assert (downloads / "boot-root.zip").read_bytes() == BODY
    assert list(cache.CACHE.iterdir()) == []


def test_fetch_from_the_browser_finds_an_earlier_download(
    *,
    cached: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "boot-root.zip").write_bytes(data=b"another release")
    (downloads / "boot-root (2).zip").mkdir()
    (downloads / "boot-root (3).zip").symlink_to(target=tmp_path / "missing")
    (downloads / "boot-root (4).zip").write_bytes(data=BODY)
    (downloads / "lookalike.bin").write_bytes(data=BODY[:-1] + b"x")
    (downloads / "renamed.zip").write_bytes(data=BODY)
    (downloads / "still-going.zip.part").write_bytes(data=BODY)
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    hashed = []
    real_digest = cache.digest

    def recording_digest(**options: object) -> str:
        hashed.append(options["path"].name)
        return real_digest(**options)

    monkeypatch.setattr(name="digest", target=cache, value=recording_digest)
    path = cache.fetch(download=browser_item())
    assert path == cached / "boot-root.zip"
    assert path.read_bytes() == BODY
    assert sorted(child.name for child in downloads.iterdir()) == [
        "boot-root (2).zip",
        "boot-root (3).zip",
        "boot-root.zip",
        "lookalike.bin",
        "still-going.zip.part",
    ]
    assert "boot-root.zip" not in hashed
    assert "still-going.zip.part" not in hashed
    assert "lookalike.bin" in hashed
    out = capsys.readouterr().out
    assert "XDA attachment" not in out
    assert out.count("removed") == 2


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_gives_up(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "lookalike.bin").write_bytes(data=BODY[:-1] + b"x")
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    hashed = []
    real_digest = cache.digest

    def recording_digest(**options: object) -> str:
        hashed.append(options["path"])
        return real_digest(**options)

    monkeypatch.setattr(name="digest", target=cache, value=recording_digest)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    now = [0.0]
    monkeypatch.setattr(name="monotonic", target=cache.time, value=lambda: now[0])
    sleeps = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(name="sleep", target=cache.time, value=sleep)
    with pytest.raises(expected_exception=SystemExit) as stopped:
        cache.fetch(download=browser_item())
    assert (
        f"boot-root.zip did not reach {downloads} in 2 minutes. Download it from"
        f" https://xdaforums.com/attachments/boot-root-zip.1/ into {downloads}."
    ) in " ".join(str(stopped.value).split())
    assert sum(sleeps) == 122
    assert set(sleeps) == {2}
    assert hashed == [downloads / "lookalike.bin"]


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_keeps_a_file_it_could_not_hash_at_first(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    monkeypatch.setattr(name="download_origin", target=cache, value=lambda **_: XDA)
    locked = [2]
    real_digest = cache.digest

    def digest(*, path: pathlib.Path, **options: object) -> str:
        if path.parent == downloads and locked[0]:
            locked[0] -= 1
            raise PermissionError(path)
        return real_digest(path=path, **options)

    monkeypatch.setattr(name="digest", target=cache, value=digest)
    arrivals = iter((
        lambda: (downloads / "boot-root.zip").write_bytes(data=BODY),
        lambda: None,
        lambda: None,
    ))
    monkeypatch.setattr(
        name="sleep", target=cache.time, value=lambda _: next(arrivals)()
    )
    assert cache.fetch(download=browser_item()).read_bytes() == BODY
    assert locked == [0]


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_keeps_directories_unless_it_came_from_the_trash(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    archive = archived(path=tmp_path / "source.zip")
    body = archive.read_bytes()
    download = dataclasses.replace(
        browser_item(), sha256=hashlib.sha256(body).hexdigest(), size=len(body)
    )
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    monkeypatch.setattr(name="download_origin", target=cache, value=lambda **_: None)

    def chrome(_: float) -> None:
        (downloads / "boot-root.zip").write_bytes(data=body)
        with zipfile.ZipFile(file=archive) as zip_file:
            zip_file.extractall(path=downloads / "boot-root")

    monkeypatch.setattr(name="sleep", target=cache.time, value=chrome)
    cache.fetch(download=download)
    assert sorted(child.name for child in downloads.iterdir()) == ["boot-root"]


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_leaves_what_it_cannot_trace(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    sources = {downloads / "notes.zip": "https://example.com/notes.zip"}
    monkeypatch.setattr(
        name="download_origin", target=cache, value=lambda *, path: sources.get(path)
    )
    now = [0.0]
    monkeypatch.setattr(name="monotonic", target=cache.time, value=lambda: now[0])

    def sleep(seconds: float) -> None:
        if now[0] == 0:
            (downloads / "boot-root.zip").write_bytes(data=b"a newer release")
            (downloads / "notes.zip").write_bytes(data=b"mine")
        now[0] += seconds

    monkeypatch.setattr(name="sleep", target=cache.time, value=sleep)
    with pytest.raises(expected_exception=SystemExit) as stopped:
        cache.fetch(download=browser_item())
    message = " ".join(str(stopped.value).split())
    assert (
        "These arrived with no record of their source, and were left:"
        f" {downloads / 'boot-root.zip'}. Download it from"
    ) in message
    assert "notes.zip" not in message
    assert sorted(child.name for child in downloads.iterdir()) == [
        "boot-root.zip",
        "notes.zip",
    ]


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_needs_a_browser(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_browser() -> None:
        raise cache.webbrowser.Error

    monkeypatch.setattr(name="get", target=cache.webbrowser, value=no_browser)
    with pytest.raises(expected_exception=SystemExit) as stopped:
        cache.fetch(download=browser_item())
    message = " ".join(str(stopped.value).split())
    assert f"None is available here. Download it from {XDA} on any computer" in message
    assert "opens next" not in capsys.readouterr().out


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_needs_it_to_open(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="get",
        target=cache.webbrowser,
        value=lambda: types.SimpleNamespace(name="default", open=lambda **_: False),
    )
    monkeypatch.setattr(name="sleep", target=cache.time, value=waited)
    with pytest.raises(expected_exception=SystemExit) as stopped:
        cache.fetch(download=browser_item())
    assert f"the browser did not open {XDA}." in " ".join(str(stopped.value).split())


@pytest.mark.skipif(
    condition=os.geteuid() == 0, reason="root reads what its modes forbid"
)
@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_points_at_a_trash_it_cannot_read(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    (tmp_path / "Downloads").mkdir()
    trash = tmp_path / ".Trash"
    trash.mkdir()
    trash.chmod(0o000)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    now = [0.0]
    monkeypatch.setattr(name="monotonic", target=cache.time, value=lambda: now[0])
    monkeypatch.setattr(
        name="sleep",
        target=cache.time,
        value=lambda seconds: now.append(now.pop() + seconds),
    )
    try:
        with pytest.raises(expected_exception=SystemExit) as stopped:
            cache.fetch(download=browser_item())
    finally:
        trash.chmod(0o700)
    assert "This terminal cannot read the Trash" in " ".join(str(stopped.value).split())


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_removes_a_wrong_download(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "boot-root (2).zip").write_bytes(data=b"from last week")
    (downloads / "abandoned.zip.crdownload").write_bytes(data=b"half")
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    placeholder = downloads / "boot-root.zip"
    sources = {
        downloads / "boot-root (2).zip": XDA,
        downloads / "notes.zip": "https://example.com/notes.zip",
        placeholder: XDA,
    }
    asked = []

    def origin(*, path: pathlib.Path) -> str | None:
        asked.append(path.name)
        return sources.get(path)

    monkeypatch.setattr(name="download_origin", target=cache, value=origin)
    in_progress = downloads / "other.zip.crdownload"
    arrivals = iter((
        lambda: (
            placeholder.write_bytes(data=b""),
            (downloads / "notes.zip").write_bytes(data=b"mine"),
        ),
        lambda: (downloads / "boot-root.zip.part").write_bytes(data=b"new"),
        (downloads / "boot-root.zip.part").unlink,
        lambda: placeholder.write_bytes(data=b"a newer release"),
        lambda: in_progress.write_bytes(data=b"unrelated"),
        lambda: in_progress.rename(target=downloads / "other.zip"),
    ))
    monkeypatch.setattr(
        name="sleep", target=cache.time, value=lambda _: next(arrivals)()
    )
    with pytest.raises(expected_exception=SystemExit) as stopped:
        cache.fetch(download=browser_item())
    message = " ".join(str(stopped.value).split())
    assert f"{XDA} gave {placeholder} with the sha256" in message
    assert hashlib.sha256(b"a newer release").hexdigest() in message
    assert next(arrivals, None) is None
    assert asked == ["notes.zip", "boot-root.zip"]
    assert sorted(child.name for child in downloads.iterdir()) == [
        "abandoned.zip.crdownload",
        "boot-root (2).zip",
        "notes.zip",
        "other.zip",
    ]


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_removes_what_safari_unpacked(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    downloads, trash = tmp_path / "Downloads", tmp_path / ".Trash"
    downloads.mkdir()
    trash.mkdir()
    archive = archived(path=tmp_path / "source.zip")
    with zipfile.ZipFile(file=archive) as zip_file:
        zip_file.extractall(path=downloads / "boot-root")
    body = archive.read_bytes()
    download = dataclasses.replace(
        browser_item(), sha256=hashlib.sha256(body).hexdigest(), size=len(body)
    )
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)
    monkeypatch.setattr(name="download_origin", target=cache, value=lambda **_: None)

    def safari(_: float) -> None:
        (trash / "boot-root.zip 12-19-07-221.zip").write_bytes(data=body)
        with zipfile.ZipFile(file=archive) as zip_file:
            zip_file.extractall(path=downloads / "boot-root 2")
            zip_file.extractall(path=downloads / "boot-root 3")
        (downloads / "boot-root 3" / ".DS_Store").write_bytes(data=b"x")
        (downloads / "boot-root 4.zip").write_bytes(data=b"not a directory")
        with zipfile.ZipFile(file=archive) as zip_file:
            zip_file.extractall(path=tmp_path / "elsewhere")
        (downloads / "boot-root 5").symlink_to(target=tmp_path / "elsewhere")

    monkeypatch.setattr(name="sleep", target=cache.time, value=safari)
    assert cache.fetch(download=download).read_bytes() == body
    assert sorted(child.name for child in downloads.iterdir()) == [
        "boot-root",
        "boot-root 3",
        "boot-root 4.zip",
        "boot-root 5",
    ]
    assert (tmp_path / "elsewhere" / "patch" / "sepolicy.rules").exists()
    assert list(trash.iterdir()) == []
    assert f"removed {downloads / 'boot-root 2'}, which the browser unpacked" in (
        capsys.readouterr().out
    )


@pytest.mark.usefixtures("cached")
def test_fetch_from_the_browser_survives_a_vanished_file(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=quiet_browser)

    def download_origin(*, path: pathlib.Path) -> str:
        path.unlink()
        return XDA

    monkeypatch.setattr(name="download_origin", target=cache, value=download_origin)
    now = [0.0]
    monkeypatch.setattr(name="monotonic", target=cache.time, value=lambda: now[0])

    def sleep(seconds: float) -> None:
        if now[0] == 0:
            (downloads / "boot-root.zip").write_bytes(data=b"a newer release")
        now[0] += seconds

    monkeypatch.setattr(name="sleep", target=cache.time, value=sleep)
    with pytest.raises(expected_exception=SystemExit, match="did not reach"):
        cache.fetch(download=browser_item())


@pytest.mark.usefixtures("cached")
def test_fetch_keeps_directories_when_the_trash_already_held_it(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="platform", target=sys, value="darwin")
    monkeypatch.setenv(name="HOME", value=str(tmp_path))
    downloads, trash = tmp_path / "Downloads", tmp_path / ".Trash"
    trash.mkdir()
    archive = archived(path=trash / "boot-root.zip")
    with zipfile.ZipFile(file=archive) as zip_file:
        zip_file.extractall(path=downloads / "boot-root")
    body = archive.read_bytes()
    download = dataclasses.replace(
        browser_item(), sha256=hashlib.sha256(body).hexdigest(), size=len(body)
    )
    cache.fetch(download=download)
    assert [child.name for child in downloads.iterdir()] == ["boot-root"]
    assert list(trash.iterdir()) == []


def test_fetch_removes_copies_of_what_the_cache_holds(
    *, cached: pathlib.Path, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    monkeypatch.setattr(name="downloads_dir", target=cache, value=lambda: downloads)
    cached.mkdir()
    (cached / "boot-root.zip").write_bytes(data=BODY)
    (cached / "zip.bin").write_bytes(data=b"other")
    (downloads / "boot-root.zip").write_bytes(data=BODY)
    (downloads / "zip.bin").write_bytes(data=b"other")
    assert cache.fetch(download=browser_item()) == cached / "boot-root.zip"
    assert not (downloads / "boot-root.zip").exists()
    (downloads / "boot-root.zip").write_bytes(data=BODY)
    assert cache.fetch(download=browser_item()) == cached / "boot-root.zip"
    assert (downloads / "boot-root.zip").exists()
    assert cache.fetch(download=item(source=downloads / "zip.bin")) == (
        cached / "zip.bin"
    )
    assert (downloads / "zip.bin").exists()


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


def test_graphical_browser_skips_a_text_browser(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    for browser, usable in (
        (cache.webbrowser.GenericBrowser(name="w3m"), False),
        (cache.webbrowser.Elinks(name="elinks"), False),
        (cache.webbrowser.BackgroundBrowser(name="xdg-open"), True),
        (cache.webbrowser.Mozilla(name="firefox"), True),
    ):
        monkeypatch.setattr(
            name="get", target=cache.webbrowser, value=lambda b=browser: b
        )
        assert (cache.graphical_browser() is browser) is usable


def test_hold() -> None:
    lock = threading.Lock()
    with cache.hold(lock=lock):
        assert lock.locked()
    assert not lock.locked()


@pytest.mark.parametrize(
    argnames=("change", "holds"),
    argvalues=[
        (lambda _: None, True),
        (lambda directory: (directory / ".DS_Store").write_bytes(data=b"x"), False),
        (
            lambda directory: (directory / "patch" / "sepolicy.rules").write_bytes(
                data=b"x"
            ),
            False,
        ),
        (lambda directory: (directory / "patch" / "sepolicy.rules").unlink(), False),
        (lambda directory: (directory / "empty").rmdir(), False),
        (lambda directory: (directory / "extra").mkdir(), False),
        (
            lambda directory: (directory / "link").symlink_to(
                target=directory / "patch"
            ),
            False,
        ),
        (
            lambda directory: (
                (directory.parent / "rules").write_bytes(data=b"rules"),
                (directory / "patch" / "sepolicy.rules").unlink(),
                (directory / "patch" / "sepolicy.rules").symlink_to(
                    target=directory.parent / "rules"
                ),
            ),
            False,
        ),
    ],
)
def test_holds_only(
    *, change: Callable[[pathlib.Path], object], holds: bool, tmp_path: pathlib.Path
) -> None:
    archive = archived(path=tmp_path / "boot-root.zip")
    unpacked = tmp_path / "boot-root"
    with zipfile.ZipFile(file=archive) as zip_file:
        zip_file.extractall(path=unpacked)
    change(unpacked)
    assert cache.holds_only(archive=archive, unpacked=unpacked) is holds


@pytest.mark.skipif(
    condition=os.geteuid() == 0, reason="root reads what its modes forbid"
)
@pytest.mark.parametrize(
    argnames="change",
    argvalues=[
        lambda directory: (directory / "empty").chmod(0o300),
        lambda directory: (directory / "patch" / "sepolicy.rules").chmod(0o000),
        lambda directory: (
            (directory / "patch" / "sepolicy.rules").unlink(),
            os.mkfifo(directory / "patch" / "sepolicy.rules"),
        ),
    ],
)
def test_holds_only_fails_closed(
    *, change: Callable[[pathlib.Path], object], tmp_path: pathlib.Path
) -> None:
    archive = archived(path=tmp_path / "boot-root.zip")
    unpacked = tmp_path / "boot-root"
    with zipfile.ZipFile(file=archive) as zip_file:
        zip_file.extractall(path=unpacked)
    change(unpacked)
    try:
        assert not cache.holds_only(archive=archive, unpacked=unpacked)
    finally:
        (unpacked / "empty").chmod(0o700)
        (unpacked / "patch" / "sepolicy.rules").chmod(0o600)


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


def test_pyserial_pin_matches_the_download() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    pinned = re.search(
        flags=re.MULTILINE,
        pattern=r'^dependencies = \["pyserial==([^"]+)"\]$',
        string=pyproject,
    )
    assert pinned, "pyproject.toml does not pin pyserial"
    wheel = f"pyserial-{pinned[1]}-py2.py3-none-any.whl"
    assert cache.PYSERIAL.name == wheel
    assert cache.PYSERIAL.url.endswith("/" + wheel)


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


def test_served_skips_a_file_that_vanished(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="names_in", target=cache, value=lambda **_: {"gone.zip"})
    monkeypatch.setattr(name="is_file", target=pathlib.Path, value=lambda _: True)
    assert (
        cache.served(before=set(), directory=tmp_path, judged=set(), settled={}) == []
    )


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


def waited(_: float) -> None:
    message = "the run waited for a browser that did not open"
    raise AssertionError(message)
