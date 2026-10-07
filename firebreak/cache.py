from __future__ import annotations

import contextlib
import hashlib
import http.client
import os
import pathlib
import shutil
import sys
import threading
import urllib.request
import zipfile
from typing import TYPE_CHECKING, BinaryIO, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Generator

from firebreak.ui import SESSION, _die, again, show

LOCKS: dict[object, threading.Lock] = {}
LOCKS_GUARD = threading.Lock()
MEGA = 1e6


class Download(NamedTuple):
    name: str
    sha256: str
    url: str
    folder: str = ""


MAGISK = Download(
    name="Magisk-v17.3.zip",
    sha256="18e46b16b25ebe691c282fe311beccd4811cd533848a64e2efbd754fb85efde7",
    url="https://github.com/topjohnwu/Magisk/releases/download/v17.3/Magisk-v17.3.zip",
)
PYSERIAL = Download(
    name="pyserial-3.5-py2.py3-none-any.whl",
    sha256="c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0",
    url="https://files.pythonhosted.org/packages/07/bc/"
    "587a445451b253b285629263eb51c2d8e9bcea4fc97826266d186f96f558/pyserial-3.5-py2.py3-none-any.whl",
)


def cache_dir() -> pathlib.Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or pathlib.Path.home()
    else:
        base = os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home() / ".cache"
    return pathlib.Path(base) / "firebreak"


CACHE = cache_dir()
ERASED = CACHE / "boot0-erased"


def cache_note() -> None:
    if CACHE.is_dir():
        size = sum(f.stat().st_size for f in CACHE.rglob("*") if f.is_file())
        path, home = str(CACHE), str(pathlib.Path.home())
        if os.name != "nt" and path.startswith(home + os.sep):
            path = "~" + path[len(home) :]
        show(
            text=f"{path} holds {size // 1000000} MB of downloads and images for"
            " the next run. It is safe to delete."
        )


def digest(*, kind: str, limit: int = 0, path: pathlib.Path) -> str:
    h = hashlib.new(kind, usedforsecurity=False)
    left = limit or path.stat().st_size
    with path.open("rb") as f:
        while left > 0:
            block = f.read(min(1 << 20, left))
            if not block:
                break
            left -= len(block)
            h.update(block)
    return h.hexdigest()


def fetch(download: Download) -> pathlib.Path:
    name, want = download.name, download.sha256
    with hold(lock_for(download)):
        CACHE.mkdir(exist_ok=True, parents=True)
        path = CACHE / name
        if path in SESSION.verified or (
            path.is_file() and digest(kind="sha256", path=path) == want
        ):
            SESSION.verified.add(path)
            return path
        part = CACHE / (name + ".part")
        try:
            with urllib.request.urlopen(download.url, timeout=60) as response:  # ruff: ignore[multiple-with-statements]
                with part.open("wb") as out:
                    done, total = save(
                        label="downloading " + name, out=out, response=response
                    )
        except (OSError, http.client.HTTPException) as error:
            _die(message=f"downloading {name} failed: {error!r}")
        if total and done != total:
            _die(
                message=f"downloading {name} stopped after {done} of {total} bytes. "
                + again()
            )
        if digest(kind="sha256", path=part) != want:
            _die(message=f"{name} does not hash to {want}")
        part.replace(path)
        SESSION.verified.add(path)
        return path


@contextlib.contextmanager
def hold(lock: threading.Lock) -> Generator[None, None, None]:
    while not lock.acquire(timeout=0.5):
        pass
    try:
        yield
    finally:
        lock.release()


def lock_for(key: object) -> threading.Lock:
    with LOCKS_GUARD:
        return LOCKS.setdefault(key, threading.Lock())


def move_old_caches() -> None:
    for old in ("overdub-firmware", "overdub-root", "overdub-stock"):
        source = CACHE.parent / old
        if not source.is_dir():
            continue
        CACHE.mkdir(exist_ok=True, parents=True)
        for path in source.iterdir():
            if not (CACHE / path.name).exists():
                with contextlib.suppress(OSError):
                    shutil.move(str(path), str(CACHE / path.name))
        with contextlib.suppress(OSError):
            source.rmdir()


def save(
    *, label: str, out: BinaryIO, response: http.client.HTTPResponse
) -> tuple[int, int]:
    total = int(response.headers.get("Content-Length") or 0)
    div, unit = (1e3, "KB") if 0 < total < MEGA else (MEGA, "MB")

    def meter(done: int) -> str:
        if total:
            return (
                f"{done / div:.1f} of {total / div:.1f} {unit} ({100 * done // total}%)"
            )
        return f"{done / div:.1f} {unit}"

    room = 78 - (len(meter(total)) if total else 12)
    if len(label) > room:
        label = label[: room - 3] + "..."
    done = 0
    loud = threading.current_thread() is threading.main_thread() and sys.stdout.isatty()
    if loud:
        show(end="", flush=True, text=f"{label:<{room}} {meter(0):>{78 - room}}")
    for block in iter(lambda: response.read(1 << 20), b""):
        out.write(block)
        done += len(block)
        if loud:
            show(
                end="", flush=True, text=f"\r{label:<{room}} {meter(done):>{78 - room}}"
            )
    if loud:
        print()
    return done, total


def unpack(download: Download) -> pathlib.Path:
    with hold(lock_for(download.folder)):
        archive = fetch(download)
        target = CACHE / download.folder
        if not target.is_dir():
            part = CACHE / (download.folder + ".part")
            shutil.rmtree(part, ignore_errors=True)
            with zipfile.ZipFile(archive) as z:
                z.extractall(part)
            part.replace(target)
        return target / "amonet"
