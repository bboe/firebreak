"""Simulate an Echo Dot (2nd Generation) for firebreak and dot_firmware.py.

python3 sim/dot.py create [--cache DIR] [--start fastboot|no-light|stock-booted]
python3 sim/dot.py plug
python3 sim/dot.py status
python3 sim/dot.py snapshot
python3 sim/dot.py table FILE
python3 sim/dot.py destroy
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

ADB_DEVICE_MODES = frozenset({"device", "recovery", "unauthorized"})
ADB_PAIRED_FLAGS = frozenset({"-H", "-P", "-s", "-t"})
ADB_FLAGS = frozenset({"-d", "-e"}) | ADB_PAIRED_FLAGS
ADB_SHELL_FLAGS = frozenset({"-T", "-n", "-t", "-x"})
ADB_SHELL_MODES = frozenset({"device", "recovery"})
ADB_UNAUTHORIZED_VERBS = frozenset({"exec-out", "get-state", "push", "reboot", "shell"})
BOOT0_SECTORS = 2048
BOOT_SECONDS = float(os.environ.get("FIREBREAK_SIM_BOOT_SECONDS", "3"))
BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
DISK_BYTES = 3917479936
FASTBOOT_FLAGS = frozenset({"-S", "-s"})
FASTBOOT_INTO = frozenset({"bootloader", "fastboot"})
FASTBOOT_REBOOTS = {
    "oem reboot-recovery": "recovery",
    "reboot": "system",
    "reboot bootloader": "bootloader",
    "reboot recovery": "recovery",
    "reboot-bootloader": "bootloader",
}
HERE = pathlib.Path(__file__).resolve().parent
IMAGE = "firebreak-sim"
LK_FIREOS5 = "f379dba-20170906_000423"
LK_FIREOS6 = "63cb91b-20221007_072309"
PATH = "/sim/path:/sim/bin:/usr/sbin:/usr/bin:/sbin:/bin"
SECTOR = 512
SERIAL = "G090SIM000000001"
STOCK_LK_SIZE = 241664
STOCK_TABLE = (
    ("kb", 2048, 2048),
    ("dkb", 4096, 2048),
    ("lk_a", 32768, 2048),
    ("tee1", 49152, 10240),
    ("lk_b", 65536, 2048),
    ("tee2", 81920, 10240),
    ("expdb", 98304, 20480),
    ("misc", 118784, 1025),
    ("persist", 131072, 32768),
    ("boot_a", 163840, 32768),
    ("boot_b", 196608, 32768),
    ("recovery", 229376, 32768),
    ("system_a", 294912, 1572864),
    ("system_b", 1867776, 1572864),
    ("cache", 3440640, 1605632),
    ("userdata", 5046272, 2605023),
)
TABLE_BACKUP_SECTORS = 33
TABLE_PRIMARY_SECTORS = 34
TWRPS = {"bboe": "3.7.0_9-bboe2", "v1": "3.2.3-0", "v2": "3.7.0_9-0"}
WAIT_FOR_ANY = frozenset({"any", "usb-device"})
WORK = pathlib.Path(
    os.environ.get("FIREBREAK_SIM") or pathlib.Path.home() / ".cache" / "firebreak-sim"
)
STATE = WORK / "state.json"
TRACE = WORK / "trace.jsonl"


def adb(*, arguments: list[str]) -> int:  # ruff: ignore[complex-structure, too-many-return-statements]
    while arguments and arguments[0] in ADB_FLAGS:
        arguments = arguments[2 if arguments[0] in ADB_PAIRED_FLAGS else 1 :]
    verb = arguments[0] if arguments else ""
    rest = arguments[1:]
    state = current()
    record(entry={"argv": arguments, "mode": state["mode"], "tool": "adb"})
    if verb == "version":
        print("Android Debug Bridge version 1.0.41\nVersion 37.0.0-sim")
        return 0
    if verb == "devices":
        print("List of devices attached")
        if state["mode"] in ADB_DEVICE_MODES:
            extra = " usb:1-1 product:biscuit model:AEOBC device:biscuit transport_id:1"
            print(f"{state['serial']}\t{state['mode']}{extra if '-l' in rest else ''}")
        print()
        return 0
    if verb.startswith("wait-for-"):
        wanted = verb[len("wait-for-") :]
        while state["mode"] != wanted and not (
            wanted in WAIT_FOR_ANY and state["mode"] in ADB_SHELL_MODES
        ):
            time.sleep(0.5)
            state = current()
        return 0
    if state["mode"] == "unauthorized" and verb in ADB_UNAUTHORIZED_VERBS:
        print("error: device unauthorized.", file=sys.stderr)
        return 1
    if state["mode"] not in ADB_SHELL_MODES:
        print("error: no devices/emulators found", file=sys.stderr)
        return 1
    if verb == "get-state":
        print(state["mode"])
        return 0
    if verb == "reboot":
        request_reboot(into=rest[0] if rest else "system")
        return 0
    if verb == "push":
        return push(local=pathlib.Path(rest[0]), remote=rest[1], state=state)
    if verb in {"exec-out", "shell"}:
        return shell(rest=rest, state=state, verb=verb)
    print(f"adb: unknown command {verb}", file=sys.stderr)
    return 1


def boot(*, into: str, state: dict) -> None:
    sim_boot(action="boot", state=state)
    spec = {
        "prefixes": {
            "lk_a": sorted({size for size, _ in state["known"]["lk"].values()}),
            "recovery": sorted({
                size for size, _ in state["known"]["recovery"].values()
            }),
        }
    }
    facts = json.loads(sim_boot(action="facts", spec=spec, state=state))
    outcome = decide(facts=facts, into=into, state=state)
    if outcome.get("consumed"):
        inside(
            command=f"dd if=/dev/zero of={BY_NAME}/{outcome['consumed']} bs=16"
            " count=1 conv=notrunc 2>/dev/null",
            state=state,
        )
    if "flavour" in outcome:
        sim_boot(
            action="enter",
            spec={
                "flavour": outcome["flavour"],
                "folders": ["/data/local/tmp", "/sdcard"],
                "props": outcome["props"],
            },
            state=state,
        )
    state.update(
        booting=None,
        exit_zero=outcome.get("exit_zero", False),
        mode=outcome["mode"],
        outcome=outcome,
        vars=outcome.get("vars", {}),
    )
    record(entry={"event": "boot", "into": into, "outcome": outcome})
    if outcome["mode"] == "bootrom":
        start_bootrom()


def build_prop(*, key: str, text: str | None) -> str:
    for line in (text or "").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1]
    return ""


def create(*, cache: pathlib.Path, start: str) -> None:
    WORK.mkdir(exist_ok=True, parents=True)
    TRACE.unlink(missing_ok=True)
    docker(arguments=["build", "-q", "-t", IMAGE, str(HERE)], capture_output=True)
    name = f"firebreak-sim-{uuid.uuid4().hex[:8]}"
    docker(
        arguments=["run", "-d", "--privileged", "--name", name, IMAGE],
        capture_output=True,
    )
    state = {
        "cache": str(cache),
        "container": name,
        "known": known_images(cache=cache),
        "mode": "none",
        "outcome": {},
        "serial": SERIAL,
        "vars": {},
    }
    save(state=state)
    disk_guid = uuid.uuid5(uuid.NAMESPACE_DNS, "firebreak-sim.disk")
    table = " ".join(
        f"-n {number}:{first}:{first + sectors - 1} -c {number}:{part}"
        f" -t {number}:8300"
        f" -u {number}:{uuid.uuid5(uuid.NAMESPACE_DNS, 'firebreak-sim.' + part)}"
        for number, (part, first, sectors) in enumerate(STOCK_TABLE, start=1)
    )
    inside(
        command="mkdir -p /sim/disk /sim/run"
        f" && truncate -s {DISK_BYTES} /sim/disk/mmcblk0.img"
        " && for s in boot0 boot1 rpmb; do truncate -s 1048576 /sim/disk/$s.img;"
        " done"
        f" && sgdisk -o -U {disk_guid} {table} /sim/disk/mmcblk0.img >/dev/null"
        " && echo a > /sim/run/active",
        state=state,
    )
    sim_boot(action="boot", state=state)
    stock = {
        "/dev/block/mmcblk0boot0": b"EMMC_BOOT\0SIM STOCK PRELOADER".ljust(
            262144, b"\x5a"
        ),
        "/dev/block/mmcblk0rpmb": stock_rpmb(),
        f"{BY_NAME}/lk_a": stock_lk(),
        f"{BY_NAME}/lk_b": stock_lk(),
        f"{BY_NAME}/recovery": b"ANDROID!SIM STOCK RECOVERY".ljust(1 << 20, b"\0"),
    }
    with tempfile.TemporaryDirectory() as folder:
        local = pathlib.Path(folder) / "image"
        for node, data in stock.items():
            local.write_bytes(data)
            write_image(local=local, node=node, state=state)
    inside(
        command="mkdir -p /sim/stock"
        " && printf 'ro.build.version.name=Fire OS 6.5.7.4 (stock 8146)\\n'"
        " > /sim/stock/build.prop"
        " && i=0 && for p in system_a userdata cache; do i=$((i + 1));"
        " E2FSPROGS_FAKE_TIME=1700000000 mke2fs -q -F -t ext4"
        " -U 5eed0000-0000-4000-8000-$(printf %012x $i)"
        " -E hash_seed=5eed0000-0000-4000-8000-000000000000"
        f" $( [ $p = system_a ] && echo -d /sim/stock ) {BY_NAME}/$p; done",
        state=state,
    )
    make_venv()
    if start == "no-light":
        inside(
            command="dd if=/dev/zero of=/dev/block/mmcblk0boot0 bs=512"
            f" count={BOOT0_SECTORS} 2>/dev/null",
            state=state,
        )
        record(entry={"event": "unplugged"})
    else:
        boot(into="bootloader" if start == "fastboot" else "system", state=state)
    save(state=state)
    print(f"{name}: {state['mode']}")


def current() -> dict:
    with locked():
        state = load()
        settle(state=state)
        return state


def decide(*, facts: dict, into: str, state: dict) -> dict:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    known = state["known"]
    lk = identify(prefixes=facts["prefixes"].get("lk_a", {}), table=known["lk"])
    none = {"mode": "none", "why": ""}
    if facts["boot0_empty"]:
        return {"mode": "bootrom", "why": "boot0 is empty"}
    if lk is None:
        return {**none, "why": "lk_a holds no LK this simulator knows"}
    description = LK_FIREOS5 if lk == "v1" else LK_FIREOS6
    marker = (lk == "v1" and facts.get("expdb_fastboot")) or (
        lk == "v2" and facts.get("misc_fastboot")
    )
    if into in FASTBOOT_INTO or marker:
        return {
            "consumed": "expdb" if lk == "v1" and facts.get("expdb_fastboot") else None,
            "lk": lk,
            "mode": "fastboot",
            "vars": {
                "lk_build_desc": description,
                "product": "BISCUIT",
                "unlock_status": "false" if lk == "stock" else "true",
            },
        }
    slot = facts["active"] or "a"
    if into == "recovery":
        if lk == "stock":
            return {**none, "why": "a locked LK refuses an unsigned recovery"}
        twrp = identify(
            prefixes=facts["prefixes"].get("recovery", {}), table=known["recovery"]
        )
        if twrp is None:
            return {**none, "why": "recovery holds no TWRP this simulator knows"}
        return {
            "flavour": "recovery-busybox" if twrp == "v1" else "recovery-toybox",
            "lk": lk,
            "mode": "recovery",
            "props": {
                "ro.boot.lk_build_desc": description,
                "ro.boot.slot_suffix": f"_{slot}",
                "ro.twrp.version": TWRPS[twrp],
                "sim.uid": "0",
                "sys.usb.config": "mtp,adb",
            },
            "twrp": twrp,
        }
    if lk == "v1":
        slot = "a"
    system = facts.get(f"system_{slot}") or {}
    version = build_prop(key="ro.build.version.name", text=system.get("build"))
    if version.startswith("Fire OS 5"):
        if lk != "v1":
            return {**none, "why": f"{lk}'s LK hangs booting a Fire OS 5 kernel"}
        if "if true; then" not in system.get("flags", ""):
            return {**none, "why": "Fire OS 5 booted with adb off"}
        return {
            "exit_zero": True,
            "flavour": "device",
            "lk": lk,
            "mode": "device",
            "props": {
                "ro.boot.lk_build_desc": description,
                "ro.boot.slot_suffix": f"_{slot}",
                "ro.build.version.name": version,
                "sim.su": "1" if facts["magisk"] else "0",
                "sim.uid": "2000",
                "sys.boot_completed": "1",
                "sys.usb.config": "mtp,adb",
            },
        }
    if version.startswith("Fire OS 6"):
        if lk == "v1":
            return {**none, "why": "amonet v1.1.0's LK does not boot Fire OS 6"}
        if lk == "v2" and facts.get(f"root_adb_{slot}"):
            return {
                "flavour": "device",
                "lk": lk,
                "mode": "device",
                "props": {
                    "ro.boot.lk_build_desc": description,
                    "ro.boot.slot_suffix": f"_{slot}",
                    "ro.build.version.name": version,
                    "sim.su": "0",
                    "sim.uid": "0",
                    "sys.boot_completed": "1",
                },
            }
        return {"lk": lk, "mode": "unauthorized"}
    return {**none, "why": f"system_{slot} holds no OS this simulator knows"}


def destroy() -> None:
    if not STATE.exists():
        return
    state = load()
    if state.get("bootrom_pid"):
        with contextlib.suppress(OSError):
            os.kill(state["bootrom_pid"], signal.SIGTERM)
    inside(
        check=False,
        command="for l in $(cat /sim/run/loops 2>/dev/null); do losetup -d $l; done",
        state=state,
    )
    docker(arguments=["rm", "-f", state["container"]], capture_output=True, check=False)
    STATE.unlink()


def docker(
    *, arguments: list[str], check: bool = True, **options: object
) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *arguments], check=check, **options)


def dump_table(*, path: pathlib.Path) -> None:
    state = current()
    skip = DISK_BYTES // SECTOR - TABLE_BACKUP_SECTORS
    inside(
        command="dd if=/sim/disk/mmcblk0.img bs=512"
        f" count={TABLE_PRIMARY_SECTORS} 2>/dev/null > /sim/run/table.bin"
        f" && dd if=/sim/disk/mmcblk0.img bs=512 skip={skip} 2>/dev/null"
        " >> /sim/run/table.bin",
        state=state,
    )
    docker(
        arguments=["cp", f"{state['container']}:/sim/run/table.bin", str(path)],
        capture_output=True,
    )


def erase(*, part: str, state: dict) -> int:
    node = "/dev/block/mmcblk0boot0" if part == "boot0" else f"{BY_NAME}/{part}"
    inside(
        command="echo 0 > /sys/block/mmcblk0boot0/force_ro;"
        f" dd if=/dev/zero of={node} bs=512 2>/dev/null; true",
        state=state,
    )
    print(f"Erasing '{part}' OKAY\nFinished. Total time: 0.050s")
    return 0


def fastboot(*, arguments: list[str]) -> int:  # ruff: ignore[complex-structure, too-many-return-statements]
    while arguments and arguments[0] in FASTBOOT_FLAGS:
        arguments = arguments[2:]
    verb = arguments[0] if arguments else ""
    rest = arguments[1:]
    if verb == "--help":
        print("usage: fastboot [OPTION...] COMMAND...")
        print(
            " -S SIZE[K|M|G]             Break into sparse files no larger than SIZE."
        )
        return 0
    state = current()
    record(entry={"argv": arguments, "mode": state["mode"], "tool": "fastboot"})
    if verb == "devices":
        if state["mode"] == "fastboot":
            print(f"{state['serial']}\tfastboot")
        return 0
    while state["mode"] != "fastboot":
        time.sleep(0.5)
        state = current()
    if verb == "getvar":
        name = rest[0]
        if name in state["vars"]:
            print(f"{name}: {state['vars'][name]}\nFinished. Total time: 0.001s")
            return 0
        print(f"getvar:{name} FAILED (remote: 'GetVar Variable Not found')")
        return 1
    if verb == "flash":
        return flash(image=rest[1], part=rest[0], state=state)
    if verb == "erase":
        return erase(part=rest[0], state=state)
    into = FASTBOOT_REBOOTS.get(" ".join(arguments))
    if into:
        request_reboot(into=into)
        print("Rebooting OKAY\nFinished. Total time: 0.001s")
        return 0
    print(f"fastboot: unknown command {verb}", file=sys.stderr)
    return 1


def fastbrick(*, image: str, state: dict) -> int:
    description = state["vars"].get("lk_build_desc", "")
    wanted = "fastbrick-20221007.img" if description == LK_FIREOS6 else "fastbrick.img"
    if pathlib.Path(image).name != wanted:
        print(
            "Sending 'brick' OKAY\nWriting 'brick' FAILED (remote: 'unknown partition')"
        )
        return 1
    cache = pathlib.Path(state["cache"])
    with (
        zipfile.ZipFile(cache / "amonet-biscuit-v2.0.0.zip") as v2,
        tempfile.TemporaryDirectory() as folder,
    ):
        for target, suffix in (
            ("lk_a", "bin/lk.bin"),
            ("lk_b", "bin/lk.bin"),
            ("tee2", "bin/tz.img"),
            ("tee1", "bin/tee-payload.bin"),
            ("expdb", "bin/biscuit-kaeru.bin"),
            ("recovery", "bin/twrp.img"),
        ):
            local = pathlib.Path(folder) / target
            local.write_bytes(member(archive=v2, suffix=suffix))
            write_image(local=local, node=f"{BY_NAME}/{target}", state=state)
    request_reboot(delay=BOOT_SECONDS + 2, into="recovery")
    print("Sending sparse 'brick' 1/1 (16 KB)", flush=True)
    time.sleep(3600)
    return 0


def flash(*, image: str, part: str, state: dict) -> int:
    if part == "brick":
        return fastbrick(image=image, state=state)
    if state["vars"]["unlock_status"] != "true":
        print(
            f"Sending '{part}' OKAY\nWriting '{part}' FAILED (remote: 'not allowed in"
            " locked state')"
        )
        return 1
    write_image(local=pathlib.Path(image), node=f"{BY_NAME}/{part}", state=state)
    print(f"Sending '{part}' OKAY\nWriting '{part}' OKAY\nFinished. Total time: 0.100s")
    return 0


def identify(*, prefixes: dict, table: dict) -> str | None:
    for name, (size, digest) in table.items():
        if prefixes.get(str(size)) == digest:
            return name
    return None


def inside(*, check: bool = True, command: str, state: dict) -> str:
    return docker(
        arguments=[
            "exec",
            "-e",
            f"PATH={PATH}",
            state["container"],
            "/bin/sh",
            "-c",
            command,
        ],
        capture_output=True,
        check=check,
        text=True,
    ).stdout


def known_images(*, cache: pathlib.Path) -> dict:
    with (
        zipfile.ZipFile(cache / "amonet-biscuit-v1.1.0.zip") as v1,
        zipfile.ZipFile(cache / "amonet-biscuit-v2.0.0.zip") as v2,
    ):
        lks = {
            "v1": member(archive=v1, suffix="bin/lk.bin"),
            "v2": member(archive=v2, suffix="bin/lk.bin"),
        }
        recoveries = {
            "bboe": (cache / "twrp-3.7.0_9-bboe2-biscuit.img").read_bytes(),
            "v1": member(archive=v1, suffix="bin/twrp.img"),
            "v2": member(archive=v2, suffix="bin/twrp.img"),
        }
    lks["stock"] = stock_lk()
    return {
        "lk": {name: [len(data), md5(data=data)] for name, data in lks.items()},
        "recovery": {
            name: [len(data), md5(data=data)] for name, data in recoveries.items()
        },
    }


def load() -> dict:
    return json.loads(STATE.read_text())


@contextlib.contextmanager
def locked() -> Generator[None, None, None]:
    WORK.mkdir(exist_ok=True, parents=True)
    with (WORK / "lock").open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def main() -> int:
    if sys.argv[1:2] == ["adb"]:
        return adb(arguments=sys.argv[2:])
    if sys.argv[1:2] == ["fastboot"]:
        return fastboot(arguments=sys.argv[2:])
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="action", required=True)
    made = commands.add_parser("create")
    made.add_argument(
        "--cache", default=str(pathlib.Path.home() / ".cache" / "firebreak")
    )
    made.add_argument(
        "--start", choices=("fastboot", "no-light", "stock-booted"), default="fastboot"
    )
    commands.add_parser("destroy")
    commands.add_parser("plug")
    commands.add_parser("snapshot")
    commands.add_parser("status")
    table = commands.add_parser("table")
    table.add_argument("path", type=pathlib.Path)
    options = parser.parse_args()
    if options.action == "create":
        destroy()
        create(cache=pathlib.Path(options.cache), start=options.start)
    elif options.action == "destroy":
        destroy()
    elif options.action == "plug":
        plug()
    elif options.action == "snapshot":
        print(sim_boot(action="snapshot", state=current()), end="")
    elif options.action == "status":
        state = current()
        shown = {key: state[key] for key in ("container", "mode", "outcome")}
        print(json.dumps(shown, indent=1))
    elif options.action == "table":
        dump_table(path=options.path)
    return 0


def make_venv() -> None:
    venv = WORK / "venv"
    python = venv / "bin" / "python"
    if not python.exists():
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True
        )
    packages = pathlib.Path(
        subprocess.run(
            [
                str(python),
                "-c",
                "import sysconfig; print(sysconfig.get_paths()['purelib'])",
            ],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.strip()
    )
    (packages / "firebreak_sim_ports.py").write_text((HERE / "ports.py").read_text())
    (packages / "firebreak_sim_ports.pth").write_text("import firebreak_sim_ports\n")


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def member(*, archive: zipfile.ZipFile, suffix: str) -> bytes:
    for name in archive.namelist():
        if name.endswith(suffix):
            return archive.read(name)
    raise KeyError(suffix)


def plug() -> None:
    with locked():
        state = load()
        if state["mode"] == "none" and not state.get("booting"):
            boot(into="system", state=state)
            save(state=state)
        print(state["mode"])


def push(*, local: pathlib.Path, remote: str, state: dict) -> int:
    if remote.endswith("/"):
        remote += local.name
    copied = docker(
        arguments=["cp", "-L", str(local), f"{state['container']}:{remote}"],
        capture_output=True,
        check=False,
    )
    if copied.returncode:
        print(
            f"adb: error: failed to copy '{local}' to '{remote}': remote couldn't"
            " create file"
        )
        return 1
    size = local.stat().st_size
    record(
        entry={"event": "pushed", "md5": md5(data=local.read_bytes()), "remote": remote}
    )
    print(f"{local}: 1 file pushed, 0 skipped. 40.0 MB/s ({size} bytes in 0.010s)")
    return 0


def reboot(*, delay: float = BOOT_SECONDS, into: str, state: dict) -> None:
    state.update(booting={"at": time.time() + delay, "into": into}, mode="none")
    record(entry={"event": "reboot", "into": into})


def reboot_requested(*, state: dict) -> str | None:
    said = inside(
        check=False,
        command="cat /sim/run/request 2>/dev/null && rm -f /sim/run/request",
        state=state,
    ).strip()
    return said or None


def record(*, entry: dict) -> None:
    with TRACE.open("a") as trace:
        trace.write(json.dumps({"time": round(time.time(), 3), **entry}) + "\n")


def request_reboot(*, delay: float = BOOT_SECONDS, into: str) -> None:
    with locked():
        state = load()
        reboot(delay=delay, into=into, state=state)
        save(state=state)


def save(*, state: dict) -> None:
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=1, sort_keys=True))
    temporary.replace(STATE)


def settle(*, state: dict) -> dict:
    booting = state.get("booting")
    if booting and time.time() >= booting["at"]:
        boot(into=booting["into"], state=state)
        save(state=state)
    return state


def shell(*, rest: list[str], state: dict, verb: str) -> int:
    interactive = verb == "shell" and "-n" not in rest
    command = " ".join(word for word in rest if word not in ADB_SHELL_FLAGS)
    environment = ["-e", f"PATH={PATH}"]
    if state["outcome"].get("props", {}).get("sim.uid") == "0":
        environment += ["-e", "SIM_UID=0"]
    result = docker(
        arguments=[
            "exec",
            *(["-i"] if interactive else []),
            *environment,
            state["container"],
            "/bin/busybox",
            "sh",
            "-c",
            command,
        ],
        check=False,
        stderr=subprocess.STDOUT,
        stdin=None if interactive else subprocess.DEVNULL,
    )
    requested = reboot_requested(state=state)
    if requested:
        request_reboot(into=requested)
    return 0 if state.get("exit_zero") and verb == "shell" else result.returncode


def sim_boot(*, action: str, spec: dict | None = None, state: dict) -> str:
    arguments = ["exec", state["container"], "/sim/bin/sim-boot", action]
    if spec is not None:
        arguments.append(json.dumps(spec))
    return docker(arguments=arguments, capture_output=True, text=True).stdout


def start_bootrom() -> None:
    with (WORK / "bootrom.log").open("a") as log:
        subprocess.Popen(
            [sys.executable, str(HERE / "bootrom.py")],
            start_new_session=True,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            stdout=log,
        )


def stock_lk() -> bytes:
    return (b"SIM STOCK LK " + LK_FIREOS6.encode()).ljust(STOCK_LK_SIZE, b"\xa5")


def stock_rpmb() -> bytes:
    return b"AMZN" + hashlib.sha256(b"firebreak-sim.rpmb").digest() * 7 + bytes(28)


def write_image(*, local: pathlib.Path, node: str, seek: int = 0, state: dict) -> None:
    docker(
        arguments=["cp", "-L", str(local), f"{state['container']}:/sim/upload"],
        capture_output=True,
    )
    inside(
        command=f"dd if=/sim/upload of={node} bs=512 seek={seek} conv=notrunc,fsync"
        " 2>/dev/null; rm -f /sim/upload",
        state=state,
    )


if __name__ == "__main__":
    sys.exit(main())
