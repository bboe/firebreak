from __future__ import annotations

import base64
import binascii
import contextlib
import enum
import hashlib
import os
import pathlib
import shlex
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import time
import zipfile
from typing import IO, TYPE_CHECKING

from firebreak import updates
from firebreak.android.bootimg import boot_image, cpio, magisk_db, magisk_files
from firebreak.android.ota import transfer_list
from firebreak.cache import (
    CACHE,
    MAGISK,
    Download,
    digest,
    fetch,
    hold,
    slice_path,
    system_sliced,
    write_slices,
)
from firebreak.devices import BUILDS, BY_NAME, biscuit
from firebreak.host import (
    DOT_TEMPORARY_DIRECTORY,
    PUSH_TRIES,
    adb_script,
    adb_shell,
    in_fastboot,
    last_line,
    md5_mismatch,
    push_checked,
    run,
)
from firebreak.probe import read_recovery
from firebreak.recovery import MD5_DIGITS
from firebreak.twrp import (
    ask_fastboot,
    partition_table,
    restart_into_twrp,
    wait_for_twrp,
    write_system,
)
from firebreak.ui import (
    ARGUMENTS,
    PROGRESS,
    SESSION,
    FatalError,
    again,
    confirm,
    invocation,
    title,
    warn,
)
from firebreak.unlock import amonet_chain, kamakiri_chain, restart_refusals

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


ADB_KEY = DOT_TEMPORARY_DIRECTORY / "adbkey.pub"
BOOT_ROOT = Download(
    browser=True,
    mirror=True,
    name="boot-root.zip",
    sha256="de49cc88b27a8e77cf97cf0156bee50e4ddc0e116c41aaede06b494e38397be0",
    size=473633,
    url="https://xdaforums.com/attachments/boot-root-zip.6388001/",
)
BOOT_ROOT_INSTALL = "Installing zip file '/sdcard/boot-root.zip'"
BUILD_NAME = "ro.build.version.name="
BUILD_OK = "build-ok"
ERASED_OK = "erased-ok"
FASTBOOT_WAIT = 120
HIDE_WAIT = 60
HOST_KEY = pathlib.Path.home() / ".android" / "adbkey.pub"
INSTALL_STEPS = 5
KEY_TYPES = {
    bytes.fromhex("2a8648ce3d0201"): "ECDSA",
    bytes.fromhex("2a864886f70d010101"): "RSA",
}
LAST_FIREOS5 = "5.5.5.4"
MAP_DB = "/data/ace/kvstorage/map.db"
MIGRATED_OK = "migrated-ok"
MIGRATE_BUILD = "4315"
MIGRATE_STEPS = 8
MIGRATE_WAIT = 600
MIGRATION_FAILED = frozenset({
    "MIGRATION_PUFFIN_FAIL",
    "NO_MIGRATION_PUFFIN_FINISH",
    "ROLLBACK",
    "ROLLBACK_FINISH",
})
MOUNT_OK = "mount-ok"
PRIVATE_KEY = "device_private_key"
SETUP_WAIT = 300
SIDE_FILES = ("-journal", "-wal")
SIGNATURE = "signature_algorithm"
SIGNED_OK = "signed-ok"
SLOT_OK = "slot-ok"
STAGED_OK = "staged-ok"
STAGE_WAIT = 300
STAGING_OK = "staging-ok"
TWRP = biscuit.BBOE_RECOVERY
UPDATER = "com.amazon.device.software.ota"
UPDATES_OK = "updates-ok"
UPDATE_HOSTS = (
    "amzdigitaldownloads.edgesuite.net",
    "d1s31zyz7dcc2d.cloudfront.net",
    "d1s31zyz7dcc2d.cloudfront.prod.ota-cloudfront.net",
    "prod.ota-cloudfront.net",
    "softwareupdates.amazon.com",
    "updates.amazon.com",
)
UPTIME_OK = "uptime-ok"
VERIFIED = "persist.puffin.verify_migration"
VERIFIED_OK = "verified-ok"
ZIP_OK = "zip-ok"


