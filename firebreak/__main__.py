"""Change the firmware on an Echo Dot (2nd Generation) over USB: root it, or
return it to stock. It finds where the Dot is, from stock, part way through, or
on another target, and keeps going until the Dot is on the target: it waits
while the Dot reboots, and while you take a step it asks for. Stopped, it picks
up where it left off on the next run. It uses the one Dot on USB; set
ANDROID_SERIAL when several are. It needs Python 3.9 or later, and adb and
fastboot from Android platform-tools.
https://github.com/bboe/firebreak/blob/main/docs/rooting.md says why each
step is there.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import enum
import functools
import hashlib
import http.client
import os
import pathlib
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import serial

    from firebreak.emmc import Emmc

from firebreak import bootrom, recovery
from firebreak.amonet.biscuit_v2_0_0 import Client
from firebreak.amonet.payload import NotReadyError, Payload, start_payload
from firebreak.android.bootimg import boot_image, cpio, magisk_db, magisk_files
from firebreak.android.gpt import (
    Partition,
    gpt_intact,
    stock_gpt,
)
from firebreak.android.ota import extract
from firebreak.cache import (
    CACHE,
    ERASED,
    MAGISK,
    Download,
    cache_note,
    digest,
    fetch,
    hold,
    lock_for,
    move_old_caches,
    save,
    slice_path,
    system_sliced,
    unpack,
    write_slices,
)
from firebreak.devices import State
from firebreak.emmc import EmmcArea
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    MORE_THAN_ONE,
    NO_ACCESS,
    PUSH_TRIES,
    USER_SERIAL,
    adb_script,
    adb_shell,
    check_adb,
    check_user,
    child,
    child_path,
    command,
    getvar,
    in_fastboot,
    md5_mismatch,
    no_port_help,
    push_checked,
    pyserial_wheel,
    reconnect,
    rerun,
    run,
    usb_serial,
)
from firebreak.mediatek import range_check
from firebreak.mediatek.usbdl import (
    BAUD_RATE,
    PORT_POLL_INTERVAL,
    READ_TIMEOUT,
    Bootrom,
    HandshakeTimeoutError,
    ProductId,
    UsbdlError,
    mediatek_ports,
)
from firebreak.plan import TABLE_SECTORS, Action, resolve
from firebreak.plugin import FireOs6
from firebreak.report import (
    LEFT_IN_RECOVERY,
    LISTING_OK,
    PARTITIONS_OK,
    dot_details,
    labelled,
    masked,
    mmc_said,
    node_held,
    node_names,
    node_sizes,
    partition_rows,
    system_a_rows,
    system_record,
    whole,
)
from firebreak.twrp import (
    DISK,
    TABLE_OK,
    clear_boot0,
    partition_table,
    partitions,
    read_sectors,
    reboot,
    restore_failed,
    unmount,
    wait_for_twrp,
    write,
    write_system,
)
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    PROGRESS,
    SESSION,
    SUPPORT,
    ANSIColor,
    Kind,
    _die,
    again,
    asked_for,
    clock,
    paint,
    passed,
    program,
    say,
    show,
    status,
    warn,
)
from firebreak.unlocks import (
    amonet_biscuit_v1_1_0,
    amonet_biscuit_v1_1_0_bboe,
    amonet_biscuit_v2_0_0,
)
from firebreak.unlocks.targets import FIREOS, TARGETS
from firebreak.write_test import EMMC_TARGET, MEBIBYTE, USB_TEST, emmc_leg, usb_leg

AMONET_BISCUIT_V1_1_0 = amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0.name
AMONET_BISCUIT_V1_1_0_BBOE = amonet_biscuit_v1_1_0_bboe.AMONET_BISCUIT_V1_1_0_BBOE.name
AMONET_BISCUIT_V1_1_0_ZIP = amonet_biscuit_v1_1_0.SOURCE
AMONET_BISCUIT_V2_0_0 = amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0.name
AMONET_BISCUIT_V2_0_0_ZIP = amonet_biscuit_v2_0_0.SOURCE
BOOTLOADER_CONTROL_BLOCK = b"\0ABB\x01\x8f\0"
BOOTLOADER_CONTROL_BLOCK_OFFSET = 0x360
BOOTROM_STEP_TIMEOUT = 30 * MINUTE
BOOTROM_WRITE_TIMEOUT = 30
BOOT_ROOT = Download(
    browser=True,
    name="boot-root.zip",
    sha256="de49cc88b27a8e77cf97cf0156bee50e4ddc0e116c41aaede06b494e38397be0",
    size=473633,
    url="https://xdaforums.com/attachments/boot-root-zip.6388001/",
)
BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
CHAIN_TEE = ("tee2", "tee1")
EMOS_DEVICE_ID = (0x1949, 0x2007)
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green."
)
FTVDB = "https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/"
LITTLE_KERNEL_DESCRIPTION = re.compile(pattern=r"[0-9a-f]{7}-\d{8}_\d{6}")
MD5_DIGITS = 32
OPEN_GRACE = 1
POKE_GONE_WAIT = 5
POKE_WRITE_TIMEOUT = 1
REPLUG_WAIT = 600
ROOTED = {State.ROOTED, State.ROOTED_AMONET_V1_1_0_BBOE, State.ROOTED_AMONET_V1_1_0}
SHORT_WAIT = 5
STOCK_STEPS = 16
TWRP = amonet_biscuit_v1_1_0_bboe.RECOVERY
TWRPS = frozenset({
    State.AMONET_V1_1_0_TWRP,
    State.AMONET_V2_0_0_TWRP,
    State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    State.AMONET_V1_1_0_BBOE_TWRP,
})
TWRP_VERSION = amonet_biscuit_v1_1_0_bboe.TWRP_VERSION
TWRP_VERSIONS = ("3.2.", "3.7.")
UPDATER = "com.amazon.device.software.ota"
UPDATE_HOSTS = (
    "updates.amazon.com",
    "softwareupdates.amazon.com",
    "amzndigitaldownloads.edgesuite.net",
    "amzdigital-a.akamaihd.com",
)
WAIT = 600


@dataclasses.dataclass(frozen=True)
class Build:
    date: str
    ftvdb_version: str
    md5: str
    ns: str
    number: str
    sha256: str


BUILDS = {
    "4315": Build(
        date="2023-11-20",
        ftvdb_version="6-5-5-5",
        md5="03c7c4dc338a93635dda0f5e1cd4e451",
        ns="NS6555",
        number="8087722874",
        sha256="c1ca33efd975cb8491ea9438eff95af559c632dd7ca75ff3b73facacce5f758a",
    ),
    "4405": Build(
        date="2023-01-21",
        ftvdb_version="6-5-5-6",
        md5="570f3f6b28f94323e01e95561c87887f",
        ns="NS6556",
        number="8289072516",
        sha256="6839b0a1e5c4f6aa57f89ea7ca67c85aa69f8fe32e5ddc252764b0d96be5bf69",
    ),
    "5041": Build(
        date="2023-04-06",
        ftvdb_version="6-5-0-5",
        md5="1a25d21e0363158fe0c14cb4d41b843e",
        ns="NS6505",
        number="8960323972",
        sha256="80d98d3b57bc654d435b384f096dea46edd2b86e9f8adaaf91a7b0c3001e9716",
    ),
    "6302": Build(
        date="2025-04-13",
        ftvdb_version="6-4-6-6",
        md5="62da0c58f8c3e5c8094f302346da754f",
        ns="NS6466",
        number="11712110212",
        sha256="6d395345b1d1db373f9d714172c2ac5de4b5dd3e52d1ed1c3f37c2f007537667",
    ),
    "8138": Build(
        date="2026-08-31",
        ftvdb_version="6574-1",
        md5="723886117a7a4a8a543c2ec955dcd54e",
        ns="NS65741",
        number="13222529668",
        sha256="d2a61dd2af1d322e9ecfb4643670fbe416bc2442410f1aebe9748e2438f6d55f",
    ),
    "8142": Build(
        date="2026-09-09",
        ftvdb_version="6574-1",
        md5="ead2ea9a9ca2fa1c708381a07c605356",
        ns="NS65741",
        number="13222530692",
        sha256="ed4ddb01cd53e38751bb6274ad1a8255043e0795843d6ac2d44cc2803b2179a0",
    ),
    "8146": Build(
        date="2026-09-17",
        ftvdb_version="6574-1",
        md5="8ca06ee4ef2806c974d2944b7fadd543",
        ns="NS65741",
        number="13222531716",
        sha256="90832e86498c5e803974c30359aea71c1129757be0ddc59d831a94b27f81487f",
    ),
}


class LK(enum.Enum):
    FIREOS5 = "f379dba-20170906_000423"
    FIREOS6 = "63cb91b-20221007_072309"
    FIREOS6_4315 = "41fb3ce-20221007_151724"


class Shell(enum.Enum):
    BOOT0 = (
        "d=dd; toybox dd --help >/dev/null 2>&1 && d='toybox dd'; "
        "echo 0 > /sys/block/mmcblk0boot0/force_ro; "
        "$d if={source} of=/dev/block/mmcblk0boot0 bs=1048576 2>/dev/null; "
        "echo 1 > /sys/block/mmcblk0boot0/force_ro; sync; "
        "echo 3 > /proc/sys/vm/drop_caches"
    )
    DATA = f"""\
