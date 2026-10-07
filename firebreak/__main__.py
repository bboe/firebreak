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
import gzip
import hashlib
import http.client
import os
import pathlib
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
from typing import IO, TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

from firebreak.android.bootimg import boot_image, cpio, magisk_db, magisk_files
from firebreak.android.gpt import Partition, gpt_intact, stock_gpt
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
    unpack,
)
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
from firebreak.mediatek.bootrom import child_bootrom, child_reset
from firebreak.ui import (
    ARGUMENTS,
    MINUTE,
    PROGRESS,
    SESSION,
    ANSIColor,
    Kind,
    _die,
    again,
    clock,
    paint,
    passed,
    say,
    show,
    status,
    warn,
)

AMONET_BISCUIT_V1_1_0 = "amonet-biscuit-v1.1.0"
AMONET_BISCUIT_V1_1_0_BBOE = AMONET_BISCUIT_V1_1_0 + "-bboe"
AMONET_BISCUIT_V2_0_0 = "amonet-biscuit-v2.0.0"
AMONET_V1_1_0_ALIGN = 0x400
AMONET_V1_1_0_APPEND = 0x6E000
AMONET_V1_1_0_BOOT_BLOCKS = 0x37000
AMONET_V1_1_0_PAYLOAD_SEEK = 223207
AMONET_V2_0_0_FIREOS_BUILD = "8146"
BOOTLOADER_CONTROL_BLOCK = b"\0ABB\x01\x8f\0"
BOOTLOADER_CONTROL_BLOCK_OFFSET = 0x360
BOOT_ROOT = Download(
    browser=True,
    name="boot-root.zip",
    sha256="de49cc88b27a8e77cf97cf0156bee50e4ddc0e116c41aaede06b494e38397be0",
    size=473633,
    url="https://xdaforums.com/attachments/boot-root-zip.6388001/",
)
BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
CHAIN_PARTS = (
    "boot_a",
    "boot_b",
    "lk_a",
    "lk_b",
    "misc",
    "recovery",
    "tee1",
    "tee2",
)
CHAIN_TEE = ("tee2", "tee1")
DISK = "/dev/block/mmcblk0"
EMOS_DEVICE_ID = (0x1949, 0x2007)
FASTBOOT_MODE = (
    "Unplug the USB cable, press and hold the action button (the one with a dot),"
    " plug the cable back in, and let go when the light ring turns green."
)
FIREOS = Download(
    name="update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
    sha256="6ababc517529938f0d1e836c3410a91df19683ae62d7fca9e2ca57320d5d2faa",
    url="https://d1s31zyz7dcc2d.cloudfront.net/47a1457e0802980eb32f63cd3ce355c0/"
    "update-kindle-csm_biscuit-272.6.8.0_user_680767620.bin",
)
FTVDB = "https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/"
HEAD_CHECK = 1 << 20
LITTLE_KERNEL_DESCRIPTION = re.compile(pattern=r"[0-9a-f]{7}-\d{8}_\d{6}")
MD5_DIGITS = 32
MIRROR = "https://github.com/hkfuertes/amazon_device_biscuit/releases/download/none"
AMONET_BISCUIT_V1_1_0_ZIP = Download(
    folder="v1",
    name="amonet-biscuit-v1.1.0.zip",
    sha256="bd4d3a18b6b6e9ff6e49a4739159a81020673202795cb3959f7c9ff24351b663",
    url=MIRROR + "/amonet-biscuit-v1.1.0.zip",
)
AMONET_BISCUIT_V2_0_0_ZIP = Download(
    folder="v2",
    name="amonet-biscuit-v2.0.0.zip",
    sha256="98297293701082bc7272efe077f941c56fc7b6e1f27ef6f2e93b6e4c6fc7b62d",
    url=MIRROR + "/amonet-biscuit-v2.0.0.zip",
)
SHORT_WAIT = 5
STOCK_STEPS = 16
TABLE_FIELDS = 6
TWRP_VERSION = "3.7.0_9-bboe2"
TWRP = Download(
    name=f"twrp-{TWRP_VERSION}-biscuit.img",
    sha256="f59052713a6580a1477490b2f9cad80e9b31d22408861b18fd442129a71f2ad9",
    url="https://github.com/bboe/twrp_device_amazon_echo-mt8163/releases/download/"
    f"v{TWRP_VERSION}/twrp-v{TWRP_VERSION}-biscuit.img",
)
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
    CLEAR_BOOT0 = (
        "d=dd; toybox dd --help >/dev/null 2>&1 && d='toybox dd'; "
        "echo 0 > /sys/block/mmcblk0boot0/force_ro; "
        "$d if=/dev/zero of=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null; "
        "echo 1 > /sys/block/mmcblk0boot0/force_ro; sync; "
        "echo 3 > /proc/sys/vm/drop_caches; "
        'echo "$($d if=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null | wc -c)'
        " $($d if=/dev/block/mmcblk0boot0 bs=4096 count=1 2>/dev/null"
        " | tr -d '\\0' | wc -c)\""
    )
    DATA = f"""\
set -e
umount /sdcard /data 2>/dev/null || true
d={BY_NAME}/userdata
mke2fs -q -t ext4 -b 4096 "$d" $(( $(blockdev --getsize64 "$d") / 4096 - 256 ))
mount -t ext4 "$d" /data
mountpoint -q /data
"""
    FLUSH = "sync && echo 3 > /proc/sys/vm/drop_caches && echo flushed"
    MAGISK = """\
set -e
mountpoint -q /data
cd /; cpio -idu < /tmp/magisk.cpio 2>/dev/null
chmod 700 /data/adb; chmod -R 755 /data/adb/magisk; chmod 600 /data/adb/magisk.db
sync
"""
    NODES = (
        "b=; for p in {pairs}; do n=${{p%:*}}; s=${{p#*:}};"
        ' g=$([ -b "$n" ] && blockdev --getsize64 "$n" || echo no);'
        ' [ "$g" = "$s" ] || b="$b $n=$g"; done; echo "$b nodes-ok"'
    )
    SEEK_WRITE = (
        "dd if={source} of={target} bs=512 seek={seek} 2>/dev/null;"
        " sync; echo 3 > /proc/sys/vm/drop_caches"
    )
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
    UNMOUNT = (
        'for m in $(grep "^/dev/block" /proc/mounts | cut -d" " -f2); do umount "$m";'
        ' done; echo "left:$(grep "^/dev/block" /proc/mounts | cut -d" " -f2'
        ' | tr "\\n" " ")"'
    )
    WRITE = (
        "dd if={source} of={target} bs=1048576 2>/dev/null;"
        " sync; echo 3 > /proc/sys/vm/drop_caches"
    )