class Shell(enum.Enum):
    DELETED = "rm -f {path}; [ -e {path} ] || echo {ok}"
    ZEROED = (
        "n=$(( ($(wc -c < {path}) + 4095) / 4096 ));"
        " dd if=/dev/zero bs=4096 count=$n 1<>{path} 2>/dev/null && z=1;"
        ' sync; rm -f {path}; [ -e {path} ] || [ -z "$z" ] || echo {ok}'
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
    UPDATES = """\
m=/tmp/fireos6-system
mkdir -p $m
for s in a b; do
  umount $m 2>/dev/null
  mount -t ext4 {by_name}/system_$s $m || {{ echo fos6-$s; continue; }}
  r=$(grep -l '^service otad ' $m/*.rc 2>/dev/null)
  u=$(grep -l '^service update_engine ' $m/*.rc $m/system/etc/init/*.rc 2>/dev/null)
  h=$m/system/etc/hosts
  p=$m/default.prop
  if [ -f $p ] && [ -f $h ]; then
    echo fos6-$s
    if grep -q '^ro.adb.secure=' $p; then
      sed -i 's|^ro.adb.secure=.*|ro.adb.secure=1|' $p
    else
      echo ro.adb.secure=1 >> $p
    fi
    cat {key} > $m/adb_keys
    chmod 0644 $m/adb_keys
    chcon u:object_r:adb_keys_file:s0 $m/adb_keys 2>/dev/null
    if [ -n "$r" ]; then
      grep -h -A 1 '^service otad ' $r | grep -q '^ *disabled$' || \
sed -i 's|^service otad .*|&\\n    disabled|' $r
    fi
    if [ -n "$u" ]; then
      sed -n '/^service update_engine /,/^[^ ]/p' $u | grep -q '^ *disabled$' || \
sed -i 's|^service update_engine .*|&\\n    disabled|' $u
    fi
    for n in {hosts}; do
      grep -q " $n\\$" $h || echo "127.0.0.1 $n" >> $h
    done
    sync
    k=1
    for n in {hosts}; do grep -q " $n\\$" $h || k=; done
    [ -n "$r" ] && ! grep -h -A 1 '^service otad ' $r | grep -q '^ *disabled$' && k=
    [ -n "$u" ] && ! sed -n '/^service update_engine /,/^[^ ]/p' $u | \
grep -q '^ *disabled$' && k=
    [ -n "$k" ] && echo off-$s
    grep -qx 'ro.adb.secure=1' $p && cmp -s {key} $m/adb_keys && echo locked-$s
  fi
  umount $m
done
rm -f {key}
echo {ok}
"""
    STAGED = (
        "c=/data/csm2puffin; rm -f /cache/recovery/command /data/ota_package/*.bin;"
        " [ -e /cache/recovery/command ] || echo queue-clear;"
        " grep -q ' /data ' /proc/mounts"
        " && [ -f $c/original/rollback_required.txt ]"
        " && [ -s $c/migrated/map/map.db ] && echo staged;"
        ' for f in $c/status-reports/*; do [ -f "$f" ]'
        ' && echo "${{f##*/}}=$(cat "$f")"; done; echo {ok}'
    )
    STAGING = (
        'echo "init=$(getprop com.amazon.csm2puffin.INIT)'
        ' service=$(getprop init.svc.csm2puffin)"; echo {ok}'
    )
    MIGRATED = (
        'echo "boot=$(getprop sys.boot_completed)'
        ' init=$(getprop com.amazon.csm2puffin.INIT)";'
        " [ -s /data/ace/kvstorage/map.db ] && echo map-ok; echo {ok}"
    )
    WRITE = (
        "dd if={source} of={target} bs=1048576 2>/dev/null;"
        " sync; echo 3 > /proc/sys/vm/drop_caches"
    )


def active_slot() -> str:
    deadline = time.monotonic() + 600
    while True:
        said = polled(
            command=f"ps -A | grep -c update_engine; bcbtool get_active; echo {SLOT_OK}"
        )
        if said[-3:-2] == ["0"] and said[-1:] == [SLOT_OK]:
            return said[-2]
        if time.monotonic() > deadline:
            raise FatalError(
                message=f"the {title()} did not report its active slot, with no install"
                " running, within 10 minutes. Leave it powered. " + again()
            )
        time.sleep(5)


def adb_key() -> bytes:
    path = HOST_KEY
    if not path.is_file():
        run(arguments=["adb", "start-server"], timeout=30)
    try:
        key = path.read_bytes()
    except OSError as error:
        raise FatalError(
            message=f"{path} cannot be read. The unlock lets only the adb key in"
            f" it into the {title()}, so nothing was written."
        ) from error
    if not key.strip():
        raise FatalError(
            message=f"{path} is empty. The unlock lets only the adb key in it into"
            f" the {title()}, so nothing was written."
        )
    return key


def adb_state() -> str:
    with contextlib.suppress(subprocess.TimeoutExpired):
        said = run(arguments=["adb", "get-state"], timeout=30).stdout.split("\n")
        return next(
            (line.strip() for line in said if line.strip() in {"device", "recovery"}),
            "",
        )
    return ""


def boot_root_ended() -> str:
    deadline = time.monotonic() + 300
    while True:
        said = polled(
            command="grep -E '^Installing zip file|Updater process ended'"
            f" /tmp/recovery.log | tail -2; echo {ZIP_OK}"
        )
        if (
            said[-1:] == [ZIP_OK]
            and said[-3:-2] == [BOOT_ROOT_INSTALL]
            and "Updater process ended" in said[-2]
        ):
            return said[-2]
        if time.monotonic() > deadline:
            raise FatalError(
                message="TWRP did not finish installing boot-root.zip within 5"
                f" minutes. Leave the {title()} powered. " + again()
            )
        time.sleep(5)


def build_number(*, name: str) -> str:
    return name.rpartition("/")[2].rstrip(")")


def build_system(*, package: Download, target: pathlib.Path) -> None:
    part = CACHE / "system.part"
    shutil.rmtree(ignore_errors=True, path=part)
    part.mkdir()
    fireos = fetch(download=package)
    with zipfile.ZipFile(file=fireos) as archive:
        unread = FatalError(
            message=f"{package.name} has a transfer list this does not read"
        )
        try:
            transfers = transfer_list(
                text=archive.read(name="system.transfer.list").decode()
            )
        except FatalError as error:
            raise unread from error
        ranges = [
            (block_range.start // 4096, block_range.end // 4096)
            for command in transfers.commands
            if command.verb == "new"
            for block_range in command.ranges
        ]
        if not ranges or ranges != sorted(ranges):
            raise unread
        blocks = transfers.size // 4096
        ranges.append((blocks, blocks))
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


def check_fireos5(*, version: str) -> None:
    if ARGUMENTS.target.device != biscuit.BISCUIT:
        raise FatalError(
            message=f"this {title()} holds Fire OS {version}. firebreak keeps a"
            " setup through Amazon's move to Fire OS 6 only on the Echo Dot (2nd"
            " Generation) so far, so Fire OS 6 was not written. Run"
            " again with --factory-reset to erase it and install Fire OS 6"
            f" {ARGUMENTS.target.installs.build}."
        )
    if version != LAST_FIREOS5:
        raise FatalError(
            message=f"this {title()} holds Fire OS {version}. Only Fire OS"
            f" {LAST_FIREOS5} carries Amazon's move to Fire OS 6 that keeps the"
            " setup, so Fire OS 6 was not written. Run again with"
            " --factory-reset to erase it and install Fire OS 6"
            f" {ARGUMENTS.target.installs.build}."
        )


def check_staged(*, booted: bool) -> None:
    script = Shell.STAGED.value.format(ok=STAGED_OK)
    said = adb_shell(
        command=f"su -c {shlex.quote(script)}" if booted else script, timeout=60
    ).split(sep="\n")
    if said[-1:] != [STAGED_OK]:
        raise FatalError(
            message=f"the {title()} did not say whether Fire OS {LAST_FIREOS5}"
            " prepared its move to Fire OS 6, so Fire OS 6 was not written. " + again()
        )
    if "queue-clear" not in said:
        raise FatalError(
            message=f"the update Amazon queued for this {title()} could not be"
            " removed, and the restart would install it, so Fire OS 6 was not"
            " written. " + again()
        )
    reports = {
        name: value
        for name, _, value in (line.partition("=") for line in said)
        if name.endswith("Success")
    }
    failed = sorted(name for name, value in reports.items() if value != "1")
    if "staged" in said and "MapMigrationSuccess" in reports and not failed:
        return
    why = (
        f"{', '.join(failed)} did not succeed"
        if failed
        else "that copy is missing or incomplete"
    )
    retry = (
        " Restart it, wait for its ring to settle, then run again; or run"
        if booted
        else " Run"
    )
    raise FatalError(
        message=f"Fire OS {LAST_FIREOS5} copies this {title()}'s setup for Fire OS"
        f" 6 each time it starts, and here {why}, so Fire OS 6 was not"
        f" written.{retry}"
        " again with --factory-reset to erase it and install Fire OS 6"
        f" {ARGUMENTS.target.installs.build}."
    )


def confirm_migration() -> None:
    if SESSION.migration_confirmed:
        return
    confirm(
        force=SESSION.no_wait,
        what=f"This {title()} runs Fire OS {LAST_FIREOS5}. To keep its setup,"
        f" firebreak installs Amazon's bridge build, Fire OS 6 {MIGRATE_BUILD},"
        " starts it once so it moves the setup over and reaches Alexa on its"
        " Wi-Fi, then installs Fire OS 6"
        f" {ARGUMENTS.target.installs.build}. That takes about 3 minutes more"
        f" than --factory-reset, which erases the {title()}",
    )
    SESSION.migration_confirmed = True


def erased(*, path: str, wiped: bool) -> None:
    shell = Shell.ZEROED if wiped else Shell.DELETED
    said = adb_shell(command=shell.value.format(ok=ERASED_OK, path=path))
    if last_line(said=said).strip() != ERASED_OK:
        warn(
            text=f"{path} may still be in userdata: its"
            f" {'zeroing and ' if wiped else ''}delete did not report back."
        )


def finish_setup(*, since: float) -> None:
    PROGRESS.begin(estimate=60, label=f"waiting for {MIGRATE_BUILD} to reach Alexa")
    deadline = time.monotonic() + SETUP_WAIT
    try:
        while True:
            left_recovery(doing="finish its setup", since=since)
            said = polled(command=f"start otad; getprop {VERIFIED}; echo {VERIFIED_OK}")
            if said[-2:] == ["true", VERIFIED_OK]:
                return
            if time.monotonic() > deadline:
                raise FatalError(
                    message=f"Fire OS 6 {MIGRATE_BUILD} did not finish its setup"
                    f" within {SETUP_WAIT // 60} minutes of its restart. It finishes"
                    f" only once it reaches Alexa, so check the {title()}'s Wi-Fi."
                    f" Fire OS 6 {ARGUMENTS.target.installs.build} was not installed. "
                    + again()
                )
            time.sleep(5)
    finally:
        polled(command="stop otad")


def from_fireos5_twrp(*, install: Callable[[], object]) -> object:
    if not (ARGUMENTS.factory_reset or SESSION.migration_confirmed):
        raise FatalError(
            message=f"this {title()} is in the TWRP of its Fire OS 5 chain. Its"
            " setup moves to Fire OS 6 only after a check made from Fire OS 5"
            " itself, because the next write leaves Fire OS 5 unable to start,"
            f" so nothing was written. Start it with {invocation(options=['reboot'])},"
            " wait for it to finish starting, then run this again. If Fire OS 5"
            " refuses this computer's adb key, or to erase it instead, run again"
            " with --factory-reset, which installs Fire OS 6"
            f" {ARGUMENTS.target.installs.build}."
        )
    return install()


def hide_updater() -> None:
    def hidden() -> bool:
        output = adb_shell(command=f"su -c 'dumpsys package {UPDATER}'", timeout=60)
        return any(
            line.strip().startswith("User 0:") and "hidden=true" in line
            for line in output.split(sep="\n")
        )

    if hidden():
        return
    delay = 1
    deadline = time.monotonic() + HIDE_WAIT
    while True:
        adb_shell(command=f"su -c 'pm hide {UPDATER}'", timeout=60)
        if hidden():
            return
        left = deadline - time.monotonic()
        if left <= 0:
            raise FatalError(
                message=f"{UPDATER} is not hidden; an update would replace the"
                " boot image and remove root"
            )
        if delay == 1:
            warn(
                text=f"{UPDATER} is not hidden yet. The {title()} may still be"
                " starting, so this tries again for up to a minute."
            )
        time.sleep(min(delay, left))
        delay *= 2


def install_and_root() -> None:
    zip_path = fetch(download=BOOT_ROOT)
    if "boot_a_x" in partition_table():
        raise FatalError(
            message="this TWRP runs on a boot moved partition table. " + again()
        )
    build = "" if ARGUMENTS.factory_reset else installed_build(slot=active_slot())
    if "." in build:
        write_bridge(fireos5=build)
        build = MIGRATE_BUILD
    said = (
        setup_state()
        if build == MIGRATE_BUILD
        and not ARGUMENTS.factory_reset
        and ARGUMENTS.target.device == biscuit.BISCUIT
        else []
    )
    moving = "moving" in said
    if moving and ("pending" in said or "verified" not in said):
        move_setup(moved="pending" not in said, zip_path=zip_path)
    wiped = not build
    upgraded = not wiped and outdated(build=build)
    if not ARGUMENTS.factory_reset:
        PROGRESS.steps = (
            PROGRESS.step
            + moving
            + (install_steps() - upgraded if wiped or upgraded else 2)
        )
    if moving:
        sign_setup()
    if wiped or upgraded:
        install_fireos6(wipe=wiped)
        build = ARGUMENTS.target.installs.build
    root_slot(build=build, wiped=wiped, zip_path=zip_path)


def install_fireos6(*, wipe: bool) -> None:
    build = ARGUMENTS.target.installs.build
    update_file = updates.download(build=build, builds=BUILDS[ARGUMENTS.target.device])
    if wipe:
        PROGRESS.begin(estimate=10, label="wiping cache and data")
        for part in ("cache", "data"):
            adb_shell(command="twrp wipe " + part, timeout=120)
    update = "/sdcard/update.zip"
    command = ARGUMENTS.target.device.fastboot_command
    for index, slot in enumerate(iterable=("first", "second")):
        if index and command:
            twrp_by_fastboot(command=command)
        PROGRESS.begin(
            estimate=135,
            label=f"installing Fire OS 6 {build}, {slot} slot",
        )
        if index and not command:
            run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)
            wait_for_twrp()
        if not index or md5_mismatch(
            command=f"md5sum {update}", want=digest(kind="md5", path=update_file)
        ):
            push_checked(local=update_file, remote=update)
        before = active_slot()
        adb_shell(command="twrp install " + update, timeout=600)
        after = active_slot()
        if index:
            erased(path=update, wiped=True)
        if {before, after} != {"a", "b"}:
            raise FatalError(
                message=f"installing Fire OS 6 {build} left the"
                f" active slot {after!r}, where it was {before!r}. " + again()
            )


def install_magisk(*, magisk: pathlib.Path, work: pathlib.Path) -> None:
    database = work / "magisk.db"
    magisk_db(path=database)
    files = magisk_files(database=database.read_bytes(), magisk=magisk)
    archive = work / "magisk.cpio"
    archive.write_bytes(data=cpio(files=files))
    push_checked(local=archive, remote=DOT_TEMPORARY_DIRECTORY / "magisk.cpio")
    if not adb_script(body=Shell.MAGISK.value, name="magisk.sh", work=work):
        raise FatalError(message="Magisk 17.3 did not install")
    names = sorted(name for name, (mode, _) in files.items() if stat.S_ISREG(mode))
    want = hashlib.md5(
        b"".join(files[name][1] for name in names), usedforsecurity=False
    ).hexdigest()
    paths = " ".join(name.decode() for name in names)
    if md5_mismatch(command=f"cd /; cat {paths} | md5sum", want=want):
        raise FatalError(message=f"Magisk 17.3's files did not verify on the {title()}")


def install_steps() -> int:
    return INSTALL_STEPS + bool(ARGUMENTS.target.device.fastboot_command)


def installed_build(*, slot: str) -> str:
    PROGRESS.begin(estimate=5, label="reading the installed Fire OS 6 build")
    said = adb_shell(
        command=f"m=/tmp/installed-system; mkdir -p $m; umount $m 2>/dev/null;"
        f" mount -o ro {BY_NAME}/system_{slot} $m && echo {MOUNT_OK};"
        " cat $m/system/build.prop $m/build.prop 2>/dev/null"
        " | grep -m 1 '^ro.build.version.name=';"
        f" umount $m; echo {BUILD_OK}",
        timeout=60,
    ).split(sep="\n")
    if said[-1:] != [BUILD_OK]:
        raise FatalError(
            message=f"the {title()} did not say which Fire OS slot {slot} holds;"
            " its Fire OS and data are as they were. " + again()
        )
    if MOUNT_OK not in said:
        raise FatalError(
            message=f"the {title()} did not mount slot {slot}'s system, so this run"
            " cannot tell what it holds; its Fire OS and data are as they were. "
            + again()
            + " A slot that never mounts needs --factory-reset, which installs Fire"
            f" OS 6 {ARGUMENTS.target.installs.build} without reading it."
        )
    name = next(
        (line.partition("=")[2] for line in said if line.startswith(BUILD_NAME)), ""
    )
    if name.startswith("Fire OS 5."):
        return name.split()[2]
    if not name.startswith("Fire OS 6"):
        return ""
    build = build_number(name=name)
    if build not in BUILDS[ARGUMENTS.target.device]:
        raise FatalError(
            message=f"slot {slot} holds {name}, a Fire OS 6 build firebreak does not"
            " know, so it does not patch it; its Fire OS and data are as they were."
            f" Run again with --factory-reset to erase it and install Fire OS 6"
            f" {ARGUMENTS.target.installs.build}."
        )
    return build


def key_type(*, value: bytes | str | None) -> str:
    text = value.encode() if isinstance(value, str) else value or b""
    try:
        der = base64.b64decode(
            b"".join(
                line
                for line in text.splitlines()
                if not line.strip().startswith(b"-----")
            )
        )
    except binascii.Error:
        return ""
    return next((name for oid, name in KEY_TYPES.items() if oid in der), "")


def leave_fireos5(*, reboot: Callable[[], object]) -> None:
    if not ARGUMENTS.factory_reset:
        name = adb_shell(command="getprop ro.build.version.name")
        check_fireos5(
            version=name.split()[2] if name.startswith("Fire OS 5.") else name
        )
        confirm_migration()
        hide_updater()
        wait_staged()
        check_staged(booted=True)
    reboot()


def left_recovery(*, doing: str, since: float) -> None:
    if adb_state() != "recovery":
        return
    elapsed = time.monotonic() - since
    said = polled(command=f"cat /proc/uptime; echo {UPTIME_OK}")
    up = said[-2].partition(" ")[0] if said[-2:-1] and said[-1] == UPTIME_OK else ""
    if up.replace(".", "", 1).isdigit() and float(up) < elapsed:
        raise FatalError(
            message=f"the {title()} restarted into TWRP while Fire OS 6"
            f" {MIGRATE_BUILD} was meant to {doing}, so the run stopped there. Its"
            f" data is as Fire OS 6 {MIGRATE_BUILD} left it. " + again()
        )


def move_setup(*, moved: bool, zip_path: pathlib.Path) -> None:
    PROGRESS.steps = PROGRESS.step + MIGRATE_STEPS - 2 - moved + install_steps() - 1
    since = time.monotonic()
    root_slot(build=MIGRATE_BUILD, wiped=False, zip_path=zip_path)
    if not moved:
        wait_migrated(since=since)
    finish_setup(since=since)
    restart_into_twrp(device=ARGUMENTS.target.device)
    wait_for_twrp()


def outdated(*, build: str) -> bool:
    return build.isdigit() and int(build) < int(ARGUMENTS.target.installs.build)


def polled(*, command: str) -> list[str]:
    try:
        return adb_shell(command=command, timeout=30).split(sep="\n")
    except subprocess.TimeoutExpired:
        return []


def reboot_rooted() -> None:
    for attempt in range(PUSH_TRIES):
        if attempt and not still_in_recovery():
            return
        if run(arguments=["adb", "reboot"], timeout=60).returncode == 0:
            return
    raise FatalError(
        message=f"the {title()} did not take adb reboot. boot-root.zip is installed,"
        f" so unplug the {title()}'s power and plug it back in to start rooted"
        " Fire OS 6."
    )


def root_slot(*, build: str, wiped: bool, zip_path: pathlib.Path) -> None:
    PROGRESS.begin(estimate=10, label="installing boot-root")
    push_checked(local=zip_path, remote="/sdcard/boot-root.zip")
    output = adb_shell(command="twrp install /sdcard/boot-root.zip", timeout=300)
    errors = [line for line in output.split(sep="\n") if "(!) Error" in line]
    if errors:
        raise FatalError(message="boot-root.zip failed: " + errors[0])
    ended = boot_root_ended()
    erased(path="/sdcard/boot-root.zip", wiped=wiped)
    if not ended.endswith("RC=0"):
        raise FatalError(message="boot-root.zip failed: " + ended)
    slot = active_slot()
    patched = adb_shell(
        command=f"grep -c 'slot _{slot}: neutering ota updates' /tmp/recovery.log;"
        f" echo {ZIP_OK}",
        timeout=30,
    ).split(sep="\n")
    counted = "".join(patched[-2:-1]).strip()
    if patched[-1:] != [ZIP_OK] or not counted.isdigit() or not int(counted):
        raise FatalError(
            message=f"boot-root.zip ended without patching slot {slot}, which holds"
            f" Fire OS 6 {build}. " + again()
        )
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        key = pathlib.Path(temporary) / ADB_KEY.name
        key.write_bytes(data=adb_key())
        push_checked(local=key, remote=ADB_KEY)
    off = adb_shell(
        command=Shell.UPDATES.value.format(
            by_name=BY_NAME, hosts=" ".join(UPDATE_HOSTS), key=ADB_KEY, ok=UPDATES_OK
        ),
        timeout=60,
    ).split(sep="\n")
    found = {line[len("fos6-") :] for line in off if line.startswith("fos6-")}
    missed = sorted(name for name in found | {slot} if f"off-{name}" not in off)
    if off[-1:] != [UPDATES_OK] or missed:
        raise FatalError(
            message="Amazon's updates were not blocked in Fire OS 6's"
            f" slot {' and '.join(missed or [slot])}. " + again()
        )
    open_slots = sorted(name for name in found | {slot} if f"locked-{name}" not in off)
    if open_slots:
        raise FatalError(
            message="adb was not locked to this computer's key in Fire OS 6's"
            f" slot {' and '.join(open_slots)}. " + again()
        )
    PROGRESS.begin(estimate=60, label=f"waiting for rooted Fire OS 6 {build}")
    reboot_rooted()


def setup_state() -> list[str]:
    said = adb_shell(
        command="grep -q ' /data ' /proc/mounts || mount /data;"
        " grep -q ' /data ' /proc/mounts && echo mounted; c=/data/csm2puffin;"
        " [ -f $c/original/rollback_required.txt ] && echo pending;"
        " [ -f $c/original/rollback_required.txt ] || [ -f $c/migration_success.txt ]"
        f' && echo moving; [ "$(cat /data/property/{VERIFIED} 2>/dev/null)" = true ]'
        f" && echo verified; echo {STAGED_OK}",
        timeout=60,
    ).split(sep="\n")
    if said[-1:] != [STAGED_OK]:
        raise FatalError(
            message=f"the {title()} did not say whether Fire OS 6 {MIGRATE_BUILD}"
            " still has a setup to move, so its data was not touched. " + again()
        )
    if "mounted" not in said:
        raise FatalError(
            message=f"TWRP could not mount the {title()}'s data, so it cannot tell"
            f" whether Fire OS 6 {MIGRATE_BUILD} has a setup to move. "
            + again()
            + " Data that never mounts needs --factory-reset, which erases it and"
            f" installs Fire OS 6 {ARGUMENTS.target.installs.build}."
        )
    return said


def sign_setup() -> None:
    PROGRESS.begin(estimate=10, label="adding the moved setup's signing algorithm")
    sides = [f"{MAP_DB}{suffix}" for suffix in SIDE_FILES]
    said = adb_shell(
        command="grep -q ' /data ' /proc/mounts || mount /data;"
        f" grep -q ' /data ' /proc/mounts && md5sum {MAP_DB};"
        f" for f in {' '.join(sides)}; do [ -s $f ] && md5sum $f; done;"
        f" echo {SIGNED_OK}",
        timeout=60,
    ).split(sep="\n")
    held = {
        name.strip(): value
        for value, _, name in (line.partition(" ") for line in said)
        if name.strip() in {MAP_DB, *sides}
    }
    unread = FatalError(
        message=f"{MAP_DB}, the {title()}'s moved setup, could not be read in TWRP,"
        f" so Fire OS 6 {ARGUMENTS.target.installs.build} was not installed. " + again()
    )
    if (
        said[-1:] != [SIGNED_OK]
        or MAP_DB not in held
        or any(len(value) != MD5_DIGITS for value in held.values())
    ):
        raise unread
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        local = pathlib.Path(temporary) / "map.db"
        for remote, value in held.items():
            copy = local.with_name(pathlib.PurePosixPath(remote).name)
            pulled = run(arguments=["adb", "pull", remote, copy], timeout=60)
            if pulled.returncode or not copy.is_file():
                raise unread
            if digest(kind="md5", path=copy) != value:
                raise unread
        if not signature_added(path=local):
            return
        staged = DOT_TEMPORARY_DIRECTORY / "map.db"
        push_checked(local=local, remote=staged)
        wrong = md5_mismatch(
            command=f"cat {staged} > {MAP_DB} && rm -f {staged} {' '.join(sides)}"
            f" {MAP_DB}-shm;"
            f" md5sum {MAP_DB}",
            timeout=60,
            want=digest(kind="md5", path=local),
        )
    if wrong:
        raise FatalError(
            message=f"{MAP_DB} did not verify on the {title()}{wrong}. " + again()
        )


def signature_added(*, path: pathlib.Path) -> bool:
    unknown = FatalError(
        message=f"the {title()}'s moved setup holds no device key Fire OS 6 can sign"
        f" with, so Fire OS 6 {ARGUMENTS.target.installs.build} was not installed."
        f" Fire OS 6 {MIGRATE_BUILD} still runs with the setup. Run again with"
        " --factory-reset to erase it and install Fire OS 6"
        f" {ARGUMENTS.target.installs.build}."
    )
    try:
        with contextlib.closing(sqlite3.connect(str(path))) as database, database:
            rows = dict(
                database.execute(
                    "SELECT key, value FROM deviceData WHERE key IN (?, ?)",
                    (PRIVATE_KEY, SIGNATURE),
                )
            )
            kind = "" if SIGNATURE in rows else key_type(value=rows.get(PRIVATE_KEY))
            if kind:
                database.execute(
                    "INSERT INTO deviceData (key, value) VALUES (?, ?)",
                    (SIGNATURE, f"SHA256With{kind}:1.0".encode()),
                )
    except sqlite3.Error as error:
        raise unknown from error
    if not kind and SIGNATURE not in rows:
        raise unknown
    return bool(kind)


def stage_install_fireos(*, reboot: bool = True, slot: str = "") -> None:
    fireos = fetch(download=ARGUMENTS.target.installs.package)
    magisk = fetch(download=MAGISK)
    slot = slot or adb_shell(command="getprop ro.boot.slot_suffix", timeout=30)
    if slot not in {"_a", "_b"}:
        raise FatalError(message=f"TWRP reports the boot slot {slot!r}, not _a or _b")
    boot, system = f"{BY_NAME}/boot{slot}_x", f"{BY_NAME}/system{slot}"
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        work = pathlib.Path(temporary)
        PROGRESS.begin(estimate=5, label="formatting userdata")
        if not adb_script(body=Shell.DATA.value, name="data.sh", work=work):
            raise FatalError(message="userdata did not format and mount")
        PROGRESS.begin(estimate=120, label="writing Fire OS 5.5.5.4's /system")
        slices, want, blocks = system_image(package=ARGUMENTS.target.installs.package)
        write_system(blocks=blocks, slices=slices, system=system, want=want)
        body = Shell.SYSTEM.value.format(hosts=" ".join(UPDATE_HOSTS), system=system)
        if not adb_script(body=body, name="system.sh", work=work):
            raise FatalError(message="patching /system failed")

        PROGRESS.begin(estimate=10, label="writing the boot image and Magisk")
        data = boot_image(fireos=fireos, key=adb_key(), magisk=magisk)
        wrong = write_boot(data=data, target=boot)
        if wrong:
            raise FatalError(
                message=f"the patched boot image did not verify on the {title()}"
                + wrong
            )

        install_magisk(magisk=magisk, work=work)
    if reboot:
        PROGRESS.begin(estimate=345, label="waiting for rooted Fire OS 5")
        run(arguments=["adb", "reboot"])


def stage_install_fireos6() -> None:
    amonet_chain()
    install_and_root()


def stage_install_kamakiri() -> None:
    kamakiri_chain()
    install_and_root()


def stage_replace_twrp() -> None:
    twrp = fetch(download=TWRP)
    PROGRESS.begin(
        estimate=40,
        label=f"waiting for TWRP {biscuit.BBOE_TWRP_VERSION}",
    )
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
    if md5_mismatch(command=read_back, timeout=120, want=digest(kind="md5", path=twrp)):
        raise FatalError(
            message=f"TWRP {biscuit.BBOE_TWRP_VERSION} did not verify in"
            f" recovery. Leave the {title()} running. " + again()
        )
    run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)