set -e
umount /sdcard /data 2>/dev/null || true
d={BY_NAME}/userdata
mke2fs -q -t ext4 -b 4096 "$d" $(( $(blockdev --getsize64 "$d") / 4096 - 256 ))
mount -t ext4 "$d" /data
mountpoint -q /data
"""
    MAGISK = """\
set -e
mountpoint -q /data
cd /; cpio -idu < /tmp/magisk.cpio 2>/dev/null
chmod 700 /data/adb; chmod -R 755 /data/adb/magisk; chmod 600 /data/adb/magisk.db
sync
"""
    SYSTEM = """\
set -e
m=/tmp/fireos-system
mkdir -p $m
mountpoint -q $m || mount -t ext4 {system} $m
f=$m/etc/init.fosflags.sh
sed -i 's/if \\[ $(( $FOS_FLAGS_ADB_ON & $FOSFLAGS )) != 0 \\]; then/if true; then/; \
s/^\\( *\\)unset_adb_persistent_property$/\\1true/' "$f"
for h in {hosts}; do
  grep -q " $h\\$" $m/etc/hosts || echo "127.0.0.1 $h" >> $m/etc/hosts
done
grep -q 'if true; then' "$f"
grep -q '^ *unset_adb_persistent_property$' "$f" && exit 1
sync; umount $m
"""
    TOOLS = (
        "m=; for t in sgdisk mke2fs blockdev md5sum; do"
        ' command -v "$t" >/dev/null 2>&1 || which "$t" >/dev/null 2>&1'
        ' || m="$m $t"; done; echo "tools:$m"'
    )
    WRITE = (
        "dd if={source} of={target} bs=1048576 2>/dev/null;"
        " sync; echo 3 > /proc/sys/vm/drop_caches"
    )


@dataclasses.dataclass(frozen=True)
class Stage:
    run: Callable[[], bool | None]
    steps: int
    then: State | None
    passes: frozenset[State] = frozenset()


@dataclasses.dataclass(frozen=True)
class Step:
    estimate: str
    image: str
    label: str
    partition: str


WRITES = (
    Step(
        estimate="4 min",
        image="system",
        label="write the system image to system_a",
        partition="system_a",
    ),
    Step(
        estimate="4 min",
        image="system",
        label="write the system image to system_b",
        partition="system_b",
    ),
    Step(
        estimate="10 s",
        image="boot",
        label="write boot image to boot_a",
        partition="boot_a",
    ),
    Step(
        estimate="10 s",
        image="boot",
        label="write boot image to boot_b",
        partition="boot_b",
    ),
    Step(
        estimate="5 s",
        image="misc",
        label="write misc, slot a marked good",
        partition="misc",
    ),
)


def amonet_chain() -> None:
    part = partitions()
    for slot in ("lk_a", "lk_b"):
        if slot not in part:
            _die(message=f"the Dot's partition table has no {slot}. " + again())
    if any(amonet_lk(node=f"{DISK}p{part[slot][0]}") for slot in ("lk_a", "lk_b")):
        return
    _die(
        message="neither lk_a nor lk_b holds amonet v2.0.0's or v1.1.0's LK, so"
        " this Dot is locked and the recovery it started is one amonet left"
        " behind. Nothing was written. Unlock it first: unplug the USB cable,"
        " hold the action button, plug it back in, and let go when the ring"
        " turns green. " + again()
    )


def amonet_lk(*, node: str) -> bool:
    for download in (AMONET_BISCUIT_V2_0_0_ZIP, AMONET_BISCUIT_V1_1_0_ZIP):
        local = unpack(download=download) / "bin" / "lk.bin"
        want = digest(kind="md5", path=local)
        for attempt in range(PUSH_TRIES):
            read = adb_shell(
                command=f"[ -b {node} ] && dd if={node} bs={local.stat().st_size}"
                " count=1 2>/dev/null | md5sum",
                timeout=120,
            )
            held = read.split(sep="\n")[-1].split(sep=" ")[0]
            if held == want:
                return True
            if len(held) == MD5_DIGITS:
                break
            if attempt + 1 < PUSH_TRIES:
                reconnect(remote=DISK)
        if len(held) != MD5_DIGITS:
            _die(
                message=f"{node} did not answer with an md5 of its first"
                f" {local.stat().st_size} bytes: {held or 'nothing'}. Nothing"
                " was written. " + again() + " " + asked_for()
            )
    return False


def amonet_v1_1_0_recovery() -> bool:
    unlocked = ""
    for _ in range(PUSH_TRIES):
        unlocked = getvar(name="unlock_status").lower()
        if unlocked in {"true", "false"}:
            break
        time.sleep(1)
    if unlocked == "false":
        PROGRESS.note(
            message="The Dot came back in its own locked fastboot rather than"
            " amonet's, which accepts nothing this needs. This run unlocks it again"
            " and goes on from v2.0.0's recovery."
        )
        return False
    if unlocked != "true":
        _die(
            message="the Dot's fastboot did not say whether it is unlocked. " + again()
        )
    amonet = unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    twrp = fetch(download=TWRP)
    PROGRESS.begin(estimate="30 s", label=f"waiting for TWRP {TWRP_VERSION}")
    run(
        arguments=["fastboot", "-S", "256M", "flash", "tee2", "bin/tz.img"],
        check=True,
        directory=amonet,
        timeout=120,
    )
    run(
        arguments=["fastboot", "-S", "256M", "flash", "recovery", twrp],
        check=True,
        timeout=120,
    )
    run(
        arguments=["fastboot", "oem", "reboot-recovery"],
        check=True,
        directory=amonet,
        timeout=60,
    )
    return True


def amonet_v2_0_0_payload() -> pathlib.Path:
    amonet = unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    return amonet / "brom-payload" / "build" / "payload.bin"


def await_amonet_fastboot() -> None:
    for _ in range(30):
        try:
            if in_fastboot() and getvar(name="lk_build_desc") == LK.FIREOS5.value:
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    _die(message="the Dot did not come back in v1.1.0's fastboot")


def await_bootrom_port(
    *, deadline: float, erase: Callable[[], str] | None, preloaders: set[str]
) -> serial.Serial | None:
    failures: dict[str, float] = {}
    missed = 0
    while True:
        found = mediatek_ports()
        failures = {name: when for name, when in failures.items() if name in found}
        preloaders &= set(found)
        for name in sorted(found):
            if found[name] != ProductId.BOOTROM:
                continue
            port = open_bootrom(failures=failures, name=name)
            if port is not None:
                return port
        for name in sorted(found):
            if found[name] != ProductId.PRELOADER or name in preloaders:
                continue
            preloaders.add(name)
            if not erase and not SESSION.short:
                return None
            if SESSION.short:
                missed += 1
                say_missed_short(count=missed)
        if time.monotonic() >= deadline:
            _die(
                message="the Dot's bootrom did not show up as a serial port.\n"
                + no_port_help()
            )
        time.sleep(PORT_POLL_INTERVAL)


def await_port_gone(*, deadline: float, name: str) -> None:
    while name in mediatek_ports() and time.monotonic() < deadline:
        time.sleep(PORT_POLL_INTERVAL)


def bootloader_plan(*, amonet: pathlib.Path, live: Emmc) -> tuple[Action, ...]:
    check_emmc(live=live)
    unlock = amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0
    try:
        raw = bootrom.read(count=TABLE_SECTORS, first=0, payload=live)
    except (OSError, UsbdlError) as error:
        _die(
            message=f"the Dot's partition table could not be read: {error}."
            f" {unwritten()} Unplug the Dot. " + again()
        )
    try:
        resolved = resolve(raw=raw, source=amonet, unlock=unlock)
    except (FileNotFoundError, KeyError, ValueError) as error:
        _die(
            message=f"{unlock.name} does not fit this Dot: {error.args[0]}."
            f" {unwritten()} " + again()
        )
    kinds = [action.kind for action in resolved]
    if bootrom.REBOOT not in kinds:
        return resolved
    return resolved[: kinds.index(bootrom.REBOOT) + 1]


def bootrom_client(
    *, deadline: float, erase: Callable[[], str] | None
) -> Bootrom | None:
    overall = time.monotonic() + BOOTROM_STEP_TIMEOUT
    preloaders = {
        name
        for name, product in mediatek_ports().items()
        if product == ProductId.PRELOADER
    }
    while True:
        port = await_bootrom_port(deadline=deadline, erase=erase, preloaders=preloaders)
        if port is None:
            return None
        client = Bootrom(port=port)
        try:
            client.handshake()
        except (HandshakeTimeoutError, OSError) as error:
            with contextlib.suppress(OSError):
                client.port.close()
            if SESSION.short:
                _die(
                    message=f"the Dot's bootrom did not answer ({error})."
                    f" {unwritten()} Unplug the Dot. " + again()
                )
            PROGRESS.note(
                message=f"The Dot's bootrom did not answer ({error}). Unplug the Dot"
                " and plug it back in; the run goes on when its bootrom returns."
            )
            await_port_gone(deadline=overall, name=port.name)
            if time.monotonic() >= overall:
                _die(
                    message="the Dot's bootrom never answered a handshake."
                    f" {unwritten()} Unplug the Dot. " + again()
                )
            deadline = min(overall, time.monotonic() + REPLUG_WAIT)
        except UsbdlError as error:
            with contextlib.suppress(OSError):
                client.port.close()
            _die(
                message=f"the Dot's bootrom did not answer as one: {error}."
                f" {unwritten()} Unplug the Dot. " + again()
            )
        else:
            return client


def bootrom_step(
    *,
    amonet: pathlib.Path,
    erase: Callable[[], str] | None,
    payload: pathlib.Path,
    wheel: pathlib.Path | None,
) -> bool:
    if wheel is not None and str(wheel) not in sys.path:
        sys.path.insert(0, str(wheel))
    if erase:
        ERASED.touch()
        failure = erase()
        if failure:
            _die(message=failure)
    elif SESSION.short:
        say(
            code=ANSIColor.YELLOW,
            text="Short the Dot's test point and plug it in. The run waits for"
            " its bootrom, then says when the short may come off.",
        )
        status(text="Waiting for the bootrom.")
    else:
        poke_live_payload()
        PROGRESS.begin(estimate="40 s", label="waiting for the Dot to restart")
    client = bootrom_client(
        deadline=time.monotonic() + (60 if erase else 600), erase=erase
    )
    if client is None:
        ERASED.unlink(missing_ok=True)
        PROGRESS.note(
            message="The Dot started its preloader, so boot0 is intact and it"
            " needs no bootrom step."
        )
        return False
    live = exploit(client=client, payload=payload)
    actions = bootrom.check(actions=bootloader_plan(amonet=amonet, live=live))
    if PROGRESS.steps:
        PROGRESS.steps += len(actions) - 1
    ERASED.touch()
    bootrom.execute(actions=actions, payload=live)
    with contextlib.suppress(OSError):
        client.port.close()
    ERASED.unlink(missing_ok=True)
    await_amonet_fastboot()
    return True


def build_system(*, package: Download, target: pathlib.Path) -> None:
    part = CACHE / "system.part"
    shutil.rmtree(ignore_errors=True, path=part)
    part.mkdir()
    fireos = fetch(download=package)
    with zipfile.ZipFile(file=fireos) as archive:
        words = archive.read(name="system.transfer.list").decode().split()
        commands = dict(zip(words[4::2], words[5::2]))
        if words[0] != "3" or set(commands) != {"erase", "new"}:
            _die(message=f"{package.name} has a transfer list this does not read")
        blocks = int(commands["erase"].split(sep=",")[-1])
        bounds = [int(number) for number in commands["new"].split(sep=",")[1:]]
        ranges = [*zip(bounds[::2], bounds[1::2]), (blocks, blocks)]
        with archive.open(name="system.new.dat") as new_data:
            want, slices = write_slices(
                chunks=system_chunks(
                    name=package.name, new_data=new_data, ranges=ranges
                ),
                directory=part,
            )
    (part / "md5").write_text(data=f"{want} {blocks} {slices}\n")
    for path in part.iterdir():
        with path.open(mode="rb+") as file:
            os.fsync(fd=file.fileno())
    part.replace(target=target)


def chain_writes() -> tuple[Step, ...]:
    live = (
        "lk_b" if adb_shell(command="getprop ro.boot.slot_suffix") == "_b" else "lk_a"
    )
    spare = "lk_a" if live == "lk_b" else "lk_b"
    first, last = CHAIN_TEE
    return (
        Step(
            estimate="5 s",
            image="lk",
            label=f"write LK image to {spare} (spare slot)",
            partition=spare,
        ),
        Step(
            estimate="5 s",
            image="tee",
            label=f"write TEE image to {first} (backup)",
            partition=first,
        ),
        Step(
            estimate="5 s",
            image="expdb",
            label="zero expdb (amonet kaeru payload)",
            partition="expdb",
        ),
        Step(
            estimate="5 s",
            image="lk",
            label=f"write LK image to {live} (live slot)",
            partition=live,
        ),
        Step(
            estimate="5 s",
            image="tee",
            label=f"write TEE image to {last} (primary)",
            partition=last,
        ),
    )


def check_emmc(*, live: Emmc) -> None:
    try:
        live.switch_partition(partition=EmmcArea.USER)
        block = live.read_block(index=0)
    except (OSError, UsbdlError) as error:
        said = str(error)
    else:
        if bootrom.switched(block=block, partition=EmmcArea.USER):
            return
        wanted = bootrom.USER_AREA_SIGNATURE
        said = (
            f"block 0 of its user area ends {block[-len(wanted) :]!r}, not {wanted!r}"
        )
    _die(
        message=f"the Dot's eMMC did not answer{short_hint()}: {said}."
        f" {unwritten()} Unplug the Dot. " + again()
    )


def child_emos(*, action: str, want: str) -> int:
    import serial  # ruff: ignore[import-outside-top-level]
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    ports = [
        port.device
        for port in list_ports.comports()
        if (port.vid, port.pid) == EMOS_DEVICE_ID and want in {"", port.serial_number}
    ]
    if action == "find" or len(ports) != 1:
        print(len(ports))
        return int(action != "find")
    try:
        connection = serial.Serial(
            baudrate=115200, port=ports[0], timeout=0.2, write_timeout=1
        )
    except serial.SerialException:
        print("denied")
        return 1
    with connection:
        connection.reset_input_buffer()
        connection.write(data=b"\n")
        seen = b""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            seen += connection.read(size=256)
            if seen.rstrip(b" ").endswith(b"password:"):
                print("password")
                return 1
            if seen.rstrip(b" ").endswith(b"#"):
                connection.write(data=b"/init recovery\n")
                print("recovery")
                return 0
    print("silent")
    return 1


def child_main(*, arguments: list[str], name: str) -> int:
    if sys.path[0] == str(pathlib.Path.cwd()):
        del sys.path[0]
    return {"emos": child_emos}[name](action=arguments[0], want=arguments[1])


def cli() -> None:
    installs = TARGETS[AMONET_BISCUIT_V2_0_0].installs
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""targets:
  {AMONET_BISCUIT_V1_1_0_BBOE}, the default
      rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP {TWRP_VERSION}.
  {AMONET_BISCUIT_V1_1_0}
      the same, with amonet v1.1.0's own TWRP 3.2.3.
  {AMONET_BISCUIT_V2_0_0}
      amonet v2.0.0's own procedure: Fire OS 6 {installs.build}
      with boot-root.zip's root adb.
  stock BUILD
      Amazon's Fire OS 6 BUILD, which erases the whole Dot.
Run again with another target to move the Dot to it.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog="firebreak",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print each adb and fastboot command, its exit status and the"
        " time, and each state the Dot reaches",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print what the Dot and this computer are, and the Dot's partition"
        " table, for a support request; it starts the Dot's recovery to read them"
        " and writes no partition",
    )
    parser.add_argument(
        "--write-test",
        action="store_true",
        help=f"write a known pattern over the Dot's {EMMC_TARGET} partition and"
        " read it back, which tells a failing eMMC from a failing USB cable"
        " because nothing crosses USB; it leaves a fresh empty filesystem there,"
        " or says it could not",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="for a Dot that shows no light and needs its test point shorted:"
        " wait for its bootrom, say when the short may come off, then go on",
    )
    parser.add_argument(
        "target",
        choices=tuple(TARGETS),
        default=AMONET_BISCUIT_V1_1_0_BBOE,
        help="the target, one of those listed below",
        metavar="TARGET",
        nargs="?",
    )
    parser.add_argument(
        "build",
        choices=sorted(BUILDS),
        help="with stock, and only with stock: the build to install, one of "
        + ", ".join(sorted(BUILDS)),
        metavar="BUILD",
        nargs="?",
    )
    options = parser.parse_intermixed_args()
    target = TARGETS[options.target]
    if (target.installs == FireOs6(build=None)) != (options.build is not None):
        parser.error(
            message="stock takes a BUILD, and no other target does: "
            + ", ".join(sorted(BUILDS))
        )
    ARGUMENTS.build = options.build or ""
    ARGUMENTS.target = target
    ARGUMENTS.verbose = options.verbose
    for tool in ("adb", "fastboot"):
        if not shutil.which(cmd=tool):
            _die(message=tool + " not found: install Android platform-tools")
    check_user()
    check_adb()
    move_old_caches()
    SESSION.short = options.short
    if options.report:
        report()
        return
    if options.write_test:
        write_test()
        return
    root()


def countdown() -> None:
    text = "The bootrom answered. The short may come off now; continuing{}."
    if not sys.stdout.isatty():
        warn(text=text.format(f" in {SHORT_WAIT} s"))
        time.sleep(SHORT_WAIT)
        return
    for left in range(SHORT_WAIT, 0, -1):
        status(text=text.format(f" in {left} s"))
        time.sleep(1)
    status(text=text.format(""))
    print()


def downgrade() -> bool:
    amonet = unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    wheel = pyserial_wheel()
    if getvar(name="unlock_status").lower() != "true":
        _die(message="not in amonet's fastboot")
    little_kernel = getvar(name="lk_build_desc")
    if not LITTLE_KERNEL_DESCRIPTION.fullmatch(string=little_kernel):
        _die(
            message="the Dot did not report its bootloader version;"
            " boot0 was not erased. " + again()
        )
    if little_kernel == LK.FIREOS5.value:
        _die(message="the Dot already runs amonet v1.1.0's bootloader. " + again())
    PROGRESS.begin(
        estimate="5 s", label="erasing boot0 so the Dot falls into its bootrom"
    )
    bootrom_step(
        amonet=amonet,
        erase=erase_by_fastboot,
        payload=amonet_v2_0_0_payload(),
        wheel=wheel,
    )
    return amonet_v1_1_0_recovery()


def download(*, build: str) -> pathlib.Path:
    build_details = BUILDS[build]
    CACHE.mkdir(exist_ok=True, parents=True)
    update = (
        CACHE / f"update-kindle-biscuit_puffin-{build_details.ns}_user_{build}"
        f"_{build_details.number.zfill(13)}.bin"
    )
    if update in SESSION.verified:
        return update
    if (
        not update.is_file()
        or digest(kind="sha256", path=update) != build_details.sha256
    ):
        page = (
            f"{FTVDB}{build_details.md5}-{build_details.number}-fire-os-{build_details.ftvdb_version}-{build_details.ns.lower()}"
            f"-{build}-{build_details.date}/"
        )
        request = urllib.request.Request(
            headers={"User-Agent": "Mozilla/5.0"}, url=page
        )
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            with urllib.request.urlopen(timeout=60, url=request) as response:
                links = re.findall(
                    pattern=r'https://[^"<> ]+\.bin',
                    string=response.read().decode(errors="replace"),
                )
            if not links:
                _die(message="no download link on " + page)
            part = CACHE / (update.name + ".part")
            response = urllib.request.urlopen(timeout=60, url=links[0])
            with response, part.open(mode="wb") as part_file:
                done, total = save(
                    destination=part_file,
                    label=f"downloading OTA {build}",
                    response=response,
                )
        except (OSError, http.client.HTTPException) as error:
            _die(message=f"the download failed: {error!r}")
        if total and done != total:
            _die(
                message=f"the download stopped after {done} of {total} bytes. "
                + again()
            )
        part.replace(target=update)
    if digest(kind="sha256", path=update) != build_details.sha256:
        _die(message=f"{update} does not hash to {build_details.sha256}")
    SESSION.verified.add(update)
    if threading.current_thread() is threading.main_thread():
        passed(message=f"OTA {build} verified")
    return update


def emos(*, action: str) -> str:
    if action != "find" and ARGUMENTS.verbose:
        show(
            text=f"{clock()} $ "
            + shlex.join(split_command=child(arguments=[action], name="emos"))
        )
    output = subprocess.run(
        args=child(arguments=[action, USER_SERIAL or ""], name="emos"),
        capture_output=True,
        check=False,
        cwd=CACHE,
        env=dict(os.environ, PYTHONPATH=child_path(wheel=pyserial_wheel())),
        text=True,
        timeout=30,
    ).stdout.strip()
    if output.isdigit() and int(output) > 1:
        _die(message=MORE_THAN_ONE)
    return output


def emos_recovery() -> None:
    answer = emos(action="recovery")
    if answer == "password":
        _die(
            message="emOS's console asks for a password. Type /init recovery at"
            " the console, or clear the console password in EchoMuse's"
            " dashboard, then run this again."
        )
    if answer == "denied":
        _die(message=NO_ACCESS + rerun())
    if answer != "recovery":
        _die(message="emOS's serial console did not answer. Run this again.")


def emos_stage() -> None:
    emos_recovery()
    PROGRESS.begin(estimate="40 s", label="waiting for recovery to start")


def erase_by_fastboot() -> str:
    erased = run(arguments=["fastboot", "erase", "boot0"], timeout=60)
    if erased.returncode != 0:
        ERASED.unlink(missing_ok=True)
        return f"fastboot erase boot0 failed:\n{erased.stdout}"
    rebooted = run(arguments=["fastboot", "reboot"], timeout=60)
    if rebooted.returncode != 0:
        return f"fastboot reboot failed:\n{rebooted.stdout}"
    return ""


def exploit(*, client: Bootrom, payload: pathlib.Path) -> Client:
    data = payload.read_bytes()
    try:
        client.disable_watchdog()
        if SESSION.short:
            countdown()
        range_check.defeat(bootrom=client)
        live = start_payload(bootrom=client, client=Client, payload=data)
    except NotReadyError as error:
        _die(
            message=f"the payload did not start{short_hint()}: {error}."
            f" {unwritten()} Unplug the Dot. " + again()
        )
    except (OSError, UsbdlError) as error:
        _die(
            message=f"the exploit did not go through the Dot's bootrom: {error}."
            f" {unwritten()} Unplug the Dot. " + again()
        )
    return live


def fastbrick() -> None:
    amonet = unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    if getvar(name="product") != "BISCUIT":
        _die(message="fastboot reports a product other than BISCUIT")
    little_kernel = getvar(name="lk_build_desc")
    if not little_kernel:
        _die(
            message="fastboot did not report the bootloader version;"
            " the Dot was not modified"
        )
    image = "bin/fastbrick.img"
    if little_kernel in {LK.FIREOS6.value, LK.FIREOS6_4315.value}:
        image = "bin/fastbrick-20221007.img"
    PROGRESS.begin(estimate="10 s", label="unlocking with amonet v2.0.0")
    for attempt in range(10):
        if attempt:
            time.sleep(2)
        arguments = ["fastboot", "-S", "256M", "flash", "brick", image]
        try:
            output = run(arguments=arguments, directory=amonet, timeout=8).stdout
            started = False
        except subprocess.TimeoutExpired as error:
            output = (error.output or b"").decode(encoding="utf-8", errors="replace")
            started = True
        if "eMMC-RO" in output:
            _die(message="the Dot's eMMC is read-only; it was not modified")
        if "Device mismatch" in output:
            _die(message="the payload rejected this device; it was not modified")
        if started:
            PROGRESS.begin(
                estimate="40 s", label="waiting for v2.0.0 recovery to start"
            )
            return
    _die(
        message=f"the unlock did not start after 10 attempts, with {image} for"
        f" the bootloader {little_kernel}; the Dot was not modified"
    )


def hide_updater() -> None:
    def hidden() -> bool:
        output = adb_shell(command=f"su -c 'dumpsys package {UPDATER}'", timeout=60)
        return any(
            line.strip().startswith("User 0:") and "hidden=true" in line
            for line in output.split(sep="\n")
        )

    if not hidden():
        adb_shell(command=f"su -c 'pm hide {UPDATER}'", timeout=60)
    if not hidden():
        _die(
            message=f"{UPDATER} is not hidden; an update would replace the"
            " boot image and remove root"
        )


def install_fireos(*, reboot: bool = True, slot: str = "") -> None:
    fireos = fetch(download=ARGUMENTS.target.installs.package)
    magisk = fetch(download=MAGISK)
    slot = slot or adb_shell(command="getprop ro.boot.slot_suffix", timeout=30)
    if slot not in {"_a", "_b"}:
        _die(message=f"TWRP reports the boot slot {slot!r}, not _a or _b")
    boot, system = f"{BY_NAME}/boot{slot}_x", f"{BY_NAME}/system{slot}"
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        work = pathlib.Path(temporary)
        PROGRESS.begin(estimate="5 s", label="formatting userdata")
        if not adb_script(body=Shell.DATA.value, name="data.sh", work=work):
            _die(message="userdata did not format and mount")
        PROGRESS.begin(estimate="100 s", label="writing Fire OS 5.5.5.4's /system")
        slices, want, blocks = system_image(package=ARGUMENTS.target.installs.package)
        write_system(blocks=blocks, slices=slices, system=system, want=want)
        body = Shell.SYSTEM.value.format(hosts=" ".join(UPDATE_HOSTS), system=system)
        if not adb_script(body=body, name="system.sh", work=work):
            _die(message="patching /system failed")

        PROGRESS.begin(estimate="5 s", label="writing the boot image")
        data = boot_image(fireos=fireos, magisk=magisk)
        image = work / "boot.img"
        image.write_bytes(data=data.ljust(-(-len(data) // 4096) * 4096, b"\0"))
        final = DOT_TEMPORARY_DIRECTORY / "boot.img"
        push_checked(local=image, remote=final)
        adb_shell(
            command=Shell.WRITE.value.format(source=final, target=boot),
            timeout=120,
        )
        blocks = image.stat().st_size // 4096
        read_back = (
            f"[ -b {boot} ] && dd if={boot} bs=4096 count={blocks} 2>/dev/null | md5sum"
        )
        want = digest(kind="md5", path=image)
        written = (
            adb_shell(command=read_back, timeout=120)
            .split(sep="\n")[-1]
            .split(sep=" ")[0]
        )
        if written != want:
            _die(
                message="the patched boot image did not verify on the Dot: read"
                f" {written or 'nothing'}, expected {want}"
            )

        PROGRESS.begin(estimate="5 s", label="installing Magisk 17.3")
        install_magisk(magisk=magisk, work=work)
    if reboot:
        PROGRESS.begin(estimate="4 min", label="waiting for rooted Fire OS 5 to boot")
        run(arguments=["adb", "reboot"])


def install_fireos6() -> None:
    amonet_chain()
    build = ARGUMENTS.target.installs.build
    update_file = download(build=build)
    zip_path = fetch(download=BOOT_ROOT)
    if "boot_a_x" in partition_table():
        _die(
            message="v2.0.0's TWRP runs on amonet v1.1.0's partition table. " + again()
        )
    PROGRESS.begin(estimate="10 s", label="wiping cache and data")
    for part in ("cache", "data"):
        adb_shell(command="twrp wipe " + part, timeout=120)
    update = "/sdcard/update.zip"
    for index, slot in enumerate(iterable=("first", "second")):
        PROGRESS.begin(
            estimate="2 min",
            label=f"installing Fire OS 6 {build}, {slot} slot",
        )
        if index:
            run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)
            wait_for_twrp()
        push_checked(local=update_file, remote=update)
        before = adb_shell(command="bcbtool get_active", timeout=30)
        adb_shell(command="twrp install " + update, timeout=600)
        after = adb_shell(command="bcbtool get_active", timeout=30)
        if {before, after} != {"a", "b"}:
            _die(
                message=f"installing Fire OS 6 {build} left the"
                f" active slot {after!r}, where it was {before!r}. " + again()
            )
    PROGRESS.begin(estimate="10 s", label="installing boot-root")
    push_checked(local=zip_path, remote="/sdcard/boot-root.zip")
    output = adb_shell(command="twrp install /sdcard/boot-root.zip", timeout=300)
    errors = [line for line in output.split(sep="\n") if "(!) Error" in line]
    if errors:
        _die(message="boot-root.zip failed: " + errors[0])
    PROGRESS.begin(estimate="1 min", label="waiting for rooted Fire OS 6 to boot")
    run(arguments=["adb", "reboot"])


def install_magisk(*, magisk: pathlib.Path, work: pathlib.Path) -> None:
    database = work / "magisk.db"
    magisk_db(path=database)
    files = magisk_files(database=database.read_bytes(), magisk=magisk)
    archive = work / "magisk.cpio"
    archive.write_bytes(data=cpio(files=files))
    push_checked(local=archive, remote=DOT_TEMPORARY_DIRECTORY / "magisk.cpio")
    if not adb_script(body=Shell.MAGISK.value, name="magisk.sh", work=work):
        _die(message="Magisk 17.3 did not install")
    names = sorted(name for name, (mode, _) in files.items() if stat.S_ISREG(mode))
    want = hashlib.md5(
        b"".join(files[name][1] for name in names), usedforsecurity=False
    ).hexdigest()
    paths = " ".join(name.decode() for name in names)
    got = (
        adb_shell(command=f"cd /; cat {paths} | md5sum")
        .split(sep="\n")[-1]
        .split(sep=" ")[0]
    )
    if got != want:
        _die(message="Magisk 17.3's files did not verify on the Dot")


def into_recovery(*, line: Callable[[str, object], None]) -> bool:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    asked = False
    waiting = ""
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        if in_fastboot():
            unlocked = getvar(name="unlock_status")
            for name, value in (
                ("product", getvar(name="product")),
                ("unlock_status", unlocked),
                ("lk_build_desc", getvar(name="lk_build_desc")),
            ):
                line("fastboot " + name, value or "<nothing>")
            if not unlocked:
                say(
                    text="This Dot's fastboot did not say whether it is unlocked,"
                    " so this stops rather than guess. Check the cable, and that no"
                    " other program holds the Dot, then run it again."
                )
                return False
            if unlocked.lower() != "true":
                say(
                    text="This Dot's bootloader is locked, so it holds no recovery"
                    " to collect from and nothing here can give it one. Root it"
                    " first: run firebreak again without --report, and follow"
                    " what it asks."
                )
                return False
            PROGRESS.begin(estimate="40 s", label="restarting the Dot in its recovery")
            run(arguments=["fastboot", "oem", "reboot-recovery"], timeout=60)
        else:
            adb_state = ""
            if usb_serial():
                adb_state = run(arguments=["adb", "get-state"], timeout=30).stdout
            adb_state = adb_state.strip()
            if adb_state == "recovery":
                if not adb_shell(command="getprop ro.twrp.version", timeout=30)[
                    :1
                ].isdigit():
                    say(
                        text="This Dot is in a recovery that is not TWRP, so it"
                        " holds nothing to collect from. It is left as it is."
                    )
                    return False
                if "mtp" in adb_shell(command="getprop sys.usb.config", timeout=30):
                    PROGRESS.end()
                    return True
                if waiting != "twrp":
                    waiting = "twrp"
                    status(text="Waiting for TWRP to finish starting.")
                time.sleep(2)
                continue
            if adb_state == "device":
                if "uid=0" not in adb_shell(command="id; su -c id", timeout=30):
                    say(
                        text="This Dot runs Fire OS without root, so its recovery"
                        " is Amazon's, which holds nothing to collect from. Root it"
                        " first: run firebreak again without --report, and follow"
                        " what it asks."
                    )
                    return False
                PROGRESS.begin(
                    estimate="40 s", label="restarting the Dot in its recovery"
                )
                run(arguments=["adb", "reboot", "recovery"], timeout=60)
            else:
                if not asked:
                    asked = True
                    say(
                        text="The rest of this report comes from the Dot's recovery."
                        " Start the Dot in fastboot mode and this goes on by itself. "
                        + FASTBOOT_MODE
                        + " A Dot already unlocked with amonet v2.0.0 has no"
                        " fastboot: hold the + button instead while you plug it back"
                        " in, which starts its TWRP. A Dot that shows nothing on USB"
                        " is in its bootrom, and only a root run brings it back."
                        " Ctrl-C stops this."
                    )
                if waiting != "fastboot":
                    waiting = "fastboot"
                    status(
                        text="Waiting for the Dot in fastboot mode, with a green ring."
                    )
                time.sleep(2)
                continue
        try:
            run(arguments=["adb", "wait-for-recovery"], timeout=180)
        except subprocess.TimeoutExpired:
            PROGRESS.halt()
            say(
                text="The Dot did not come back in a recovery that answers adb"
                " within 3 minutes. It is most likely in Amazon's recovery, which a"
                " root run replaces: run firebreak again without --report."
            )
            return False
        time.sleep(5)
    PROGRESS.halt()
    return False


def keep_trying(*, message: str) -> None:
    said = message + ". The run keeps trying."
    if not SESSION.short:
        PROGRESS.note(message=said)
        return
    if sys.stdout.isatty():
        print()
    warn(text=said)
    status(text="Waiting for the bootrom.")


def main() -> None:
    if sys.argv[1:2] == ["_child"]:
        sys.exit(child_main(arguments=sys.argv[3:], name=sys.argv[2]))
    try:
        cli()
    except KeyboardInterrupt:
        _die(message="stopped", prefix="")
    except subprocess.TimeoutExpired as error:
        _die(
            message=f"{' '.join(map(str, error.cmd))} did not finish in"
            f" {error.timeout:.0f} seconds"
        )


def open_bootrom(*, failures: dict[str, float], name: str) -> serial.Serial | None:
    try:
        return open_serial_port(name=name, write_timeout=BOOTROM_WRITE_TIMEOUT)
    except OSError as error:
        first = failures.setdefault(name, time.monotonic())
        if first and time.monotonic() - first >= OPEN_GRACE:
            failures[name] = 0
            keep_trying(message=f"Cannot open {name}: {error}")
        return None


def open_serial_port(*, name: str, write_timeout: float) -> serial.Serial:
    import serial  # ruff: ignore[import-outside-top-level]

    return serial.Serial(
        baudrate=BAUD_RATE,
        port=name,
        timeout=READ_TIMEOUT,
        write_timeout=write_timeout,
    )


def poke_live_payload() -> None:
    poked = []
    for name in sorted(mediatek_ports()):
        with (
            contextlib.suppress(OSError),
            open_serial_port(name=name, write_timeout=POKE_WRITE_TIMEOUT) as connection,
        ):
            Payload(port=connection).reboot()
            poked.append(name)
    deadline = time.monotonic() + POKE_GONE_WAIT
    for name in poked:
        await_port_gone(deadline=deadline, name=name)


def prebuild() -> None:
    with contextlib.suppress(Exception, SystemExit):
        system_image(package=ARGUMENTS.target.installs.package)


def predownload() -> None:
    with contextlib.suppress(Exception, SystemExit):
        prefetch()


DOWNLOADER = threading.Thread(daemon=True, target=predownload)


def prefetch() -> None:
    if DOWNLOADER.is_alive() and threading.current_thread() is threading.main_thread():
        show(text="Finishing the downloads.")
    unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    installs = ARGUMENTS.target.installs
    if isinstance(installs, FireOs6):
        build = ARGUMENTS.build or installs.build
        with hold(lock=lock_for(key=build)):
            download(build=build)
        return
    unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    pyserial_wheel()
    fetch(download=installs.package)
    fetch(download=MAGISK)
    fetch(download=TWRP)
    threading.Thread(daemon=True, target=prebuild).start()


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
        if version != TWRP_VERSION:
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
    except SystemExit as stop:
        plain = re.sub(pattern=r"\x1b\[[0-9;]*m", repl="", string=str(stop))
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


def remaining(*, start: State, table: dict[State, Stage]) -> int | None:
    total = 0
    for _ in range(len(table) + 1):
        if start == ARGUMENTS.target.goal:
            return total
        stage = table.get(start)
        if stage is None or stage.then is None:
            return None
        total += stage.steps
        start = stage.then
    return None


def replace_twrp() -> None:
    twrp = fetch(download=TWRP)
    PROGRESS.begin(estimate="40 s", label=f"waiting for TWRP {TWRP_VERSION}")
    remote = DOT_TEMPORARY_DIRECTORY / TWRP.name
    push_checked(local=twrp, remote=remote)
    recovery = f"{BY_NAME}/recovery"
    adb_shell(
        command=Shell.WRITE.value.format(source=remote, target=recovery),
        timeout=120,
    )
    sectors = twrp.stat().st_size // 512
    read_back = (
        f"[ -b {recovery} ] && dd if={recovery} bs=512 count={sectors} 2>/dev/null"
        " | md5sum"
    )
    written = (
        adb_shell(command=read_back, timeout=120).split(sep="\n")[-1].split(sep=" ")[0]
    )
    if written != digest(kind="md5", path=twrp):
        _die(
            message=f"TWRP {TWRP_VERSION} did not verify in recovery. Leave the Dot"
            " running. " + again()
        )
    run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)


def report() -> None:
    def line(label: str, value: object) -> None:
        show(text=labelled(label=label, value=value))

    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            said = adb_shell(command=command, timeout=timeout)
        except subprocess.TimeoutExpired:
            return "<timed out>"
        return masked(text=said) or "<nothing>"

    show(text=SUPPORT + "\n")
    line("firebreak", " ".join(pathlib.Path(word).name for word in program()[1:]))
    line("host", f"{sys.platform} ({os.name}), {platform.platform()}")
    line("python", sys.version.split()[0])
    said = run(arguments=["adb", "version"], timeout=30).stdout.split(sep="\n")
    line("adb", ", ".join(part.strip() for part in said[:2] if part.strip()))
    line("state", probed())
    if not into_recovery(line=line):
        show(text="\nThe report stops with what is above.")
        return
    line("state in recovery", probed())
    for text in dot_details(asked=asked):
        show(text=text)
    held = CACHE / f"system-{FIREOS.sha256[:12]}" / "md5"
    want, needs = system_record(text=held.read_text() if held.is_file() else "")
    if needs:
        line("system image", f"{needs} bytes, md5 {want}")
    else:
        line("system image", "not built yet, so its size is unknown")
    partitions = whole(
        marker=PARTITIONS_OK,
        said=asked(command=f"cat /proc/partitions; echo {PARTITIONS_OK}"),
    )
    listing = whole(
        marker=LISTING_OK, said=asked(command=f"ls -l {BY_NAME}/; echo {LISTING_OK}")
    )
    names = None if listing is None else node_names(listing=listing)
    for label, value in system_a_rows(names=names, needs=needs, partitions=partitions):
        line(label, value)
    show(text="\npartition table, with each name's node and any other name for it")
    printed = asked(command=f"sgdisk --print {DISK}; echo {TABLE_OK}", timeout=120)
    for row in partition_rows(names=names, printed=printed):
        show(text=row)
    show(text="\nwhat the kernel says about the eMMC")
    for text in mmc_said(asked=asked):
        show(text=text)
    show(text="\n" + LEFT_IN_RECOVERY)


def restore(
    *,
    backup_sector: int,
    build: str,
    files: dict[str, pathlib.Path],
    parts: dict[str, Partition],
    work: pathlib.Path,
) -> None:
    unmount()

    PROGRESS.begin(estimate="5 s", label="clear the preloader header (boot0)")
    ERASED.touch()
    clear_boot0()
    PROGRESS.end()

    for step in WRITES:
        write(
            estimate=step.estimate,
            label=step.label,
            number=parts[step.partition].number,
            path=files[step.image],
            sector=parts[step.partition].first,
        )
    write(
        estimate="5 s",
        label="write the stock table (backup)",
        path=files["gpt-backup.bin"],
        sector=backup_sector,
    )
    write(
        estimate="5 s",
        label="write the stock table (primary)",
        path=files["gpt-primary.bin"],
        sector=0,
    )

    PROGRESS.begin(estimate="30 s", label="format cache and userdata")
    if "No problems found" not in adb_shell(command="sgdisk --verify " + DISK):
        restore_failed(message="sgdisk does not accept the new table; do not reboot")
    unmount(started=True)
    adb_shell(command="blockdev --rereadpt " + DISK)
    if adb_shell(command='grep -c "mmcblk0p1[78]$" /proc/partitions') != "0":
        restore_failed(
            message="the kernel still sees amonet's partitions; do not reboot,"
            " reread the table first"
        )
    userdata, cache = parts["userdata"], parts["cache"]
    kibibytes = userdata.size // 1024
    if not adb_shell(
        command=f'grep " {kibibytes} mmcblk0p{userdata.number}$" /proc/partitions'
    ):
        restore_failed(message="userdata is not its stock size; do not reboot")
    output = adb_shell(
        command=f"mke2fs -q -t ext4 {DISK}p{cache.number}"
        f" && mke2fs -q -t ext4 {DISK}p{userdata.number} && echo formatted"
    )
    if output.split(sep="\n")[-1] != "formatted":
        restore_failed(message="cache and userdata did not format; do not reboot")
    PROGRESS.end()

    for step in chain_writes():
        write(
            estimate=step.estimate,
            label=step.label,
            number=parts[step.partition].number,
            path=files[step.image],
            sector=parts[step.partition].first,
        )

    PROGRESS.begin(estimate="5 s", label="write preloader to boot0")
    preloader = work / "preloader.img"
    staged = DOT_TEMPORARY_DIRECTORY / "pl.img"
    if run(arguments=["adb", "push", preloader, staged], timeout=120).returncode != 0:
        restore_failed(message="the preloader did not reach the Dot; do not reboot")
    adb_shell(command=Shell.BOOT0.value.format(source=staged))
    wrong = md5_mismatch(
        command="md5sum /dev/block/mmcblk0boot0",
        want=digest(kind="md5", path=preloader),
    )
    if wrong:
        restore_failed(
            message=f"boot0 does not match the {build} preloader{wrong}; do not reboot"
        )
    ERASED.unlink(missing_ok=True)
    PROGRESS.end()

    PROGRESS.begin(estimate="90 s", label=f"waiting for stock {build} to start")
    with contextlib.suppress(subprocess.TimeoutExpired):
        run(arguments=["adb", "shell", "-n", "reboot"], timeout=60)


def restore_stage() -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    build = ARGUMENTS.build
    work = CACHE / ("stock-" + build)
    work.mkdir(exist_ok=True, parents=True)
    extract(update=download(build=build), work=work)
    deadline = time.monotonic() + 30
    version = ""
    while not version or "mtp" not in adb_shell(command="getprop sys.usb.config"):
        if time.monotonic() > deadline:
            _die(message="TWRP did not finish starting within 30 seconds")
        time.sleep(1)
        version = adb_shell(command="getprop ro.twrp.version")
        if not version[:1].isdigit():
            version = ""
        elif not version.startswith(TWRP_VERSIONS):
            _die(
                message="this needs a TWRP for this Dot: v1.1.0's 3.2.3,"
                f" v2.0.0's 3.7.0, or the {TWRP_VERSION} that firebreak"
                " installs"
            )
    if (
        adb_shell(command="toybox dd --help >/dev/null 2>&1 && echo yes").split(
            sep="\n"
        )[-1]
        == "yes"
    ):
        SESSION.dd = "toybox dd"
    tools = adb_shell(command=Shell.TOOLS.value).split(sep="\n")[-1]
    if not tools.startswith("tools:"):
        _die(message="the Dot did not answer which tools it has: " + tools)
    if tools != "tools:":
        _die(message="this TWRP has no" + tools[len("tools:") :])
    device = adb_shell(command="getprop ro.product.device")
    if device != "biscuit":
        _die(
            message="this is not an Echo Dot (2nd Gen): TWRP reports the"
            f" device {device!r}"
        )

    raw = read_sectors(count=34, start=0)
    if not gpt_intact(entries=raw[1024:], header=raw[512:1024]):
        size = adb_shell(command=f"blockdev --getsize64 {DISK}")
        if not size.isdigit():
            _die(message="could not read the Dot's disk size")
        tail = read_sectors(count=33, start=int(size) // 512 - 33)
        raw = raw[:512] + tail[-512:] + tail[:-512]
        show(text="the primary partition table is damaged; using the backup")
    saved = work / f"current-gpt-{os.environ['ANDROID_SERIAL']}.bin"
    if not saved.exists():
        saved.write_bytes(data=raw)
    table = stock_gpt(raw=raw)
    files = {}
    for name, data in (
        ("gpt-primary.bin", table.primary),
        ("gpt-backup.bin", table.backup),
    ):
        files[name] = work / name
        files[name].write_bytes(data=data)
    boot = work / "boot.img"
    boot_size = table.partitions["boot_a"].size
    files["boot"] = work / "boot16.img"
    files["boot"].write_bytes(data=boot.read_bytes().ljust(boot_size, b"\0"))
    files["expdb"] = work / "expdb.zero"
    files["expdb"].write_bytes(data=b"\0" * table.partitions["expdb"].size)
    misc = bytearray(table.partitions["misc"].size)
    misc[
        BOOTLOADER_CONTROL_BLOCK_OFFSET : BOOTLOADER_CONTROL_BLOCK_OFFSET
        + len(BOOTLOADER_CONTROL_BLOCK)
    ] = BOOTLOADER_CONTROL_BLOCK
    files["misc"] = work / "misc.img"
    files["misc"].write_bytes(data=misc)
    for image in ("system", "tee", "lk"):
        files[image] = work / (image + ".img")
    for step in (*WRITES, *chain_writes()):
        if files[step.image].stat().st_size > table.partitions[step.partition].size:
            _die(message=f"{files[step.image].name} does not fit {step.partition}")
    if (
        adb_shell(command="[ -b /dev/block/mmcblk0boot0 ] && echo block").split(
            sep="\n"
        )[-1]
        != "block"
    ):
        _die(
            message="/dev/block/mmcblk0boot0 is not a block device, so the"
            " preloader would be written to a file and read back from it"
        )
    boot0 = adb_shell(command="cat /sys/block/mmcblk0boot0/size")
    if (
        not boot0.isdigit()
        or (work / "preloader.img").stat().st_size != int(boot0) * 512
    ):
        _die(message=f"preloader.img is not the size of boot0 ({boot0} sectors)")
    passed(message="stock partition table built from this Dot's own")
    warn(
        text="About to overwrite this Dot's bootloaders, system and data with"
        f" stock {build}."
    )
    warn(text="Root is gone afterwards; firebreak puts it back.")
    try:
        for left in range(10, 0, -1):
            show(
                end="",
                flush=True,
                kind=Kind.WARN,
                text="\r"
                + paint(
                    code=ANSIColor.YELLOW,
                    text=f"Starting in {left:2d} s. Ctrl-C cancels.",
                ),
            )
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        _die(message="stopped; nothing was written", prefix="")
    show(
        kind=Kind.WARN,
        text="\r"
        + paint(code=ANSIColor.YELLOW, text="Starting now.                     "),
    )

    try:
        restore(
            backup_sector=table.backup_sector,
            build=build,
            files=files,
            parts=table.partitions,
            work=work,
        )
    except subprocess.TimeoutExpired as error:
        restore_failed(
            message=f"{' '.join(map(str, error.cmd))} did not finish in"
            f" {error.timeout:.0f} seconds. Do not reboot. " + again()
        )
    except KeyboardInterrupt:
        if PROGRESS.step == PROGRESS.steps:
            _die(message=f"stopped; stock {build} is in place", prefix="")
        restore_failed(message="stopped part way. Do not reboot. " + again())


def root() -> None:  # ruff: ignore[complex-structure, too-many-branches, too-many-locals, too-many-statements]
    usage = run(arguments=["fastboot", "--help"], timeout=30).stdout
    if not any(line.split()[:1] == ["-S"] for line in usage.splitlines()):
        _die(
            message="this fastboot has no -S option: install a newer"
            " Android platform-tools"
        )
    done: set[State] = set()
    table = stages()
    target = ARGUMENTS.target
    guided = False
    resumed = False
    seen = None
    shown = None
    deadline = None
    while True:
        current = state()
        installed = (
            target.goal == State.AMONET_V2_0_0_BOOTED
            and State.AMONET_V2_0_0_TWRP in done
        )
        restored = target.unlock is None and bool(done & TWRPS)
        gesture = current == State.AMONET_V2_0_0_FASTBOOT and current not in table
        if (
            DOWNLOADER.ident is None
            and current not in {State.BOOTED, State.STARTING, *ROOTED}
            and not (
                target.unlock is None
                and current in {State.STOCK_BOOTED, State.STOCK_FASTBOOT}
            )
        ):
            DOWNLOADER.start()
        if current not in {State.NONE, State.STARTING, *TWRPS}:
            ERASED.unlink(missing_ok=True)
        SESSION.boot0_marker = ERASED
        if current != State.NONE:
            SESSION.short = False
        if current == State.NONE and (ERASED.exists() or SESSION.short) and not resumed:
            if target.goal == State.AMONET_V2_0_0_BOOTED:
                fetch(download=BOOT_ROOT)
            prefetch()
            resumed = True
            done.difference_update(TWRPS)
            done.add(State.AMONET_V1_1_0_FASTBOOT)
            if not SESSION.short:
                say(
                    code=ANSIColor.YELLOW,
                    text="The last run stopped after it erased boot0, so the Dot"
                    " cannot start. This run writes amonet v1.1.0 through the"
                    " bootrom, then goes on from v1.1.0's TWRP. If nothing"
                    " happens within a minute, unplug the Dot and plug it back"
                    " in.",
                )
            left = remaining(start=State.AMONET_V1_1_0_BBOE_TWRP, table=table)
            if left is not None:
                PROGRESS.steps = PROGRESS.step + (2 if SESSION.short else 3) + left
            if bootrom_step(
                amonet=unpack(download=AMONET_BISCUIT_V1_1_0_ZIP),
                erase=None,
                payload=amonet_v2_0_0_payload(),
                wheel=pyserial_wheel(),
            ):
                amonet_v1_1_0_recovery()
            else:
                done.discard(State.AMONET_V1_1_0_FASTBOOT)
                resumed = False
            seen = None
            continue
        if current != seen:
            seen = current
            deadline = time.monotonic() + WAIT
            if ARGUMENTS.verbose and current != shown:
                shown = current
                show(text=f"{clock()} state: {current.value}")
            if (
                current not in done
                and current not in {State.NONE, State.STARTING, State.BOOTED}
                and not (current == State.STOCK_BOOTED and installed)
            ):
                PROGRESS.end()
            if (
                current == State.BOOTED
                and not PROGRESS.open
                and target.unlock is not None
            ):
                show(text="The Dot is starting Fire OS. Waiting for it to finish.")
            elif current == State.STOCK_BOOTED and installed:
                deadline = time.monotonic() + MINUTE
            elif current == State.STOCK_BOOTED and target.unlock is not None:
                guided = True
                say(
                    text="This Dot appears to be unmodified. To unlock and root it,"
                    " start it in fastboot mode. "
                    + FASTBOOT_MODE
                    + " A Dot already unlocked with amonet v2.0.0 has no fastboot:"
                    " hold the + button instead while you plug it back in, which"
                    " starts its TWRP."
                )
            elif current == State.EMOS and current not in done:
                say(
                    text="This Dot runs EchoMuse's emOS. Rebooting it into recovery"
                    " through its serial console."
                )
            elif gesture:
                say(
                    text="This Dot is in amonet v2.0.0's fastboot. Unplug it, and"
                    " hold the + button while you plug it back in: that starts"
                    " v2.0.0's TWRP."
                )
            elif (
                current == State.AMONET_V2_0_0_BOOTED
                and current not in done
                and current != target.goal
            ):
                say(
                    text="This Dot runs rooted Fire OS 6 on amonet v2.0.0."
                    " Rebooting it into recovery."
                )
            elif current == State.NONE and not done and not PROGRESS.open and guided:
                show(text="Waiting for the Dot in fastboot mode, with a green ring.")
            elif current == State.NONE and not done and not PROGRESS.open:
                guided = True
                say(
                    text="Waiting for a Dot on USB. Connect it with a USB cable."
                    " A Dot that runs Amazon's own software needs fastboot mode. "
                    + FASTBOOT_MODE
                    + " Ctrl-C stops the script."
                )
        if current == State.AMONET_V2_0_0_BOOTED == target.goal:
            version = adb_shell(command="getprop ro.build.version.name")
            warn(text=f"The Dot is rooted: {version}, with root adb.")
            cache_note()
            return
        if target.unlock is None and current in {
            State.STOCK_BOOTED,
            State.STOCK_FASTBOOT,
        }:
            if done:
                passed(message=f"The Dot runs stock {ARGUMENTS.build}.")
                warn(
                    text="If you will root it again, do not set it up in the Alexa app"
                    " first: on Wi-Fi it can take an update to a build"
                    " firebreak does not support."
                )
            else:
                say(
                    text="This Dot appears to run stock Fire OS 6, so there is"
                    " nothing to restore. However, if you unlocked it with amonet"
                    " v2.0.0, hold its + button while you plug it in. That starts"
                    " its TWRP. Then run this again."
                )
            cache_note()
            return
        if current == target.goal:
            hide_updater()
            version = adb_shell(command="getprop ro.build.version.name")
            selinux = adb_shell(command="getenforce")
            warn(
                text=f"The Dot is rooted: {version}, SELinux {selinux},"
                f" {UPDATER} hidden."
            )
            cache_note()
            return
        if (
            gesture
            or current in done
            or current in {State.NONE, State.STOCK_BOOTED, State.STARTING}
            or (current == State.BOOTED and target.unlock is not None)
        ):
            waits = {State.NONE} if installed else {State.NONE, State.STOCK_BOOTED}
            if restored:
                waits = set()
            if not gesture and current not in waits and time.monotonic() > deadline:
                if restored:
                    _die(
                        message=f"stock {ARGUMENTS.build} has not started"
                        f" {WAIT // 60} minutes after the restore"
                    )
                if current == State.STOCK_BOOTED:
                    _die(
                        message="Fire OS 6 started without root adb, so"
                        " boot-root.zip did not take. " + again()
                    )
                if current == State.BOOTED:
                    _die(
                        message="Fire OS has not finished booting with root."
                        " Reboot to recovery. " + again()
                    )
                _die(
                    message=f"the Dot has been {current.value} for"
                    f" {WAIT // 60} minutes. " + again()
                )
            time.sleep(2)
            continue
        if not done:
            if target.goal == State.AMONET_V2_0_0_BOOTED:
                fetch(download=BOOT_ROOT)
            if isinstance(target.installs, FireOs6) or current not in ROOTED:
                prefetch()
            warn(text="Keep the Dot plugged in until firebreak finishes.")
        done.add(current)
        stage = table.get(current)
        if stage:
            left = remaining(start=current, table=table)
            PROGRESS.steps = 0 if left is None else PROGRESS.step + left
            if stage.run() is not False:
                done.update(stage.passes)
        seen = None


def rooted() -> State:
    images = {
        State.ROOTED_AMONET_V1_1_0_BBOE: fetch(download=TWRP),
        State.ROOTED_AMONET_V1_1_0: unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
        / "bin"
        / "twrp.img",
    }
    data = read_recovery(size=max(image.stat().st_size for image in images.values()))
    for found, image in images.items():
        size = image.stat().st_size
        if hashlib.md5(data[:size], usedforsecurity=False).hexdigest() == digest(
            kind="md5", path=image
        ):
            return found
    return State.ROOTED


def say_missed_short(*, count: int) -> None:
    if sys.stdout.isatty():
        print()
    show(
        kind=Kind.WARN,
        text=paint(
            code=ANSIColor.RED,
            text=f"Short {count} missed: the Dot started normally. Unplug, short,"
            " and plug it in again.",
        ),
    )
    status(text="Waiting for the bootrom.")


def short_hint() -> str:
    return ", most likely because the short was still on" if SESSION.short else ""


def stages() -> dict[State, Stage]:
    downgrades = frozenset({
        State.AMONET_V2_0_0_TWRP,
        State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
        State.AMONET_V1_1_0_FASTBOOT,
        State.AMONET_V2_0_0_FASTBOOT,
    })
    table = {
        State.EMOS: Stage(run=emos_stage, steps=1, then=None),
        State.STOCK_FIREOS5_FASTBOOT: Stage(
            run=fastbrick, steps=2, then=State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE
        ),
        State.STOCK_FASTBOOT: Stage(
            run=fastbrick, steps=2, then=State.AMONET_V2_0_0_TWRP
        ),
        State.AMONET_V1_1_0_FASTBOOT: Stage(
            run=amonet_v1_1_0_recovery, steps=1, then=State.AMONET_V1_1_0_BBOE_TWRP
        ),
    }
    to_twrp = "waiting for recovery"
    install = functools.partial(
        recovery.carry_out,
        after=functools.partial(reboot, label="waiting for v2.0.0 recovery to start"),
        guard=amonet_chain,
        unlock=amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0,
        zero=("misc",),
    )
    if ARGUMENTS.target.unlock is None:
        return (
            table
            | {
                twrp: Stage(
                    passes=TWRPS,
                    run=restore_stage,
                    steps=STOCK_STEPS,
                    then=State.STOCK_BOOTED,
                )
                for twrp in TWRPS
            }
            | {
                State.BOOTED: Stage(
                    run=lambda: reboot(label=to_twrp), steps=1, then=None
                ),
                State.ROOTED: Stage(
                    run=lambda: reboot(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_TWRP,
                ),
                State.ROOTED_AMONET_V1_1_0_BBOE: Stage(
                    run=lambda: reboot(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_BBOE_TWRP,
                ),
                State.ROOTED_AMONET_V1_1_0: Stage(
                    run=lambda: reboot(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_TWRP,
                ),
                State.AMONET_V2_0_0_BOOTED: Stage(
                    run=lambda: reboot(label="waiting for v2.0.0 recovery to start"),
                    steps=1,
                    then=State.AMONET_V2_0_0_TWRP,
                ),
            }
        )
    if isinstance(ARGUMENTS.target.installs, FireOs6):
        return table | {
            State.AMONET_V1_1_0_TWRP: Stage(
                run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
            ),
            State.AMONET_V2_0_0_TWRP: Stage(
                run=install_fireos6, steps=5, then=State.AMONET_V2_0_0_BOOTED
            ),
            State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(
                run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
            ),
            State.AMONET_V1_1_0_BBOE_TWRP: Stage(
                run=install, steps=12, then=State.AMONET_V2_0_0_TWRP
            ),
            State.ROOTED: Stage(
                run=lambda: reboot(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_TWRP,
            ),
            State.ROOTED_AMONET_V1_1_0_BBOE: Stage(
                run=lambda: reboot(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_BBOE_TWRP,
            ),
            State.ROOTED_AMONET_V1_1_0: Stage(
                run=lambda: reboot(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_TWRP,
            ),
        }
    goal = ARGUMENTS.target.goal
    chain = functools.partial(
        recovery.carry_out,
        after=functools.partial(
            reboot,
            estimate="4 min",
            into="",
            label="waiting for rooted Fire OS 5 to boot",
        ),
        before_preloader=functools.partial(install_fireos, reboot=False, slot="_a"),
        guard=amonet_chain,
        unlock=ARGUMENTS.target.unlock,
    )
    return (
        table
        | {
            State.AMONET_V1_1_0_TWRP: Stage(
                run=replace_twrp, steps=1, then=State.AMONET_V1_1_0_BBOE_TWRP
            ),
            State.AMONET_V2_0_0_TWRP: Stage(
                run=chain,
                steps=3,
                then=State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
            ),
            State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(
                run=chain, steps=17, then=goal
            ),
            State.AMONET_V1_1_0_BBOE_TWRP: Stage(
                run=install_fireos, steps=5, then=State.ROOTED_AMONET_V1_1_0_BBOE
            ),
            State.AMONET_V2_0_0_BOOTED: Stage(
                run=lambda: reboot(label="waiting for v2.0.0 recovery to start"),
                steps=1,
                then=State.AMONET_V2_0_0_TWRP,
            ),
            State.AMONET_V2_0_0_FASTBOOT: Stage(
                passes=downgrades,
                run=downgrade,
                steps=2,
                then=State.AMONET_V1_1_0_BBOE_TWRP,
            ),
        }
        | {
            rooted: Stage(run=swap_twrp, steps=1, then=goal)
            for rooted in ROOTED - {goal}
        }
    )


def state() -> State:
    SESSION.probing = True
    try:
        current = probe()
    except subprocess.TimeoutExpired:
        current = State.STARTING
    finally:
        SESSION.probing = False
    return current


def swap_twrp() -> None:
    image, label = (
        unpack(download=AMONET_BISCUIT_V1_1_0_ZIP) / "bin" / "twrp.img",
        "TWRP 3.2.3",
    )
    if ARGUMENTS.target.goal == State.ROOTED_AMONET_V1_1_0_BBOE:
        image, label = fetch(download=TWRP), f"TWRP {TWRP_VERSION}"
    PROGRESS.begin(estimate="10 s", label=f"writing {label} to recovery")
    remote = "/data/local/tmp/recovery.img"
    run(arguments=["adb", "push", image, remote], check=True, timeout=120)
    write = Shell.WRITE.value.format(source=remote, target=f"{BY_NAME}/recovery")
    adb_shell(command="su -c " + shlex.quote(s=f"{write}; rm -f {remote}"), timeout=120)
    size = image.stat().st_size
    if hashlib.md5(
        read_recovery(size=size), usedforsecurity=False
    ).hexdigest() != digest(kind="md5", path=image):
        _die(
            message=f"{label} did not verify in recovery. Leave the Dot running. "
            + again()
        )


def system_chunks(
    *, name: str, new_data: IO[bytes], ranges: list[tuple[int, int]]
) -> Iterator[bytes]:
    position = 0
    for start, end in ranges:
        for offset in range(position * 4096, start * 4096, 1 << 20):
            yield bytes(min(1 << 20, start * 4096 - offset))
        for offset in range(start * 4096, end * 4096, 1 << 20):
            length = min(1 << 20, end * 4096 - offset)
            chunk = new_data.read(length)
            if len(chunk) != length:
                _die(message=f"{name}'s system.new.dat is short")
            yield chunk
        position = end


def system_image(*, package: Download) -> tuple[list[pathlib.Path], str, int]:
    target = CACHE / f"system-{package.sha256[:12]}"
    with hold(lock=SESSION.system_lock):
        if not system_sliced(directory=target):
            shutil.rmtree(ignore_errors=True, path=target)
            build_system(package=package, target=target)
    want, blocks, slices = (target / "md5").read_text().split()
    return (
        [slice_path(directory=target, index=index) for index in range(int(slices))],
        want,
        int(blocks),
    )


def unwritten() -> str:
    return "Only boot0 was erased." if ERASED.exists() else "Nothing was written."


def write_test() -> None:
    def line(label: str, value: object) -> None:
        show(text=labelled(label=label, value=value))

    def asked(*, command: str, timeout: float = 60) -> str:
        try:
            return masked(text=adb_shell(command=command, timeout=timeout))
        except subprocess.TimeoutExpired:
            return "<timed out>"

    show(text=SUPPORT + "\n")
    line("state", probed())
    if not into_recovery(line=line):
        show(text="\nThe test needs a recovery, so it stops here.")
        return
    toybox = asked(command="toybox dd --help >/dev/null 2>&1 && echo yes")
    if toybox.split(sep="\n")[-1] == "yes":
        SESSION.dd = "toybox dd"
    line("dd on the Dot", SESSION.dd)
    listing = whole(
        marker=LISTING_OK, said=asked(command=f"ls -l {BY_NAME}/; echo {LISTING_OK}")
    )
    partitions = whole(
        marker=PARTITIONS_OK,
        said=asked(command=f"cat /proc/partitions; echo {PARTITIONS_OK}"),
    )
    try:
        chunk = usb_leg(asked=asked, line=line)
        if listing is None or partitions is None:
            line(
                "over the eMMC",
                "skipped: the Dot's partition lists did not arrive whole",
            )
        else:
            node = node_names(listing=listing).get(EMMC_TARGET, "")
            sizes = node_sizes(partitions=partitions)
            emmc_leg(
                asked=asked,
                blocks=sizes.get(node_held(target=node), 0) // MEBIBYTE,
                chunk=chunk,
                line=line,
                node=node,
            )
    finally:
        asked(command=f"rm -f {USB_TEST}")
    show(text="\nwhat the kernel says about the eMMC")
    for text in mmc_said(asked=asked):
        show(text=text)
    show(text="\n" + LEFT_IN_RECOVERY)


if __name__ == "__main__":
    main()
