from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from firebreak import ui

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def fresh_session() -> Iterator[None]:
    ui.ARGUMENTS.verbose = False
    vars(ui.SESSION).update(vars(ui.Session()))
    vars(ui.PROGRESS).update(vars(ui.Progress()))
    yield
    ui.PROGRESS.halt()