@dataclasses.dataclass(frozen=True)
class Stage:
    run: Callable[[], None]
    steps: int
    then: State | None
    passes: frozenset[State] = frozenset()


class State(enum.Enum):
    AMONET_V1_1_0_BBOE_TWRP = "amonet-v1.1.0-bboe-twrp"
    AMONET_V1_1_0_FASTBOOT = "amonet-v1.1.0-fastboot"
    AMONET_V1_1_0_TWRP = "amonet-v1.1.0-twrp"
    AMONET_V2_0_0_BOOTED = "amonet-v2.0.0-booted"
    AMONET_V2_0_0_FASTBOOT = "amonet-v2.0.0-fastboot"
    AMONET_V2_0_0_TWRP = "amonet-v2.0.0-twrp"
    AMONET_V2_0_0_TWRP_V1_1_0_TABLE = "amonet-v2.0.0-twrp-v1.1.0-table"
    BOOTED = "booted"
    EMOS = "emos"
    NONE = "none"
    ROOTED = "rooted"
    ROOTED_AMONET_V1_1_0 = "rooted-amonet-v1.1.0"
    ROOTED_AMONET_V1_1_0_BBOE = "rooted-amonet-v1.1.0-bboe"
    STARTING = "starting"
    STOCK_BOOTED = "stock-booted"
    STOCK_FASTBOOT = "stock-fastboot"
    STOCK_FIREOS5_FASTBOOT = "stock-fireos5-fastboot"


GOALS = {
    "stock": State.STOCK_BOOTED,
    AMONET_BISCUIT_V1_1_0: State.ROOTED_AMONET_V1_1_0,
    AMONET_BISCUIT_V1_1_0_BBOE: State.ROOTED_AMONET_V1_1_0_BBOE,
    AMONET_BISCUIT_V2_0_0: State.AMONET_V2_0_0_BOOTED,
}
ROOTED = {State.ROOTED, State.ROOTED_AMONET_V1_1_0_BBOE, State.ROOTED_AMONET_V1_1_0}
TWRPS = frozenset({
    State.AMONET_V1_1_0_TWRP,
    State.AMONET_V2_0_0_TWRP,
    State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    State.AMONET_V1_1_0_BBOE_TWRP,
})


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
    if "lk_a" not in part:
        _die(message="the Dot's partition table has no lk_a. " + again())
    node = f"{DISK}p{part['lk_a'][0]}"
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
                return
            if len(held) == MD5_DIGITS:
                break
            if attempt + 1 < PUSH_TRIES:
                reconnect(remote=DISK)
        if len(held) != MD5_DIGITS:
            _die(
                message=f"{node} did not answer with an md5 of its first"
                f" {local.stat().st_size} bytes: {held or 'nothing'}. Nothing"
                " was written. " + again()
            )
    _die(
        message="lk_a holds neither amonet v2.0.0's nor v1.1.0's LK, so this Dot"
        " is locked and the recovery it started is one amonet left behind."
        " Nothing was written. Unlock it first: unplug the USB cable, hold the"
        " action button, plug it back in, and let go when the ring turns green. "
        + again()
    )