def stage_swap_twrp() -> None:
    image = fetch(download=TWRP)
    PROGRESS.begin(
        estimate=10, label=f"writing TWRP {biscuit.BBOE_TWRP_VERSION} to recovery"
    )
    remote = "/data/local/tmp/recovery.img"
    run(arguments=["adb", "push", image, remote], check=True, timeout=120)
    write = Shell.WRITE.value.format(source=remote, target=f"{BY_NAME}/recovery")
    adb_shell(command="su -c " + shlex.quote(s=f"{write}; rm -f {remote}"), timeout=120)
    size = image.stat().st_size
    if hashlib.md5(
        read_recovery(size=size), usedforsecurity=False
    ).hexdigest() != digest(kind="md5", path=image):
        raise FatalError(
            message=f"TWRP {biscuit.BBOE_TWRP_VERSION} did not verify in"
            f" recovery. Leave the {title()} running. " + again()
        )


def still_in_recovery() -> bool:
    deadline = time.monotonic() + 120
    while True:
        state = adb_state()
        if state in {"device", "recovery"}:
            return state == "recovery"
        if time.monotonic() > deadline:
            return True
        time.sleep(5)


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
                raise FatalError(message=f"{name}'s system.new.dat is short")
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


def twrp_by_fastboot(*, command: bytes) -> None:
    ask_fastboot(command=command)
    run(arguments=["adb", "reboot"], check=True, timeout=60)
    deadline = time.monotonic() + FASTBOOT_WAIT
    while not in_fastboot():
        if time.monotonic() > deadline:
            raise FatalError(
                message=f"the {title()} did not reach fastboot within"
                f" {FASTBOOT_WAIT} seconds of asking for it, between the two"
                " slot installs. " + again()
            )
        time.sleep(2)
    refused = restart_refusals()
    if refused:
        raise FatalError(
            message=f"the {title()}'s fastboot took neither command that starts"
            " its TWRP between the two slot installs: "
            + "; ".join(f"{words}: {said}" for words, said in refused)
            + ". "
            + again()
        )
    wait_for_twrp()


