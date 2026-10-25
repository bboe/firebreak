from __future__ import annotations

import contextlib
import enum
import hashlib
import os
import pathlib
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile
from typing import IO, TYPE_CHECKING

from firebreak import updates
from firebreak.android.bootimg import boot_image, cpio, magisk_db, magisk_files
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
    md5_mismatch,
    push_checked,
    run,
)
from firebreak.probe import read_recovery
from firebreak.twrp import partition_table, wait_for_twrp, write_system
from firebreak.ui import ARGUMENTS, PROGRESS, SESSION, FatalError, again, title, warn
from firebreak.unlock import amonet_chain

if TYPE_CHECKING:
    from collections.abc import Iterator


BOOT_ROOT = Download(
    browser=True,
    mirror=True,
    name="boot-root.zip",
    sha256="de49cc88b27a8e77cf97cf0156bee50e4ddc0e116c41aaede06b494e38397be0",
    size=473633,
    url="https://xdaforums.com/attachments/boot-root-zip.6388001/",
)
BOOT_ROOT_INSTALL = "Installing zip file '/sdcard/boot-root.zip'"
HIDE_WAIT = 60
SLOT_OK = "slot-ok"
TWRP = biscuit.BBOE_RECOVERY
UPDATER = "com.amazon.device.software.ota"
UPDATE_HOSTS = (
    "updates.amazon.com",
    "softwareupdates.amazon.com",
    "amzndigitaldownloads.edgesuite.net",
    "amzdigital-a.akamaihd.com",
)
ZIP_OK = "zip-ok"


class Shell(enum.Enum):
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


def build_system(*, package: Download, target: pathlib.Path) -> None:
    part = CACHE / "system.part"
    shutil.rmtree(ignore_errors=True, path=part)
    part.mkdir()
    fireos = fetch(download=package)
    with zipfile.ZipFile(file=fireos) as archive:
        words = archive.read(name="system.transfer.list").decode().split()
        commands = dict(zip(words[4::2], words[5::2]))
        if words[0] != "3" or set(commands) != {"erase", "new"}:
            raise FatalError(
                message=f"{package.name} has a transfer list this does not read"
            )
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


def stage_install_fireos(*, reboot: bool = True, slot: str = "") -> None:
    fireos = fetch(download=ARGUMENTS.target.installs.package)
    magisk = fetch(download=MAGISK)
    slot = slot or adb_shell(command="getprop ro.boot.slot_suffix", timeout=30)
    if slot not in {"_a", "_b"}:
        raise FatalError(message=f"TWRP reports the boot slot {slot!r}, not _a or _b")
    boot, system = f"{BY_NAME}/boot{slot}_x", f"{BY_NAME}/system{slot}"
    with tempfile.TemporaryDirectory(dir=CACHE) as temporary:
        work = pathlib.Path(temporary)
        PROGRESS.begin(estimate="5 s", label="formatting userdata")
        if not adb_script(body=Shell.DATA.value, name="data.sh", work=work):
            raise FatalError(message="userdata did not format and mount")
        PROGRESS.begin(estimate="120 s", label="writing Fire OS 5.5.5.4's /system")
        slices, want, blocks = system_image(package=ARGUMENTS.target.installs.package)
        write_system(blocks=blocks, slices=slices, system=system, want=want)
        body = Shell.SYSTEM.value.format(hosts=" ".join(UPDATE_HOSTS), system=system)
        if not adb_script(body=body, name="system.sh", work=work):
            raise FatalError(message="patching /system failed")

        PROGRESS.begin(estimate="10 s", label="writing the boot image and Magisk")
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
        wrong = md5_mismatch(
            command=read_back, timeout=120, want=digest(kind="md5", path=image)
        )
        if wrong:
            raise FatalError(
                message=f"the patched boot image did not verify on the {title()}"
                + wrong
            )

        install_magisk(magisk=magisk, work=work)
    if reboot:
        PROGRESS.begin(estimate="345 s", label="waiting for rooted Fire OS 5 to boot")
        run(arguments=["adb", "reboot"])


def stage_install_fireos6() -> None:
    amonet_chain()
    build = ARGUMENTS.target.installs.build
    update_file = updates.download(build=build, builds=BUILDS[ARGUMENTS.target.device])
    zip_path = fetch(download=BOOT_ROOT)
    if "boot_a_x" in partition_table():
        raise FatalError(
            message="v2's TWRP runs on amonet v1.1.0's partition table. " + again()
        )
    PROGRESS.begin(estimate="10 s", label="wiping cache and data")
    for part in ("cache", "data"):
        adb_shell(command="twrp wipe " + part, timeout=120)
    update = "/sdcard/update.zip"
    for index, slot in enumerate(iterable=("first", "second")):
        PROGRESS.begin(
            estimate="135 s",
            label=f"installing Fire OS 6 {build}, {slot} slot",
        )
        if index:
            run(arguments=["adb", "reboot", "recovery"], check=True, timeout=60)
            wait_for_twrp()
        push_checked(local=update_file, remote=update)
        before = active_slot()
        adb_shell(command="twrp install " + update, timeout=600)
        after = active_slot()
        if {before, after} != {"a", "b"}:
            raise FatalError(
                message=f"installing Fire OS 6 {build} left the"
                f" active slot {after!r}, where it was {before!r}. " + again()
            )
    PROGRESS.begin(estimate="10 s", label="installing boot-root")
    push_checked(local=zip_path, remote="/sdcard/boot-root.zip")
    output = adb_shell(command="twrp install /sdcard/boot-root.zip", timeout=300)
    errors = [line for line in output.split(sep="\n") if "(!) Error" in line]
    if errors:
        raise FatalError(message="boot-root.zip failed: " + errors[0])
    ended = boot_root_ended()
    if not ended.endswith("RC=0"):
        raise FatalError(message="boot-root.zip failed: " + ended)
    PROGRESS.begin(estimate="60 s", label="waiting for rooted Fire OS 6 to boot")
    reboot_rooted()


def stage_replace_twrp() -> None:
    twrp = fetch(download=TWRP)
    PROGRESS.begin(
        estimate="40 s",
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
        estimate="10 s", label=f"writing TWRP {biscuit.BBOE_TWRP_VERSION} to recovery"
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
        with contextlib.suppress(subprocess.TimeoutExpired):
            state = run(arguments=["adb", "get-state"], timeout=30).stdout.strip()
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
