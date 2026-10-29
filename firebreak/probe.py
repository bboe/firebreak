from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from firebreak.devices import BY_NAME, FIREOS5_CHAINS, LITTLE_KERNEL_DESCRIPTION
from firebreak.emos import emos
from firebreak.host import adb_shell, adb_state, command, getvar, in_fastboot
from firebreak.report import masked
from firebreak.states import State
from firebreak.twrp import partition_table
from firebreak.ui import ARGUMENTS, SESSION, FatalError, explained

if TYPE_CHECKING:
    from collections.abc import Callable

    from firebreak.plugin import FireOs5Chain

NO_SHELL = "exec '/system/bin/sh' failed"


def chains() -> tuple[FireOs5Chain, ...]:
    device = ARGUMENTS.target.device if ARGUMENTS.target else SESSION.device
    if device is None:
        return tuple(FIREOS5_CHAINS.values())
    chain = FIREOS5_CHAINS.get(device)
    return () if chain is None else (chain,)


def probe() -> State:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    if in_fastboot():
        unlock = getvar(name="unlock_status").lower()
        if unlock == "false":
            little_kernel = getvar(name="lk_build_desc")
            found = recognised(
                ask=lambda chain: chain.fastboot(
                    little_kernel=little_kernel, unlocked=False
                )
            )
            return State.STOCK_FASTBOOT if found is None else found
        if unlock != "true":
            return State.STARTING
        little_kernel = getvar(name="lk_build_desc")
        if not little_kernel:
            return State.STARTING
        found = recognised(
            ask=lambda chain: chain.fastboot(little_kernel=little_kernel, unlocked=True)
        )
        return State.AMONET_FASTBOOT if found is None else found
    connected = adb_state()
    if "unauthorized" in connected:
        return State.STOCK_BOOTED
    if connected == "recovery":
        version = adb_shell(command="getprop ro.twrp.version", timeout=30)
        little_kernel = adb_shell(command="getprop ro.boot.lk_build_desc", timeout=30)
        if not version[:1].isdigit() or not LITTLE_KERNEL_DESCRIPTION.fullmatch(
            string=little_kernel
        ):
            return State.STARTING
        if "mtp" not in adb_shell(command="getprop sys.usb.config", timeout=30):
            return State.STARTING
        found = recognised(
            ask=lambda chain: chain.twrp(little_kernel=little_kernel, version=version)
        )
        if found is not None:
            return found
        if "boot_a_x" in partition_table():
            return State.AMONET_TWRP_BOOT_MOVED
        return State.AMONET_TWRP
    if connected == "device":
        completed = adb_shell(command="getprop sys.boot_completed", timeout=30)
        if NO_SHELL in completed:
            return State.NO_SYSTEM
        booted = completed == "1"
        if adb_shell(command="getprop ro.build.version.name", timeout=30).startswith(
            "Fire OS 6"
        ):
            if "uid=0" in adb_shell(command="id; su -c id", timeout=30):
                return State.AMONET_BOOTED
            return State.STOCK_BOOTED
        if booted and "uid=0" in adb_shell(command="su -c id", timeout=30):
            return rooted()
        return State.BOOTED
    return State.EMOS if emos(action="find") == "1" else State.NONE


def probed() -> str:
    try:
        return state().value
    except FatalError as error:
        plain = explained(error=error)
        return "<unreadable: " + masked(text=plain).strip().split(sep="\n")[0] + ">"


def read_recovery(*, size: int) -> bytes:
    return command(
        arguments=[
            "adb",
            "exec-out",
            f"su -c 'dd if={BY_NAME}/recovery bs=512 count={size // 512} 2>/dev/null'",
        ],
        standard_input=subprocess.DEVNULL,
        standard_output=subprocess.PIPE,
        timeout=60,
    ).stdout


def recognised(*, ask: Callable[[FireOs5Chain], State | None]) -> State | None:
    return next(
        (found for chain in chains() if (found := ask(chain)) is not None), None
    )


def rooted() -> State:
    found = recognised(ask=lambda chain: chain.booted(read=read_recovery))
    return State.ROOTED if found is None else found


def state() -> State:
    SESSION.probing = True
    try:
        current = probe()
    except subprocess.TimeoutExpired:
        current = State.STARTING
    finally:
        SESSION.probing = False
    return current