def wait_migrated(*, since: float) -> None:
    PROGRESS.begin(
        estimate=90,
        label=f"waiting for {MIGRATE_BUILD}'s migration",
    )
    deadline = time.monotonic() + MIGRATE_WAIT
    while True:
        left_recovery(doing="move the setup", since=since)
        said = polled(command=Shell.MIGRATED.value.format(ok=MIGRATED_OK))
        state = next(
            (
                line.partition(" init=")[2]
                for line in said
                if line.startswith("boot=1 init=")
            ),
            "",
        )
        if said[-1:] == [MIGRATED_OK] and state:
            if state == "MIGRATION_PUFFIN_FINISH" and "map-ok" in said:
                return
            if state in MIGRATION_FAILED or state == "MIGRATION_PUFFIN_FINISH":
                raise FatalError(
                    message=f"Fire OS 6 {MIGRATE_BUILD} did not move this"
                    f" {title()}'s setup: Amazon's migration ended {state}"
                    f"{'' if state in MIGRATION_FAILED else ' with no registration'}."
                    " Its data is still there. Run again with --factory-reset to"
                    " erase it and install Fire OS 6"
                    f" {ARGUMENTS.target.installs.build}."
                )
        if time.monotonic() > deadline:
            raise FatalError(
                message=f"Fire OS 6 {MIGRATE_BUILD} did not finish moving this"
                f" {title()}'s setup within {MIGRATE_WAIT // 60} minutes of its"
                f" restart. Leave the {title()} powered. " + again()
            )
        time.sleep(5)


