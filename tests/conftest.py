from __future__ import annotations

import sys
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import cache, ui

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def fresh_session() -> Iterator[None]:
    ui.ARGUMENTS.verbose = False
    vars(ui.SESSION).update(vars(ui.Session()))
    vars(ui.PROGRESS).update(vars(ui.Progress()))
    yield
    ui.PROGRESS.halt()


@pytest.fixture(autouse=True)
def no_real_cache(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    directory = tmp_path / "real-cache"
    for module in (cache, sys.modules.get("firebreak.__main__")):
        if module is not None:
            monkeypatch.setattr(name="CACHE", target=module, value=directory)
            monkeypatch.setattr(
                name="ERASED", target=module, value=directory / "boot0-erased"
            )
    monkeypatch.setenv(name="HOME", value=str(tmp_path / "real-home"))
    monkeypatch.setenv(name="USERPROFILE", value=str(tmp_path / "real-home"))
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=real_browser)


def opened_a_browser(**options: str) -> None:
    message = f"a test opened the real browser at {options}"
    raise AssertionError(message)


def real_browser() -> types.SimpleNamespace:
    return types.SimpleNamespace(name="real-browser", open=opened_a_browser)