def amonet_v1_1_0_append() -> None:
    amonet_chain()
    part = partitions()
    if "boot_a_x" in part:
        reboot_recovery(label="waiting for v2.0.0 recovery to start")
        return
    number, start, end = part["userdata"]
    if number != max(held[0] for held in part.values()):
        _die(message="userdata is not the last partition. " + again())
    shrunk = (
        ((end // AMONET_V1_1_0_ALIGN) * AMONET_V1_1_0_ALIGN) - AMONET_V1_1_0_APPEND - 1
    )
    first, second = shrunk + 1, shrunk + 1 + AMONET_V1_1_0_BOOT_BLOCKS
    if shrunk <= start:
        _die(message="userdata cannot give up room for amonet v1.1.0's boot images")
    code = partition_field(name="Partition GUID code", number=number)
    unique_identifier = partition_field(name="Partition unique GUID", number=number)
    boot_a_number, boot_b_number = number + 1, number + 2
    PROGRESS.begin(estimate="5 s", label="making room for amonet v1.1.0")
    adb_shell(
        command=f"sgdisk --set-alignment=1 --delete={number}"
        f" --new={number}:{start}:{shrunk} --typecode={number}:{code}"
        f" --partition-guid={number}:{unique_identifier}"
        f" --change-name={number}:userdata"
        f" --new={boot_a_number}:{first}:{first + AMONET_V1_1_0_BOOT_BLOCKS - 1}"
        f" --typecode={boot_a_number}:{code}"
        f" --new={boot_b_number}:{second}:{second + AMONET_V1_1_0_BOOT_BLOCKS - 1}"
        f" --typecode={boot_b_number}:{code}"
        f" --change-name={part['boot_a'][0]}:boot_a_x"
        f" --change-name={part['boot_b'][0]}:boot_b_x"
        f" --change-name={boot_a_number}:boot_a"
        f" --change-name={boot_b_number}:boot_b {DISK}",
        timeout=60,
    )
    left = partitions()
    for name, want in (
        ("userdata", (number, start, shrunk)),
        ("boot_a", (boot_a_number, first, first + AMONET_V1_1_0_BOOT_BLOCKS - 1)),
        ("boot_b", (boot_b_number, second, second + AMONET_V1_1_0_BOOT_BLOCKS - 1)),
    ):
        if left.get(name) != want:
            _die(
                message=f"sgdisk left {name} as {left.get(name)}, not {want}. "
                + again()
            )
    for name in ("boot_a_x", "boot_b_x"):
        if name not in left:
            _die(message=f"sgdisk did not leave a {name}. " + again())
    for field, holds in (
        ("Partition GUID code", code),
        ("Partition unique GUID", unique_identifier),
    ):
        if partition_field(name=field, number=number) != holds:
            _die(message=f"sgdisk left userdata a different {field}. " + again())
    reboot_recovery(label="waiting for v2.0.0 recovery to start")


def amonet_v1_1_0_chain() -> None:
    amonet_chain()
    amonet = unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    twrp = amonet / "bin" / "twrp.img"
    if ARGUMENTS.target == AMONET_BISCUIT_V1_1_0_BBOE:
        twrp = fetch(download=TWRP)
    node, part = chain_nodes()
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        work = pathlib.Path(temporary)
        PROGRESS.begin(estimate="5 s", label="clear the preloader header (boot0)")
        ERASED.touch()
        answer = adb_shell(command=Shell.CLEAR_BOOT0.value).split(sep="\n")[-1].split()
        if answer != ["4096", "0"]:
            read, *still_set = answer or [""]
            if read == "4096" and still_set:
                ERASED.unlink(missing_ok=True)
            _die(message="boot0's header did not read back as cleared. " + again())
        PROGRESS.begin(estimate="20 s", label="writing amonet v1.1.0's bootchain")
        for name, source, seek in (
            ("boot_a", "boot.hdr", 0),
            ("boot_a", "boot.payload", AMONET_V1_1_0_PAYLOAD_SEEK),
            ("boot_b", "boot.hdr", 0),
            ("boot_b", "boot.payload", AMONET_V1_1_0_PAYLOAD_SEEK),
            ("tee1", "tz.img", 0),
            ("tee2", "tz.img", 0),
            ("lk_a", "lk.bin", 0),
            ("lk_b", "lk.bin", 0),
        ):
            write_checked(
                local=amonet / "bin" / source,
                node=node[name],
                seek=seek,
                work=work,
            )
        write_checked(local=twrp, node=node["recovery"], seek=0, work=work)
        PROGRESS.begin(estimate="5 s", label="write misc, slot a marked good")
        if adb_shell(command=Shell.FLUSH.value).split(sep="\n")[-1] != "flushed":
            _die(message="the Dot did not flush its caches. " + again())
        block = bytearray(read_sectors(count=1, start=part["misc"][1] + 1))
        block[
            BOOTLOADER_CONTROL_BLOCK_OFFSET - 512 : BOOTLOADER_CONTROL_BLOCK_OFFSET
            - 512
            + len(BOOTLOADER_CONTROL_BLOCK)
        ] = BOOTLOADER_CONTROL_BLOCK
        staged = work / "misc.block"
        staged.write_bytes(data=bytes(block))
        write_checked(local=staged, node=node["misc"], seek=1, work=work)
        install_fireos(reboot=False, slot="_a")
        write_preloader(image=amonet / "bin" / "preloader.img")
        ERASED.unlink(missing_ok=True)
    run(arguments=["adb", "reboot"], check=True, timeout=60)
    PROGRESS.begin(estimate="4 min", label="waiting for rooted Fire OS 5 to boot")


def amonet_v1_1_0_recovery() -> None:
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


def amonet_v2_0_0_payload() -> pathlib.Path:
    amonet = unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    return amonet / "brom-payload" / "build" / "payload.bin"


def bootrom(  # ruff: ignore[complex-structure, too-many-branches, too-many-statements]
    *,
    amonet: pathlib.Path,
    erase: Callable[[], str] | None,
    payload: pathlib.Path,
    wheel: pathlib.Path | None,
) -> bool:
    shutil.copyfile(dst=amonet / "brom-payload" / "build" / "payload.bin", src=payload)
    log_path = CACHE / "bootrom.log"
    environment = dict(
        os.environ, PYTHONPATH=child_path(wheel=wheel), PYTHONUNBUFFERED="1"
    )
    if SESSION.short:
        environment["FIREBREAK_ERASED"] = str(ERASED)
    if not erase and not SESSION.short:
        environment["FIREBREAK_RESUME"] = "1"
        with contextlib.suppress(subprocess.TimeoutExpired):
            subprocess.run(
                args=child(name="reset"),
                check=False,
                cwd=CACHE,
                env=environment,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                timeout=30,
            )
    with log_path.open(mode="w") as log:
        if ARGUMENTS.verbose:
            show(
                text=f"{clock()} $ "
                + shlex.join(split_command=child(name="bootrom"))
                + " (amonet v1.1.0 bootrom step, 64 blocks per write)"
            )
        bootrom_process = subprocess.Popen(
            args=child(name="bootrom"),
            cwd=amonet / "modules",
            env=environment,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            stdout=log,
        )
        if not SESSION.short:
            bootrom_process.stdin.write(b"\n" * 5)
            bootrom_process.stdin.close()
        started = time.monotonic()
        while time.monotonic() - started < (30 if SESSION.short else 3):
            if bootrom_process.poll() is not None or (
                SESSION.short
                and "Waiting for bootrom" in log_path.read_text(errors="replace")
            ):
                break
            time.sleep(0.25)
        if bootrom_process.poll() is not None:
            _die(message=f"v1.1.0's bootrom step did not start; see {log_path}")
        if erase:
            ERASED.touch()
            try:
                failure = erase()
            except subprocess.TimeoutExpired:
                bootrom_process.kill()
                raise
            if failure:
                bootrom_process.kill()
                _die(message=failure)
        elif SESSION.short:
            say(
                code=ANSIColor.YELLOW,
                text="Short the Dot's test point and plug it in. The run waits for"
                " its bootrom, then says when the short may come off.",
            )
            status(text="Waiting for the bootrom.")
        else:
            PROGRESS.begin(estimate="40 s", label="waiting for the Dot to restart")
        deadline = time.monotonic() + (60 if erase else 600)
        missed = unopened = 0
        while bootrom_process.poll() is None and time.monotonic() < deadline:
            text = log_path.read_text(errors="replace")
            if "Found port" in text:
                break
            if not erase and not SESSION.short and "Ignoring the preloader" in text:
                bootrom_process.kill()
                ERASED.unlink(missing_ok=True)
                PROGRESS.note(
                    message="The Dot started its preloader, so boot0 is intact and it"
                    " needs no bootrom step."
                )
                return False
            if SESSION.short and text.count("Ignoring the preloader") > missed:
                missed = text.count("Ignoring the preloader")
                if sys.stdout.isatty():
                    print()
                said = (
                    f"Short {missed} missed: the Dot started normally. Unplug, short,"
                    " and plug it in again."
                )
                show(kind=Kind.WARN, text=paint(code=ANSIColor.RED, text=said))
                status(text="Waiting for the bootrom.")
            if text.count("Cannot open") > unopened:
                unopened = text.count("Cannot open")
                if SESSION.short and sys.stdout.isatty():
                    print()
                said = "Cannot open" + text.split(sep="Cannot open")[-1].splitlines()[0]
                said += ". The run keeps trying."
                if SESSION.short:
                    warn(text=said)
                    status(text="Waiting for the bootrom.")
                else:
                    PROGRESS.note(message=said)
            time.sleep(1)
        else:
            if bootrom_process.poll() is None:
                bootrom_process.kill()
                _die(
                    message="the Dot's bootrom did not show up as a serial port.\n"
                    + no_port_help()
                )
        if SESSION.short and bootrom_process.poll() is None:
            countdown()
            with contextlib.suppress(OSError):
                bootrom_process.stdin.write(b"\n" * 5)
                bootrom_process.stdin.close()
        if not erase:
            PROGRESS.begin(estimate="30 s", label="writing amonet v1.1.0's bootloader")
        deadline = time.monotonic() + 1800
        unanswered = 0
        while bootrom_process.poll() is None:
            if time.monotonic() > deadline:
                bootrom_process.kill()
                _die(message=f"v1.1.0's bootrom step did not finish; see {log_path}")
            text = log_path.read_text(errors="replace")
            if text.count("did not answer the handshake") > unanswered:
                unanswered = text.count("did not answer the handshake")
                if SESSION.short:
                    bootrom_process.kill()
                    _die(
                        message="the Dot's bootrom did not answer. Nothing was"
                        " written. Unplug the Dot. " + again()
                    )
                PROGRESS.note(
                    message="The Dot's bootrom did not answer. Unplug the Dot and"
                    " plug it back in; the run goes on when its bootrom returns."
                )
            if text.count("Cannot open") > unopened:
                unopened = text.count("Cannot open")
                said = "Cannot open" + text.split(sep="Cannot open")[-1].splitlines()[0]
                PROGRESS.note(message=said + ". The run keeps trying.")
            time.sleep(1)
    if bootrom_process.returncode != 0:
        said = log_path.read_text(errors="replace")
        if SESSION.short and (
            "The eMMC did not answer" in said or "expected pattern" in said
        ):
            _die(
                message="the Dot's eMMC did not answer, most likely because the"
                " short was still on. Nothing was written. Unplug the Dot. " + again()
            )
        _die(message=f"v1.1.0's bootrom step failed; see {log_path}")
    if "Reboot to unlocked fastboot" not in log_path.read_text(errors="replace"):
        _die(message=f"v1.1.0's bootrom step did not finish; see {log_path}")
    ERASED.unlink(missing_ok=True)
    for _ in range(30):
        try:
            if in_fastboot() and getvar(name="lk_build_desc") == LK.FIREOS5.value:
                break
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    else:
        _die(message="the Dot did not come back in v1.1.0's fastboot")
    return True


def build_system(*, target: pathlib.Path) -> None:
    part = CACHE / "system.part"
    shutil.rmtree(ignore_errors=True, path=part)
    part.mkdir()
    checksum = hashlib.md5(usedforsecurity=False)
    fireos = fetch(download=FIREOS)
    with zipfile.ZipFile(file=fireos) as archive:
        words = archive.read(name="system.transfer.list").decode().split()
        commands = dict(zip(words[4::2], words[5::2]))
        if words[0] != "3" or set(commands) != {"erase", "new"}:
            _die(message=f"{FIREOS.name} has a transfer list this does not read")
        blocks = int(commands["erase"].split(sep=",")[-1])
        bounds = [int(number) for number in commands["new"].split(sep=",")[1:]]
        ranges = [*zip(bounds[::2], bounds[1::2]), (blocks, blocks)]
        image = part / "system.img.gz"
        with archive.open(name="system.new.dat") as new_data:  # ruff: ignore[multiple-with-statements]
            with gzip.open(compresslevel=6, filename=image, mode="wb") as compressed:
                for chunk in system_chunks(new_data=new_data, ranges=ranges):
                    checksum.update(chunk)
                    compressed.write(chunk)
    (part / "md5").write_text(data=f"{checksum.hexdigest()} {blocks}\n")
    for path in part.iterdir():
        with path.open(mode="rb+") as file:
            os.fsync(fd=file.fileno())
    part.replace(target=target)


def chain_nodes() -> tuple[dict[str, str], dict[str, tuple[int, int, int]]]:
    part = partitions()
    for name in (*CHAIN_PARTS, "boot_a_x", "boot_b_x"):
        if name not in part:
            _die(
                message=f"the Dot's partition table has no {name}. Rebuild it"
                f" with firebreak stock {AMONET_V2_0_0_FIREOS_BUILD}, then"
                " root again."
            )
    for name in ("boot_a", "boot_b"):
        held = part[name][2] - part[name][1] + 1
        if held != AMONET_V1_1_0_BOOT_BLOCKS:
            _die(message=f"{name} holds {held} blocks, not {AMONET_V1_1_0_BOOT_BLOCKS}")
    node = {name: f"{DISK}p{part[name][0]}" for name in CHAIN_PARTS}
    wrong = check_nodes(
        want={node[name]: (part[name][2] - part[name][1] + 1) * 512 for name in node}
    )
    if wrong:
        run(arguments=["adb", "reboot", "recovery"], check=False, timeout=60)
        _die(
            message="the kernel does not hold the table that is on the disk:"
            f" {wrong}. A write by that name could land in RAM and verify"
            " against itself, so the Dot is restarting into recovery. " + again()
        )
    if (
        adb_shell(command="[ -b /dev/block/mmcblk0boot0 ] && echo block").split(
            sep="\n"
        )[-1]
        != "block"
    ):
        _die(
            message="/dev/block/mmcblk0boot0 is not a block device, so the"
            " preloader would be written to a file in RAM. " + again()
        )
    return node, part


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


def check_nodes(*, want: dict[str, int]) -> str:
    command = Shell.NODES.value.format(
        pairs=" ".join(f"{node}:{size}" for node, size in want.items())
    )
    for attempt in range(PUSH_TRIES):
        said = adb_shell(command=command, timeout=60).split(sep="\n")[-1]
        if said.endswith("nodes-ok"):
            read = [token.partition("=") for token in said[: -len("nodes-ok")].split()]
            if all(node in want for node, _, _ in read):
                return ", ".join(
                    f"{node} reads {got}, not {want[node]} bytes"
                    for node, _, got in read
                )
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(
        message="the Dot did not answer which of its partitions are block"
        f" devices: {said!r}. " + again()
    )
    return ""


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
    if name == "emos":
        return child_emos(action=arguments[0], want=arguments[1])
    return {"bootrom": child_bootrom, "reset": child_reset}[name]()


def clear_boot0() -> None:
    answer = adb_shell(command=Shell.CLEAR_BOOT0.value).split(sep="\n")[-1].split()
    if answer == ["4096", "0"]:
        return
    read, *still_set = answer or [""]
    if read == "4096" and still_set:
        ERASED.unlink(missing_ok=True)
        restore_failed(
            bootable=True,
            message="boot0's header did not clear, so a failure from here would brick"
            " rather than fall into the bootrom; nothing else was written",
        )
    restore_failed(
        message="boot0 did not read back, so whether its header cleared is unknown;"
        " nothing else was written"
    )


def cli() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""targets:
  {AMONET_BISCUIT_V1_1_0_BBOE}, the default
      rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP {TWRP_VERSION}.
  {AMONET_BISCUIT_V1_1_0}
      the same, with amonet v1.1.0's own TWRP 3.2.3.
  {AMONET_BISCUIT_V2_0_0}
      amonet v2.0.0's own procedure: Fire OS 6 {AMONET_V2_0_0_FIREOS_BUILD}
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
        "--short",
        action="store_true",
        help="for a Dot that shows no light and needs its test point shorted:"
        " wait for its bootrom, say when the short may come off, then go on",
    )
    parser.add_argument(
        "target",
        choices=tuple(GOALS),
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
    if (options.target == "stock") != (options.build is not None):
        parser.error(
            message="stock takes a BUILD, and no other target does: "
            + ", ".join(sorted(BUILDS))
        )
    ARGUMENTS.build = options.build or ""
    ARGUMENTS.target = options.target
    ARGUMENTS.verbose = options.verbose
    for tool in ("adb", "fastboot"):
        if not shutil.which(cmd=tool):
            _die(message=tool + " not found: install Android platform-tools")
    check_user()
    check_adb()
    move_old_caches()
    SESSION.short = options.short
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


def downgrade() -> None:
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
    PROGRESS.begin(estimate="45 s", label="writing amonet v1.1.0's bootloader")
    bootrom(
        amonet=amonet,
        erase=erase_by_fastboot,
        payload=amonet_v2_0_0_payload(),
        wheel=wheel,
    )
    amonet_v1_1_0_recovery()


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
    for arguments in (["fastboot", "erase", "boot0"], ["fastboot", "reboot"]):
        result = run(arguments=arguments, timeout=60)
        if result.returncode != 0:
            return f"{' '.join(arguments)} failed:\n{result.stdout}"
    return ""


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


def install_amonet_v2_0_0() -> None:
    zip_path = preloader_last()
    PROGRESS.begin(estimate="40 s", label="installing amonet v2.0.0")
    remote = DOT_TEMPORARY_DIRECTORY / AMONET_BISCUIT_V2_0_0_ZIP.name
    push_checked(local=zip_path, remote=remote)
    ERASED.touch()
    answer = adb_shell(command=Shell.CLEAR_BOOT0.value, timeout=60).split()
    if answer[-2:] != ["4096", "0"]:
        if answer[-2:-1] == ["4096"]:
            ERASED.unlink(missing_ok=True)
        _die(
            message="boot0's header did not read back as cleared, so amonet"
            " v2.0.0's zip was not installed. " + again()
        )
    output = ""
    with contextlib.suppress(subprocess.TimeoutExpired):
        output = adb_shell(command=f"twrp install {remote}", timeout=120)
    if "- Done" in output:
        ERASED.unlink(missing_ok=True)
    errors = [line for line in output.split(sep="\n") if "(!)" in line]
    if errors:
        _die(message="amonet v2.0.0's zip failed: " + errors[0])
    PROGRESS.begin(estimate="40 s", label="waiting for v2.0.0 recovery to start")


def install_fireos(*, reboot: bool = True, slot: str = "") -> None:
    fireos = fetch(download=FIREOS)
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
        write_system(system=system)
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
    update_file = download(build=AMONET_V2_0_0_FIREOS_BUILD)
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
            label=f"installing Fire OS 6 {AMONET_V2_0_0_FIREOS_BUILD}, {slot} slot",
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
                message=f"installing Fire OS 6 {AMONET_V2_0_0_FIREOS_BUILD} left the"
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


def partition_field(*, name: str, number: int) -> str:
    command = f"sgdisk --info={number} {DISK}; echo field-ok"
    for attempt in range(PUSH_TRIES):
        output = adb_shell(command=command, timeout=30)
        if output.split(sep="\n")[-1] == "field-ok":
            for line in output.split(sep="\n"):
                if line.startswith(name + ":"):
                    return (
                        line.split(maxsplit=1, sep=":")[1].strip().strip("'").split()[0]
                    )
            _die(message=f"sgdisk --info={number} printed no {name}:\n{output}")
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(message=f"sgdisk --info={number} did not answer in full. " + again())
    return ""


def partition_table() -> str:
    command = f"sgdisk --print {DISK}; echo table-ok"
    for attempt in range(PUSH_TRIES):
        said = adb_shell(command=command, timeout=30).split(sep="\n")
        if said[-1] == "table-ok" and any(" userdata" in line for line in said):
            return "\n".join(said[:-1])
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(message="sgdisk did not print the Dot's partition table:\n" + "\n".join(said))
    return ""


def partitions() -> dict[str, tuple[int, int, int]]:
    found = {}
    for line in partition_table().split(sep="\n"):
        field = line.split()
        if len(field) >= TABLE_FIELDS and all(value.isdigit() for value in field[:3]):
            found[field[-1]] = (int(field[0]), int(field[1]), int(field[2]))
    if "userdata" not in found:
        _die(message="no userdata in the Dot's partition table")
    return found


def prebuild() -> None:
    with contextlib.suppress(Exception, SystemExit):
        system_image()


def predownload() -> None:
    with contextlib.suppress(Exception, SystemExit):
        prefetch()


DOWNLOADER = threading.Thread(daemon=True, target=predownload)


def prefetch() -> None:
    if DOWNLOADER.is_alive() and threading.current_thread() is threading.main_thread():
        show(text="Finishing the downloads.")
    unpack(download=AMONET_BISCUIT_V2_0_0_ZIP)
    if ARGUMENTS.target in {"stock", AMONET_BISCUIT_V2_0_0}:
        build = ARGUMENTS.build or AMONET_V2_0_0_FIREOS_BUILD
        with hold(lock=lock_for(key=build)):
            download(build=build)
        return
    unpack(download=AMONET_BISCUIT_V1_1_0_ZIP)
    pyserial_wheel()
    fetch(download=FIREOS)
    fetch(download=MAGISK)
    fetch(download=TWRP)
    threading.Thread(daemon=True, target=prebuild).start()


def preloader_last() -> pathlib.Path:
    patched = CACHE / ("preloader-last-" + AMONET_BISCUIT_V2_0_0_ZIP.name)
    source = fetch(download=AMONET_BISCUIT_V2_0_0_ZIP)
    script = "META-INF/com/google/android/update-binary"
    anchor = "set_progress 1.00\n"
    with zipfile.ZipFile(file=source) as source_archive:
        text = source_archive.read(name=script).decode()
        start = text.find('ui_print "- Updating preloader"')
        end = text.find('ui_print "- Updating lk"')
        if not 0 < start < end or text.count(anchor) != 1:
            _die(
                message=f"{AMONET_BISCUIT_V2_0_0_ZIP.name}'s installer is not the"
                " one expected"
            )
        rest = text[:start] + text[end:]
        moved = rest.replace(anchor, anchor + "\n" + text[start:end])
        part = patched.with_suffix(suffix=".part")
        with zipfile.ZipFile(file=part, mode="w") as patched_archive:
            for info in source_archive.infolist():
                data = (
                    moved.encode()
                    if info.filename == script
                    else source_archive.read(name=info)
                )
                patched_archive.writestr(data=data, zinfo_or_arcname=info)
    part.replace(target=patched)
    return patched


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


def read_sectors(*, count: int, start: int) -> bytes:
    raw = command(
        arguments=[
            "adb",
            "exec-out",
            f"{SESSION.dd} if={DISK} bs=512 skip={start} count={count} 2>/dev/null",
        ],
        standard_input=subprocess.DEVNULL,
        standard_output=subprocess.PIPE,
        timeout=60,
    ).stdout
    if len(raw) != count * 512:
        _die(
            message=f"read {len(raw)} bytes of the Dot's partition table,"
            f" not {count * 512}"
        )
    return raw


def reboot_recovery(*, label: str) -> None:
    run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)
    PROGRESS.begin(estimate="40 s", label=label)


def remaining(*, start: State, table: dict[State, Stage]) -> int | None:
    total = 0
    for _ in range(len(table) + 1):
        if start == GOALS[ARGUMENTS.target]:
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


def restore_failed(*, bootable: bool = False, message: str) -> NoReturn:
    if not bootable and ERASED.exists():
        message = message.rstrip(".") + (
            ". boot0 has no preloader until the last step, so the Dot will not"
            " start at all until this run finishes"
        )
    _die(message=message)


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
    guided = False
    resumed = False
    seen = None
    shown = None
    deadline = None
    while True:
        current = state()
        installed = (
            ARGUMENTS.target == AMONET_BISCUIT_V2_0_0
            and State.AMONET_V2_0_0_TWRP in done
        )
        restored = ARGUMENTS.target == "stock" and bool(done & TWRPS)
        gesture = (
            ARGUMENTS.target in {"stock", AMONET_BISCUIT_V2_0_0}
            and current == State.AMONET_V2_0_0_FASTBOOT
        )
        if (
            DOWNLOADER.ident is None
            and current not in {State.BOOTED, State.STARTING, *ROOTED}
            and not (
                ARGUMENTS.target == "stock"
                and current in {State.STOCK_BOOTED, State.STOCK_FASTBOOT}
            )
        ):
            DOWNLOADER.start()
        if current not in {State.NONE, State.STARTING, *TWRPS}:
            ERASED.unlink(missing_ok=True)
        if current != State.NONE:
            SESSION.short = False
        if current == State.NONE and (ERASED.exists() or SESSION.short) and not resumed:
            if ARGUMENTS.target == AMONET_BISCUIT_V2_0_0:
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
            if bootrom(
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
                and ARGUMENTS.target != "stock"
            ):
                show(text="The Dot is starting Fire OS. Waiting for it to finish.")
            elif current == State.STOCK_BOOTED and installed:
                deadline = time.monotonic() + MINUTE
            elif current == State.STOCK_BOOTED and ARGUMENTS.target != "stock":
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
                and ARGUMENTS.target != AMONET_BISCUIT_V2_0_0
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
        if (
            ARGUMENTS.target == AMONET_BISCUIT_V2_0_0
            and current == State.AMONET_V2_0_0_BOOTED
        ):
            version = adb_shell(command="getprop ro.build.version.name")
            warn(text=f"The Dot is rooted: {version}, with root adb.")
            cache_note()
            return
        if ARGUMENTS.target == "stock" and current in {
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
        if current == GOALS[ARGUMENTS.target]:
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
            or (current == State.BOOTED and ARGUMENTS.target != "stock")
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
            if ARGUMENTS.target == AMONET_BISCUIT_V2_0_0:
                fetch(download=BOOT_ROOT)
            if (
                ARGUMENTS.target in {"stock", AMONET_BISCUIT_V2_0_0}
                or current not in ROOTED
            ):
                prefetch()
            warn(text="Keep the Dot plugged in until firebreak finishes.")
        done.add(current)
        stage = table.get(current)
        if stage:
            left = remaining(start=current, table=table)
            PROGRESS.steps = 0 if left is None else PROGRESS.step + left
            stage.run()
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
    if ARGUMENTS.target == "stock":
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
                    run=lambda: reboot_recovery(label=to_twrp), steps=1, then=None
                ),
                State.ROOTED: Stage(
                    run=lambda: reboot_recovery(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_TWRP,
                ),
                State.ROOTED_AMONET_V1_1_0_BBOE: Stage(
                    run=lambda: reboot_recovery(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_BBOE_TWRP,
                ),
                State.ROOTED_AMONET_V1_1_0: Stage(
                    run=lambda: reboot_recovery(label=to_twrp),
                    steps=1,
                    then=State.AMONET_V1_1_0_TWRP,
                ),
                State.AMONET_V2_0_0_BOOTED: Stage(
                    run=lambda: reboot_recovery(
                        label="waiting for v2.0.0 recovery to start"
                    ),
                    steps=1,
                    then=State.AMONET_V2_0_0_TWRP,
                ),
            }
        )
    if ARGUMENTS.target == AMONET_BISCUIT_V2_0_0:
        return table | {
            State.AMONET_V1_1_0_TWRP: Stage(
                run=install_amonet_v2_0_0, steps=2, then=State.AMONET_V2_0_0_TWRP
            ),
            State.AMONET_V2_0_0_TWRP: Stage(
                run=install_fireos6, steps=5, then=State.AMONET_V2_0_0_BOOTED
            ),
            State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(
                run=install_amonet_v2_0_0, steps=2, then=State.AMONET_V2_0_0_TWRP
            ),
            State.AMONET_V1_1_0_BBOE_TWRP: Stage(
                run=install_amonet_v2_0_0, steps=2, then=State.AMONET_V2_0_0_TWRP
            ),
            State.ROOTED: Stage(
                run=lambda: reboot_recovery(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_TWRP,
            ),
            State.ROOTED_AMONET_V1_1_0_BBOE: Stage(
                run=lambda: reboot_recovery(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_BBOE_TWRP,
            ),
            State.ROOTED_AMONET_V1_1_0: Stage(
                run=lambda: reboot_recovery(label=to_twrp),
                steps=1,
                then=State.AMONET_V1_1_0_TWRP,
            ),
        }
    goal = GOALS[ARGUMENTS.target]
    return (
        table
        | {
            State.AMONET_V1_1_0_TWRP: Stage(
                run=replace_twrp, steps=1, then=State.AMONET_V1_1_0_BBOE_TWRP
            ),
            State.AMONET_V2_0_0_TWRP: Stage(
                run=amonet_v1_1_0_append,
                steps=2,
                then=State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
            ),
            State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: Stage(
                run=amonet_v1_1_0_chain, steps=9, then=goal
            ),
            State.AMONET_V1_1_0_BBOE_TWRP: Stage(
                run=install_fireos, steps=5, then=State.ROOTED_AMONET_V1_1_0_BBOE
            ),
            State.AMONET_V2_0_0_BOOTED: Stage(
                run=lambda: reboot_recovery(
                    label="waiting for v2.0.0 recovery to start"
                ),
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
    if ARGUMENTS.target == AMONET_BISCUIT_V1_1_0_BBOE:
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
    *, new_data: IO[bytes], ranges: list[tuple[int, int]]
) -> Iterator[bytes]:
    position = 0
    for start, end in ranges:
        for offset in range(position * 4096, start * 4096, 1 << 20):
            yield bytes(min(1 << 20, start * 4096 - offset))
        for offset in range(start * 4096, end * 4096, 1 << 20):
            length = min(1 << 20, end * 4096 - offset)
            chunk = new_data.read(length)
            if len(chunk) != length:
                _die(message=f"{FIREOS.name}'s system.new.dat is short")
            yield chunk
        position = end


def system_image() -> tuple[pathlib.Path, str, int]:
    target = CACHE / f"system-{FIREOS.sha256[:12]}"
    with hold(lock=SESSION.system_lock):
        if not (target / "md5").is_file():
            shutil.rmtree(ignore_errors=True, path=target)
            build_system(target=target)
    want, blocks = (target / "md5").read_text().split()
    return target / "system.img.gz", want, int(blocks)


def unmount(*, started: bool = False) -> None:
    left = adb_shell(command=Shell.UNMOUNT.value).split(sep="\n")[-1]
    if left.startswith("left:"):
        if not left[len("left:") :].strip():
            return
        message = "still mounted: " + left[len("left:") :].strip()
    else:
        message = "the Dot did not answer what is mounted: " + left
    if started:
        restore_failed(message=message + "; do not reboot")
    _die(message=message + "; nothing was written")


def wait_for_twrp() -> None:
    time.sleep(15)
    try:
        run(arguments=["adb", "wait-for-recovery"], timeout=300)
    except subprocess.TimeoutExpired:
        _die(message="the Dot did not reach recovery (TWRP) within 5 minutes")
    deadline = time.monotonic() + 30
    while not adb_shell(command="getprop ro.twrp.version", timeout=30)[
        :1
    ].isdigit() or "mtp" not in adb_shell(command="getprop sys.usb.config"):
        if time.monotonic() > deadline:
            _die(message="TWRP did not finish starting within 30 seconds")
        time.sleep(1)


def write(
    *,
    estimate: str,
    label: str,
    number: int | None = None,
    path: pathlib.Path,
    sector: int,
) -> None:
    size = path.stat().st_size
    if sector % 8 == 0 and size % 4096 == 0:
        block_size, offset, count = 4096, sector // 8, size // 4096
    else:
        block_size, offset, count = 512, sector, size // 512
    verify = (
        f"{SESSION.dd} if={DISK} bs={block_size} skip={offset} count={count}"
        " 2>/dev/null | md5sum"
    )
    want = digest(kind="md5", path=path)
    head = min(size, HEAD_CHECK)
    PROGRESS.begin(estimate=estimate, label=label)
    same_head = head == size or not md5_mismatch(
        command=f"{SESSION.dd} if={DISK} bs={block_size} skip={offset}"
        f" count={head // block_size} 2>/dev/null | md5sum",
        want=digest(kind="md5", limit=head, path=path),
    )
    if same_head and not md5_mismatch(command=verify, want=want):
        PROGRESS.end(skipped=True)
        return
    if number is not None:
        start = adb_shell(command=f"cat /sys/class/block/mmcblk0p{number}/start")
        if start.split(sep="\n")[-1].strip() != str(sector):
            restore_failed(
                message=f"{DISK}p{number} starts at {start or 'nothing'}, not {sector},"
                " so the running partition table is not the one this expects"
            )
        pushed = run(arguments=["adb", "push", path, f"{DISK}p{number}"], timeout=1800)
        if pushed.returncode != 0:
            restore_failed(message=f"{label} failed; do not reboot:\n{pushed.stdout}")
    else:
        staged = DOT_TEMPORARY_DIRECTORY / path.name
        pushed = run(arguments=["adb", "push", path, staged], timeout=120)
        if pushed.returncode != 0:
            restore_failed(
                message=f"{label} did not reach the Dot; do not reboot:"
                f"\n{pushed.stdout}"
            )
        no_truncate = " conv=notrunc" if SESSION.dd == "toybox dd" else ""
        done = adb_shell(
            command=f"{SESSION.dd} if={staged} of={DISK} bs={block_size} seek={offset}"
            f"{no_truncate} && rm -f {staged} && echo written"
        )
        if done.split(sep="\n")[-1] != "written":
            restore_failed(message=f"{label} failed; do not reboot:\n{done}")
    if adb_shell(command=Shell.FLUSH.value).split(sep="\n")[-1] != "flushed":
        restore_failed(message=label + " could not be flushed; do not reboot")
    wrong = md5_mismatch(command=verify, want=want)
    if wrong:
        restore_failed(message=f"{label} did not verify{wrong}; do not reboot")
    PROGRESS.end()


def write_checked(
    *, local: pathlib.Path, node: str, seek: int, work: pathlib.Path
) -> None:
    data = local.read_bytes()
    padded = work / local.name
    padded.write_bytes(data=data.ljust(-(-len(data) // 512) * 512, b"\0"))
    remote = DOT_TEMPORARY_DIRECTORY / local.name
    push_checked(local=padded, remote=remote)
    adb_shell(
        command=Shell.SEEK_WRITE.value.format(seek=seek, source=remote, target=node),
        timeout=600,
    )
    blocks = padded.stat().st_size // 512
    want = digest(kind="md5", path=padded)
    for attempt in range(PUSH_TRIES):
        read = adb_shell(
            command=f"[ -b {node} ] && dd if={node} bs=512 skip={seek}"
            f" count={blocks} 2>/dev/null | md5sum",
            timeout=600,
        )
        if read.split(sep="\n")[-1].split(sep=" ")[0] == want:
            return
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(message=f"{local.name} did not read back from {node}. " + again())


def write_preloader(*, image: pathlib.Path) -> None:
    PROGRESS.begin(estimate="5 s", label="write preloader to boot0")
    staged = DOT_TEMPORARY_DIRECTORY / image.name
    push_checked(local=image, remote=staged)
    adb_shell(command=Shell.BOOT0.value.format(source=staged))
    blocks = image.stat().st_size // 512
    want = digest(kind="md5", path=image)
    for attempt in range(PUSH_TRIES):
        read = adb_shell(
            command="d=dd; toybox dd --help >/dev/null 2>&1 && d='toybox dd';"
            f" $d if=/dev/block/mmcblk0boot0 bs=512 count={blocks} 2>/dev/null | md5sum"
        )
        if read.split(sep="\n")[-1].split(sep=" ")[0] == want:
            return
        if attempt + 1 < PUSH_TRIES:
            reconnect(remote=DISK)
    _die(
        message="the preloader did not read back, so boot0 is still cleared"
        " and the Dot restarts into its bootrom. " + again()
    )


def write_system(*, system: str) -> None:
    image, want, blocks = system_image()
    ready = adb_shell(
        command="umount /system_root /tmp/fireos-system 2>/dev/null;"
        f' d=$(readlink -f {system}); [ -b "$d" ]'
        f' && ! grep -q -e "^$d " -e "^{system} " /proc/mounts && echo ready'
    )
    if ready.split(sep="\n")[-1] != "ready":
        _die(message=f"{system} is not a block device, or it stayed mounted")
    stream = f"gunzip -c | dd of={system} bs=1048576 2>/dev/null"
    read_back = (
        "sync; echo 3 > /proc/sys/vm/drop_caches;"
        f" dd if={system} bs=4096 count={blocks} 2>/dev/null | md5sum"
    )
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(remote=system)
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            with image.open(mode="rb") as file:
                result = run(
                    arguments=["adb", "shell", stream], standard_input=file, timeout=600
                )
            if result.returncode != 0:
                said = result.stdout or f"it exited with {result.returncode}"
                continue
            if adb_shell(command=read_back, timeout=300).split(sep=" ")[0] == want:
                return
            said = "its md5 read back did not match"
        except subprocess.TimeoutExpired as error:
            said = (
                f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
    if said == "its md5 read back did not match":
        (image.parent / "md5").unlink(missing_ok=True)
        said += ". The cached image was discarded, so the next run rebuilds it"
    _die(
        message=f"{system} was not written intact after {PUSH_TRIES} tries;"
        f" the last: {said}"
    )


if __name__ == "__main__":
    main()