def wait_staged() -> None:
    deadline = time.monotonic() + STAGE_WAIT
    noted = False
    while True:
        said = polled(command=Shell.STAGING.value.format(ok=STAGING_OK))
        if said[-2:] == ["init=MIGRATION_CSM_FINISH service=stopped", STAGING_OK]:
            return
        if time.monotonic() > deadline:
            raise FatalError(
                message=f"Fire OS {LAST_FIREOS5} did not finish copying this"
                f" {title()}'s setup for Fire OS 6 within {STAGE_WAIT // 60}"
                " minutes, so Fire OS 6 was not written. Restart it, wait for its"
                " ring to settle, then run again."
            )
        if not noted:
            PROGRESS.note(
                message=f"waiting for Fire OS {LAST_FIREOS5} to finish copying this"
                f" {title()}'s setup for Fire OS 6."
            )
            noted = True
        time.sleep(5)


def write_boot(*, data: bytes, target: str) -> str:
    padded = data.ljust(-(-len(data) // 4096) * 4096, b"\0")
    final = DOT_TEMPORARY_DIRECTORY / "boot.img"
    read_back = (
        f"[ -b {target} ] && dd if={target} bs=4096 count={len(padded) // 4096}"
        " 2>/dev/null | md5sum"
    )
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        image = pathlib.Path(temporary) / "boot.img"
        image.write_bytes(data=padded)
        push_checked(local=image, remote=final)
        adb_shell(
            command=Shell.WRITE.value.format(source=final, target=target),
            timeout=120,
        )
        return md5_mismatch(
            command=read_back,
            timeout=120,
            want=hashlib.md5(padded, usedforsecurity=False).hexdigest(),
        )


def write_bridge(*, fireos5: str) -> None:
    check_fireos5(version=fireos5)
    confirm_migration()
    check_staged(booted=False)
    PROGRESS.steps = PROGRESS.step + MIGRATE_STEPS + install_steps() - 1
    package = BUILDS[ARGUMENTS.target.device][MIGRATE_BUILD]
    slot = active_slot()
    PROGRESS.begin(estimate=10, label=f"writing Fire OS 6 {MIGRATE_BUILD}'s boot image")
    with zipfile.ZipFile(file=fetch(download=package)) as archive:
        data = archive.read(name="boot.img")
    wrong = write_boot(data=data, target=f"{BY_NAME}/boot_{slot}")
    if wrong:
        raise FatalError(
            message=f"Fire OS 6 {MIGRATE_BUILD}'s boot image did not verify on the"
            f" {title()}{wrong}. " + again()
        )
    PROGRESS.begin(estimate=120, label=f"writing Fire OS 6 {MIGRATE_BUILD}'s /system")
    slices, want, blocks = system_image(package=package)
    write_system(
        blocks=blocks, slices=slices, system=f"{BY_NAME}/system_{slot}", want=want
    )
