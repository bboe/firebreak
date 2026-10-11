"""Show the simulated Dot's bootrom as the only serial port pyserial lists."""

from __future__ import annotations

import importlib.abc
import json
import os
import pathlib
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from importlib.machinery import ModuleSpec
    from types import ModuleType

BOOTROM_PRODUCT_ID = 0x0003
MEDIATEK_VENDOR_ID = 0x0E8D
MODULE = "serial.tools.list_ports"
STATE = (
    pathlib.Path(
        os.environ.get("FIREBREAK_SIM")
        or pathlib.Path.home() / ".cache" / "firebreak-sim"
    )
    / "state.json"
)


class Finder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> ModuleSpec | None:
        if fullname != MODULE:
            return None
        for finder in sys.meta_path:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                spec.loader = Loader(inner=spec.loader)
                return spec
        return None


class Loader(importlib.abc.Loader):
    def __init__(self, *, inner: importlib.abc.InspectLoader) -> None:
        self.inner = inner

    def exec_module(self, module: ModuleType) -> None:
        exec(  # ruff: ignore[exec-builtin]
            self.inner.get_code(module.__name__), module.__dict__
        )
        module.comports = comports


def comports(*_: object) -> list:
    from serial.tools.list_ports_common import (  # ruff: ignore[import-outside-top-level]
        ListPortInfo,
    )

    try:
        state = json.loads(STATE.read_text())
    except (OSError, ValueError):
        return []
    port = state.get("port")
    if state.get("mode") != "bootrom" or not port:
        return []
    info = ListPortInfo(port, skip_link_detection=True)
    info.vid = MEDIATEK_VENDOR_ID
    info.pid = BOOTROM_PRODUCT_ID
    info.serial_number = None
    info.manufacturer = "MediaTek Inc"
    info.product = "MT65xx Preloader"
    info.hwid = f"USB VID:PID={MEDIATEK_VENDOR_ID:04X}:{BOOTROM_PRODUCT_ID:04X}"
    return [info]


sys.meta_path.insert(0, Finder())
