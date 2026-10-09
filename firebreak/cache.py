from __future__ import annotations

import contextlib
import dataclasses
import gzip
import hashlib
import http.client
import os
import pathlib
import plistlib
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
import zipfile
import zlib
from typing import TYPE_CHECKING, BinaryIO, NoReturn
from xml.parsers.expat import ExpatError

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator

from firebreak.ui import SESSION, ANSIColor, _die, again, passed, say, show, warn

BROWSER_POLL_SECONDS = 2
BROWSER_WAIT_SECONDS = 120
GZIP_MAGIC = b"\x1f\x8b"
LOCKS: dict[object, threading.Lock] = {}
LOCKS_GUARD = threading.Lock()
MEGA = 1e6
PARTIAL_SUFFIXES = (".crdownload", ".download", ".part", ".tmp")
SYSTEM_SLICE_BYTES = 128 << 20
WHERE_FROMS = "com.apple.metadata:kMDItemWhereFroms"


@dataclasses.dataclass(frozen=True)
class Download:
    name: str
    sha256: str
    url: str
    browser: bool = False
    directory: str = ""
    size: int = 0


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


def browser_fetch(*, download: Download, path: pathlib.Path) -> None:
    directory = downloads_dir()
    checked: set[tuple[pathlib.Path, int, float]] = set()
    found = copies(checked=checked, download=download)
    before: set[str] | None = None
    judged: set[pathlib.Path] = set()
    settled: dict[pathlib.Path, tuple[int, float]] = {}
    unknown: list[pathlib.Path] = []
    if not found:
        before = names_in(directory=directory)
        open_in_browser(directory=directory, download=download)
    deadline = time.monotonic() + BROWSER_WAIT_SECONDS
    while not found:
        if time.monotonic() > deadline:
            gave_up(directory=directory, download=download, unknown=unknown)
        time.sleep(BROWSER_POLL_SECONDS)
        found = copies(checked=checked, download=download)
        for arrived in (
            []
            if found
            else served(
                before=before or set(),
                directory=directory,
                judged=judged,
                settled=settled,
            )
        ):
            judged.add(arrived)
            judge(arrived=arrived, download=download, unknown=unknown)
    part = path.with_name(path.name + ".part")
    shutil.copyfile(dst=part, src=found[0])
    if digest(kind="sha256", path=part) != download.sha256:
        part.unlink()
        _die(message=f"the copy of {found[0]} in {CACHE} does not hash to the pin")
    part.replace(target=path)
    passed(message=f"{download.name} verified")
    discard(paths=found)
    if before is not None and any(
        found_path.parent == trash_dir() for found_path in found
    ):
        discard_unpacked(archive=path, before=before, directory=directory)


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
        size = sum(
            file.stat().st_size for file in CACHE.rglob(pattern="*") if file.is_file()
        )
        path, home = str(CACHE), str(pathlib.Path.home())
        if os.name != "nt" and path.startswith(home + os.sep):
            path = "~" + path[len(home) :]
        show(
            text=f"{path} holds {size // 1000000} MB of downloads and images for"
            " the next run. It is safe to delete."
        )


def copies(
    *, checked: set[tuple[pathlib.Path, int, float]], download: Download
) -> list[pathlib.Path]:
    directories = [downloads_dir()]
    trash = trash_dir()
    if trash is not None:
        directories.append(trash)
    return [
        path
        for directory in directories
        for path in downloaded(checked=checked, directory=directory, download=download)
    ]


def digest(*, kind: str, limit: int = 0, path: pathlib.Path) -> str:
    hasher = hashlib.new(name=kind, usedforsecurity=False)
    left = limit or path.stat().st_size
    with path.open(mode="rb") as file:
        while left > 0:
            block = file.read(min(1 << 20, left))
            if not block:
                break
            left -= len(block)
            hasher.update(block)
    return hasher.hexdigest()


