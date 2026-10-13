from __future__ import annotations

import hashlib
import subprocess

from firebreak.cache import digest, unpack
from firebreak.devices import BY_NAME, LITTLE_KERNEL_DESCRIPTION, LK, State
from firebreak.emos import emos
from firebreak.host import adb_shell, command, getvar, in_fastboot, run, usb_serial
from firebreak.report import masked
from firebreak.twrp import partition_table
from firebreak.ui import SESSION, FatalError, explained
from firebreak.unlocks import amonet_biscuit_v1_1_0, amonet_biscuit_v1_1_0_bboe


def probe() -> State:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    if in_fastboot():
        unlock = getvar(name="unlock_status").lower()
        if unlock == "false":
            if getvar(name="lk_build_desc") == LK.FIREOS5.value:
                return State.STOCK_FIREOS5_FASTBOOT
            return State.STOCK_FASTBOOT
        if unlock != "true":
            return State.STARTING
        little_kernel = getvar(name="lk_build_desc")
        if not little_kernel:
            return State.STARTING
        if little_kernel == LK.FIREOS5.value:
            return State.AMONET_V1_1_0_FASTBOOT
        return State.AMONET_V2_0_0_FASTBOOT
    adb_state = ""
    if usb_serial():
        adb_state = run(arguments=["adb", "get-state"], timeout=30).stdout
    if "unauthorized" in adb_state:
        return State.STOCK_BOOTED
    adb_state = adb_state.strip()
    if adb_state == "recovery":
        version = adb_shell(command="getprop ro.twrp.version", timeout=30)
        little_kernel = adb_shell(command="getprop ro.boot.lk_build_desc", timeout=30)
        if not version[:1].isdigit() or not LITTLE_KERNEL_DESCRIPTION.fullmatch(
            string=little_kernel
        ):
            return State.STARTING
        if "mtp" not in adb_shell(command="getprop sys.usb.config", timeout=30):
            return State.STARTING
        if little_kernel != LK.FIREOS5.value:
            if "boot_a_x" in partition_table():
                return State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE
            return State.AMONET_V2_0_0_TWRP
        if version != amonet_biscuit_v1_1_0_bboe.TWRP_VERSION:
            return State.AMONET_V1_1_0_TWRP
        return State.AMONET_V1_1_0_BBOE_TWRP
    if adb_state == "device":
        booted = adb_shell(command="getprop sys.boot_completed", timeout=30) == "1"
        if adb_shell(command="getprop ro.build.version.name", timeout=30).startswith(
            "Fire OS 6"
        ):
            if "uid=0" in adb_shell(command="id; su -c id", timeout=30):
                return State.AMONET_V2_0_0_BOOTED
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


def rooted() -> State:
    bboe = amonet_biscuit_v1_1_0_bboe.RECOVERY
    image = unpack(download=amonet_biscuit_v1_1_0.SOURCE) / "bin" / "twrp.img"
    size = image.stat().st_size
    data = read_recovery(size=max(bboe.size, size))
    if hashlib.sha256(data[: bboe.size]).hexdigest() == bboe.sha256:
        return State.AMONET_V1_1_0_BBOE_BOOTED
    if hashlib.md5(data[:size], usedforsecurity=False).hexdigest() == digest(
        kind="md5", path=image
    ):
        return State.AMONET_V1_1_0_BOOTED
    return State.ROOTED


def state() -> State:
    SESSION.probing = True
    try:
        current = probe()
    except subprocess.TimeoutExpired:
        current = State.STARTING
    finally:
        SESSION.probing = False
    return current