def discard(*, paths: list[pathlib.Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            continue
        show(text=f"removed {path}, which the cache now holds")


def discard_unpacked(
    *, archive: pathlib.Path, before: set[str], directory: pathlib.Path
) -> None:
    for name in sorted(names_in(directory=directory) - before):
        unpacked = directory / name
        if (
            unpacked.is_dir()
            and not unpacked.is_symlink()
            and holds_only(archive=archive, unpacked=unpacked)
        ):
            try:
                shutil.rmtree(unpacked)
            except OSError as error:
                warn(text=f"could not remove {unpacked}: {error}")
                continue
            show(text=f"removed {unpacked}, which the browser unpacked from it")


def download_origin(*, path: pathlib.Path) -> str | None:
    if sys.platform == "darwin":
        return download_origin_macos(path=path)
    if os.name == "nt":
        return download_origin_windows(path=path)
    return download_origin_linux(path=path)


def download_origin_linux(*, path: pathlib.Path) -> str | None:
    try:
        return os.getxattr(path, "user.xdg.origin.url").decode(errors="replace")
    except (AttributeError, OSError):
        return None


def download_origin_macos(*, path: pathlib.Path) -> str | None:
    try:
        dump = subprocess.run(
            args=["/usr/bin/xattr", "-px", WHERE_FROMS, str(path)],
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        ).stdout
        sources = plistlib.loads(bytes.fromhex("".join(dump.split())))
    except (ExpatError, OSError, subprocess.SubprocessError, ValueError):
        return None
    if isinstance(sources, list) and sources and isinstance(sources[0], str):
        return sources[0]
    return None


def download_origin_windows(*, path: pathlib.Path) -> str | None:
    try:
        zone = pathlib.Path(f"{path}:Zone.Identifier").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return None
    for line in zone.splitlines():
        if line.startswith("HostUrl="):
            return line[len("HostUrl=") :].strip()
    return None


def downloaded(
    *,
    checked: set[tuple[pathlib.Path, int, float]],
    directory: pathlib.Path,
    download: Download,
) -> list[pathlib.Path]:
    found: list[pathlib.Path] = []
    try:
        paths = sorted(directory.iterdir())
    except OSError:
        return found
    for path in paths:
        if path.suffix in PARTIAL_SUFFIXES:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        key = (path, stat.st_size, stat.st_mtime)
        if stat.st_size != download.size or key in checked or not path.is_file():
            continue
        try:
            matches = digest(kind="sha256", path=path) == download.sha256
        except OSError:
            continue
        checked.add(key)
        if matches:
            found.append(path)
    return found


def downloads_dir() -> pathlib.Path:
    return pathlib.Path.home() / "Downloads"


def fetch(*, download: Download) -> pathlib.Path:
    name, want = download.name, download.sha256
    with hold(lock=lock_for(key=download)):
        CACHE.mkdir(exist_ok=True, parents=True)
        path = CACHE / name
        if path in SESSION.verified:
            return path
        if path.is_file() and digest(kind="sha256", path=path) == want:
            SESSION.verified.add(path)
            if download.browser:
                discard(paths=copies(checked=set(), download=download))
            return path
        if download.browser:
            browser_fetch(download=download, path=path)
            SESSION.verified.add(path)
            return path
        part = CACHE / (name + ".part")
        try:
            with urllib.request.urlopen(timeout=60, url=download.url) as response:  # ruff: ignore[multiple-with-statements]
                with part.open(mode="wb") as part_file:
                    done, total = save(
                        destination=part_file,
                        label="downloading " + name,
                        response=response,
                    )
        except (OSError, http.client.HTTPException) as error:
            part.unlink(missing_ok=True)
            _die(message=f"downloading {name} failed: {error!r}")
        if total and done != total:
            part.unlink()
            _die(
                message=f"downloading {name} stopped after {done} of {total} bytes. "
                + again()
            )
        if digest(kind="sha256", path=part) != want:
            part.unlink()
            _die(message=f"{name} does not hash to {want}")
        part.replace(target=path)
        SESSION.verified.add(path)
        return path


def gave_up(
    *, directory: pathlib.Path, download: Download, unknown: list[pathlib.Path]
) -> NoReturn:
    left = (
        " These arrived with no record of their source, and were left:"
        f" {', '.join(str(path) for path in unknown)}."
        if unknown
        else ""
    )
    trash = trash_dir()
    if trash is not None and trash.exists() and not listable(directory=trash):
        left += (
            " This terminal cannot read the Trash, where Safari moves a zip it"
            f" unpacks. If it is there, drag it into {directory}."
        )
    _die(
        message=f"{download.name} did not reach {directory} in"
        f" {BROWSER_WAIT_SECONDS // 60} minutes.{left} Download it from"
        f" {download.url} into {directory}. " + again()
    )


def graphical_browser() -> webbrowser.BaseBrowser | None:
    try:
        browser = webbrowser.get()
    except webbrowser.Error:
        return None
    if (
        type(browser) is webbrowser.GenericBrowser
        or getattr(browser, "background", None) is False
    ):
        return None
    return browser


def gzip_intact(*, path: pathlib.Path) -> bool:
    try:
        with gzip.open(filename=path) as unpacked:
            while unpacked.read(1 << 20):
                pass
    except (EOFError, OSError, zlib.error):
        return False
    return True


def gzip_member(*, path: pathlib.Path) -> bool:
    try:
        with path.open(mode="rb") as file:
            return file.read(len(GZIP_MAGIC)) == GZIP_MAGIC
    except OSError:
        return False


@contextlib.contextmanager
def hold(*, lock: threading.Lock) -> Generator[None, None, None]:
    while not lock.acquire(timeout=0.5):
        pass
    try:
        yield
    finally:
        lock.release()


def holds_only(*, archive: pathlib.Path, unpacked: pathlib.Path) -> bool:
    with zipfile.ZipFile(file=archive) as zip_file:
        files = {
            info.filename: info for info in zip_file.infolist() if not info.is_dir()
        }
        directories = {
            info.filename.rstrip("/") for info in zip_file.infolist() if info.is_dir()
        }
        directories.update(
            parent.as_posix()
            for name in files
            for parent in pathlib.PurePosixPath(name).parents
            if parent.as_posix() != "."
        )
        try:
            entries = walked(directory=unpacked)
        except OSError:
            return False
        for relative, path in entries:
            if path.is_symlink():
                return False
            if path.is_dir():
                if relative not in directories:
                    return False
                directories.discard(relative)
                continue
            info = files.pop(relative, None)
            if (
                info is None
                or not path.is_file()
                or not same_bytes(data=zip_file.read(info), path=path)
            ):
                return False
        return not files and not directories


def judge(
    *, arrived: pathlib.Path, download: Download, unknown: list[pathlib.Path]
) -> None:
    source = download_origin(path=arrived)
    if source is None:
        unknown.append(arrived)
        return
    if source != download.url:
        return
    try:
        got = digest(kind="sha256", path=arrived)
    except OSError:
        return
    if got == download.sha256:
        return
    arrived.unlink(missing_ok=True)
    _die(
        message=f"{download.url} gave {arrived} with the sha256 {got},"
        f" not {download.sha256}, and it was removed. The attachment"
        " may have changed."
    )


def listable(*, directory: pathlib.Path) -> bool:
    try:
        next(directory.iterdir(), None)
    except OSError:
        return False
    return True


def lock_for(*, key: object) -> threading.Lock:
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
                    shutil.move(dst=str(CACHE / path.name), src=str(path))
        with contextlib.suppress(OSError):
            source.rmdir()


def names_in(*, directory: pathlib.Path) -> set[str]:
    return {path.name for path in directory.iterdir()} if directory.is_dir() else set()


def open_in_browser(*, directory: pathlib.Path, download: Download) -> None:
    browser = graphical_browser()
    if browser is None:
        _die(
            message=f"{download.name} is an XDA attachment, and XDA serves it"
            " only to a browser that runs JavaScript. None is available here."
            f" Download it from {download.url} on any computer, and copy it"
            f" into {directory}. " + again()
        )
    say(
        code=ANSIColor.YELLOW,
        text=f"{download.name} is an XDA attachment, and XDA serves it only to"
        " a browser. Your browser opens next and downloads it from the address"
        f" below. This waits up to {BROWSER_WAIT_SECONDS // 60} minutes for it"
        f" to be in {directory}, with the sha256 {download.sha256}. If XDA asks"
        " you to log in, log in and the download starts. Ctrl-C stops the"
        " script.",
    )
    show(text=download.url)
    if not browser.open(url=download.url):
        _die(
            message=f"the browser did not open {download.url}. Download it"
            f" there, into {directory}. " + again()
        )


def portions(*, chunks: Iterator[bytes]) -> Iterator[list[bytes]]:
    held: list[bytes] = []
    size = 0
    for chunk in chunks:
        view = memoryview(chunk)
        while view:
            took = min(SYSTEM_SLICE_BYTES - size, len(view))
            held.append(bytes(view[:took]))
            view, size = view[took:], size + took
            if size == SYSTEM_SLICE_BYTES:
                yield held
                held, size = [], 0
    if held:
        yield held


def reraise(error: OSError) -> NoReturn:
    raise error


def same_bytes(*, data: bytes, path: pathlib.Path) -> bool:
    try:
        return path.read_bytes() == data
    except OSError:
        return False


def save(
    *, destination: BinaryIO, label: str, response: http.client.HTTPResponse
) -> tuple[int, int]:
    total = int(response.headers.get(name="Content-Length") or 0)
    divisor, unit = (1e3, "KB") if 0 < total < MEGA else (MEGA, "MB")

    def meter(*, done: int) -> str:
        if total:
            return (
                f"{done / divisor:.1f} of {total / divisor:.1f} {unit}"
                f" ({100 * done // total}%)"
            )
        return f"{done / divisor:.1f} {unit}"

    room = 78 - (len(meter(done=total)) if total else 12)
    if len(label) > room:
        label = label[: room - 3] + "..."
    done = 0
    loud = threading.current_thread() is threading.main_thread() and sys.stdout.isatty()
    if loud:
        show(end="", flush=True, text=f"{label:<{room}} {meter(done=0):>{78 - room}}")
    for block in iter(lambda: response.read(1 << 20), b""):
        destination.write(block)
        done += len(block)
        if loud:
            show(
                end="",
                flush=True,
                text=f"\r{label:<{room}} {meter(done=done):>{78 - room}}",
            )
    if loud:
        print()
    return done, total


def served(
    *,
    before: set[str],
    directory: pathlib.Path,
    judged: set[pathlib.Path],
    settled: dict[pathlib.Path, tuple[int, float]],
) -> list[pathlib.Path]:
    names = names_in(directory=directory)
    if any(name.endswith(PARTIAL_SUFFIXES) for name in names - before):
        return []
    arrived = []
    for name in sorted(names - before):
        path = directory / name
        if path in judged or not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size == 0:
            continue
        state = (stat.st_size, stat.st_mtime)
        if settled.get(path) == state:
            arrived.append(path)
        settled[path] = state
    return arrived


def slice_path(*, directory: pathlib.Path, index: int) -> pathlib.Path:
    return directory / f"system.{index:02d}.gz"


def system_sliced(*, directory: pathlib.Path) -> bool:
    try:
        _, blocks, slices = (directory / "md5").read_text().split()
    except (OSError, ValueError):
        return False
    return (
        blocks.isdigit()
        and slices.isdigit()
        and int(slices) > 0
        and all(
            gzip_member(path=slice_path(directory=directory, index=index))
            for index in range(int(slices))
        )
    )


def trash_dir() -> pathlib.Path | None:
    return pathlib.Path.home() / ".Trash" if sys.platform == "darwin" else None


def unpack(*, download: Download) -> pathlib.Path:
    with hold(lock=lock_for(key=download.directory)):
        archive = fetch(download=download)
        target = CACHE / download.directory
        if not target.is_dir():
            part = CACHE / (download.directory + ".part")
            shutil.rmtree(ignore_errors=True, path=part)
            with zipfile.ZipFile(file=archive) as zip_file:
                zip_file.extractall(path=part)
            part.replace(target=target)
        return target / "amonet"


def walked(*, directory: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    entries = []
    for root, directories, names in os.walk(directory, onerror=reraise):
        for name in (*directories, *names):
            path = pathlib.Path(root) / name
            entries.append((path.relative_to(directory).as_posix(), path))
    return entries


def write_slices(
    *, chunks: Iterator[bytes], directory: pathlib.Path
) -> tuple[str, int]:
    checksum = hashlib.md5(usedforsecurity=False)
    count = 0
    for count, portion in enumerate(portions(chunks=chunks), start=1):
        path = slice_path(directory=directory, index=count - 1)
        with gzip.open(compresslevel=6, filename=path, mode="wb") as compressed:
            for chunk in portion:
                checksum.update(chunk)
                compressed.write(chunk)
    return checksum.hexdigest(), count
