"""Simulate an Echo Dot (2nd Generation), or an Echo (2nd Generation), for
firebreak.

python3 simulator/dot.py create [--cache DIR] [--device biscuit|radar] [--runner PID]
    [--start fastboot|no-light|stock-booted|twrp]
python3 simulator/dot.py plug
python3 simulator/dot.py status
python3 simulator/dot.py snapshot
python3 simulator/dot.py table FILE
python3 simulator/dot.py halt
python3 simulator/dot.py destroy
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import select
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from hashlib import _Hash as Hash
    from typing import BinaryIO

try:
    from firebreak_sim_ports import busy
except ImportError:
    busy = contextlib.nullcontext

ADB_DEVICE_MODES = frozenset({"device", "recovery", "unauthorized"})
ADB_PAIRED_FLAGS = frozenset({"-H", "-P", "-s", "-t"})
ADB_FLAGS = frozenset({"-d", "-e"}) | ADB_PAIRED_FLAGS
ADB_SHELL_MODES = frozenset({"device", "recovery"})
ADB_SHELL_OPTIONS = frozenset("ntTx")
ADB_UNAUTHORIZED_VERBS = frozenset({"exec-out", "get-state", "push", "reboot", "shell"})
BOOT0_SECTORS = 2048
BOOT_SECONDS = float(os.environ.get("FIREBREAK_SIM_BOOT_SECONDS", "3"))
BY_NAME = "/dev/block/platform/mtk-msdc.0/by-name"
DETACH_SHELL = "mkdir -p /sim/run && cat > /sim/run/loops && /sim/bin/sim-boot detach"
DEVICES = {
    "biscuit": {
        "amonet": "amonet-biscuit-v2.0.0.zip",
        "fastbricks": {"63cb91b-20221007_072309": "fastbrick-20221007.img"},
        "kaeru": "bin/biscuit-kaeru.bin",
        "model": "AEOBC",
        "stock": "Fire OS 6.5.7.4 (stock 8146)",
        "stock_lk": "63cb91b-20221007_072309",
        "v2_lk": "63cb91b-20221007_072309",
    },
    "radar": {
        "amonet": "amonet-radar-v1.0.0.zip",
        "fastbricks": {"59779ca-20220524_183401": "fastbrick-20220524.img"},
        "kaeru": "bin/radar-kaeru.bin",
        "model": "AEORD",
        "stock": "Fire OS 6.5.7.2 (stock 6436)",
        "stock_lk": "63cb91b-20221007_073612",
        "v2_lk": "59779ca-20220524_183401",
    },
}
DISK_BYTES = 3917479936
DOWNLOAD_SUFFIXES = frozenset({".bin", ".img", ".whl", ".zip"})
FASTBOOT_FLAGS = frozenset({"-S", "-s"})
FASTBOOT_INTO = frozenset({"bootloader", "fastboot"})
FASTBOOT_REBOOTS = {
    "oem reboot-recovery": "recovery",
    "reboot": "system",
    "reboot bootloader": "bootloader",
    "reboot recovery": "recovery",
    "reboot-bootloader": "bootloader",
}
FASTBOOT_SPARSE_UNITS = {"G": 1 << 30, "K": 1 << 10, "M": 1 << 20}
HALT_SECONDS = 10
HERE = pathlib.Path(__file__).resolve().parent
IMAGE = "firebreak-sim"
INSIDE_PATH = "/sim/bin:/usr/sbin:/usr/bin:/sbin:/bin"
LEGACY_SERVICE_BYTES = 4096
LK_FIREOS5 = "f379dba-20170906_000423"
LOCKED = "the command you input is restricted on locked hw"
MTP_PROPS = ("ro.twrp.version", "sys.usb.config")
PUSH_SHELL = 'cat > "$1" && { [ "$2" = 0 ] || chmod 666 "$1"; }'
SECTOR = 512
SERIAL = "G090SIM000000001"
SHELL_UID = 2000
SIDE_PARTITIONS = frozenset({"boot0", "boot1"})
SIM_CACHE = pathlib.Path(
    os.environ.get("FIREBREAK_SIM_CACHE")
    or pathlib.Path.home() / ".cache" / "firebreak-sim-cache"
)
STARTS = {"fastboot": "bootloader", "stock-booted": "system", "twrp": "recovery"}
STDIN_CHUNK = 1 << 20
STDIN_POLL_SECONDS = 0.1
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
TOOL_CACHE = "firebreak"
TWRPS = {"bboe": "3.7.0_9-bboe2", "v1": "3.2.3-0", "v2": "3.7.0_9-0"}
USB_CUT_STATUS = 255
USB_DROP_SECONDS = 1.0
USB_SWITCH_SECONDS = 5.0
WAIT_FOR_ANY = frozenset({"any", "usb-device"})
WORK = pathlib.Path(
    os.environ.get("FIREBREAK_SIM") or pathlib.Path.home() / ".cache" / "firebreak-sim"
)
CLOCK = WORK / "clock.json"
STATE = WORK / "state.json"
TRACE = WORK / "trace.jsonl"


def adb(*, arguments: list[str]) -> int:  # ruff: ignore[complex-structure, too-many-branches, too-many-return-statements]
    entry = {"argv": arguments, "tool": "adb"}
    while arguments and arguments[0] in ADB_FLAGS:
        arguments = arguments[2 if arguments[0] in ADB_PAIRED_FLAGS else 1 :]
    verb = arguments[0] if arguments else ""
    rest = arguments[1:]
    state = current()
    entry["mode"] = state["mode"]
    if verb == "push" and rest and pathlib.Path(rest[0]).is_file():
        entry["md5"] = md5(data=pathlib.Path(rest[0]).read_bytes())
    record(entry=entry)
    if verb == "version":
        print("Android Debug Bridge version 1.0.41\nVersion 37.0.0-sim")
        return 0
    if verb == "devices":
        print("List of devices attached")
        if seen(state=state) in ADB_DEVICE_MODES:
            device = state["device"]
            extra = (
                f" usb:1-1 product:{device} model:{DEVICES[device]['model']}"
                f" device:{device} transport_id:1"
            )
            print(f"{state['serial']}\t{state['mode']}{extra if '-l' in rest else ''}")
        print()
        return 0
    if verb.startswith("wait-for-"):
        wanted = verb[len("wait-for-") :]
        while seen(state=state) != wanted and not (
            wanted in WAIT_FOR_ANY and seen(state=state) in ADB_SHELL_MODES
        ):
            time.sleep(0.5)
            state = current()
        return 0
    if state["mode"] == "unauthorized" and verb in ADB_UNAUTHORIZED_VERBS:
        print("error: device unauthorized.", file=sys.stderr)
        return 1
    if seen(state=state) not in ADB_SHELL_MODES:
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
        return shell(entry=entry, rest=rest, state=state, verb=verb)
    print(f"adb: unknown command {verb}", file=sys.stderr)
    return 1


def boot(*, into: str, state: dict) -> None:
    sim_boot(action="boot", state=state)
    known = state["known"]
    known["lk"]["stock"] = stock_lks(device=state["device"])
    spec = {
        "prefixes": {
            "lk_a": sizes(table=known["lk"]),
            "recovery": sizes(table=known["recovery"]),
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
    props = dict(outcome.get("props", {}))
    later = {}
    if outcome["mode"] == "recovery":
        later = {key: props.pop(key) for key in MTP_PROPS}
        props["sys.usb.config"] = "adb"
    if "flavour" in outcome:
        sim_boot(
            action="enter",
            spec={
                "flavour": outcome["flavour"],
                "props": props,
                "twrp": outcome.get("twrp"),
                "uid": outcome["uid"],
            },
            state=state,
        )
    switch = time.time() + USB_SWITCH_SECONDS
    state.update(
        booting=None,
        mode=outcome["mode"],
        outcome=outcome,
        shell_protocol=outcome.get("shell_protocol", True),
        usb={"at": switch, "props": later, "until": switch + USB_DROP_SECONDS}
        if later
        else None,
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


def clone(*, source: pathlib.Path, target: pathlib.Path) -> None:
    if sys.platform != "darwin":
        subprocess.run(["cp", "--reflink=auto", str(source), str(target)], check=True)
        return
    if subprocess.run(
        ["cp", "-c", str(source), str(target)], capture_output=True, check=False
    ).returncode:
        target.unlink(missing_ok=True)
        shutil.copyfile(source, target)


def create(*, cache: pathlib.Path, device: str, runner: int, start: str) -> None:
    if device != "biscuit" and start == "no-light":
        message = (
            f"a {device} cannot start with no light: bootrom.py knows only"
            " biscuit's payloads"
        )
        raise SystemExit(message)
    refuse_real_caches()
    previous = load().get("runner") if STATE.exists() else None
    if previous and previous != runner and is_runner(pid=previous):
        message = f"run.sh (pid {previous}) still runs this Dot in {WORK}"
        raise SystemExit(message)
    destroy()
    WORK.mkdir(exist_ok=True, parents=True)
    CLOCK.unlink(missing_ok=True)
    TRACE.unlink(missing_ok=True)
    docker(arguments=["build", "-q", "-t", IMAGE, str(HERE)], capture_output=True)
    name = f"firebreak-sim-{uuid.uuid4().hex[:8]}"
    state = {
        "cache": str(cache),
        "container": name,
        "device": device,
        "known": known_images(cache=cache, device=device),
        "mode": "none",
        "outcome": {},
        "runner": runner,
        "serial": SERIAL,
        "vars": {},
    }
    save(state=state)
    docker(
        arguments=[
            "run",
            "-d",
            "--init",
            "--network",
            "none",
            "--privileged",
            "--name",
            name,
            IMAGE,
        ],
        capture_output=True,
    )
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
        "/dev/block/mmcblk0boot0": (
            b"EMMC_BOOT".ljust(SECTOR, b"\0") + b"BRLYT\0SIM STOCK PRELOADER"
        ).ljust(262144, b"\x5a"),
        "/dev/block/mmcblk0rpmb": stock_rpmb(),
        f"{BY_NAME}/lk_a": stock_lk(device=device),
        f"{BY_NAME}/lk_b": stock_lk(device=device),
        f"{BY_NAME}/recovery": b"ANDROID!SIM STOCK RECOVERY".ljust(1 << 20, b"\0"),
    }
    with tempfile.TemporaryDirectory() as folder:
        local = pathlib.Path(folder) / "image"
        for node, data in stock.items():
            local.write_bytes(data)
            write_image(local=local, node=node, state=state)
    inside(
        command="mkdir -p /sim/stock"
        f" && printf 'ro.build.version.name={DEVICES[device]['stock']}\\n'"
        " > /sim/stock/build.prop"
        " && i=0 && for p in system_a userdata cache; do i=$((i + 1));"
        " E2FSPROGS_FAKE_TIME=1700000000 mke2fs -q -F -t ext4"
        " -U 5eed0000-0000-4000-8000-$(printf %012x $i)"
        " -E hash_seed=5eed0000-0000-4000-8000-000000000000"
        f" $( [ $p = system_a ] && echo -d /sim/stock ) {BY_NAME}/$p; done",
        state=state,
    )
    make_venv()
    link_downloads(cache=cache)
    if start == "no-light":
        inside(
            command="blockdev --setrw /dev/block/mmcblk0boot0 && dd if=/dev/zero"
            f" of=/dev/block/mmcblk0boot0 bs=512 count={BOOT0_SECTORS} 2>/dev/null"
            + protect(node="/dev/block/mmcblk0boot0"),
            state=state,
        )
        record(entry={"event": "unplugged"})
    else:
        if start == "twrp":
            write_amonet_v2(state=state)
        boot(into=STARTS[start], state=state)
    save(state=state)
    print(f"{name}: {state['mode']}")


def current() -> dict:
    with locked():
        state = load()
        settle(state=state)
        return state


def decide(*, facts: dict, into: str, state: dict) -> dict:  # ruff: ignore[complex-structure, too-many-return-statements, too-many-branches]
    device = state["device"]
    spec = DEVICES[device]
    known = state["known"]
    lk = identify(prefixes=facts["prefixes"].get("lk_a", {}), table=known["lk"])
    none = {"mode": "none", "why": ""}
    if not facts["preloader"]:
        return {"mode": "bootrom", "why": "boot0 holds no preloader"}
    if lk is None:
        return {**none, "why": "lk_a holds no LK this simulator knows"}
    description = {"stock": spec["stock_lk"], "v1": LK_FIREOS5}.get(lk, spec["v2_lk"])
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
                "product": device.upper(),
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
            "flavour": "twrp-3.2.3" if twrp == "v1" else "twrp-3.7.0",
            "lk": lk,
            "mode": "recovery",
            "props": {
                "ro.boot.lk_build_desc": description,
                "ro.boot.slot_suffix": f"_{slot}",
                "ro.product.device": device,
                "ro.twrp.version": TWRPS[twrp],
                "sys.usb.config": "mtp,adb",
            },
            "shell_protocol": twrp != "v1",
            "twrp": twrp,
            "uid": 0,
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
            "flavour": "fire-os-5",
            "lk": lk,
            "mode": "device",
            "props": {
                "ro.boot.lk_build_desc": description,
                "ro.boot.slot_suffix": f"_{slot}",
                "ro.build.version.name": version,
                "ro.product.device": device,
                "sim.su": "1" if facts["magisk"] else "0",
                "sys.boot_completed": "1",
                "sys.usb.config": "mtp,adb",
            },
            "shell_protocol": False,
            "uid": SHELL_UID,
        }
    if version.startswith("Fire OS 6"):
        if lk == "v1":
            return {**none, "why": "amonet v1.1.0's LK does not boot Fire OS 6"}
        if lk == "v2" and facts.get(f"root_adb_{slot}"):
            return {
                "flavour": "fire-os-6",
                "lk": lk,
                "mode": "device",
                "props": {
                    "ro.boot.lk_build_desc": description,
                    "ro.boot.slot_suffix": f"_{slot}",
                    "ro.build.version.name": version,
                    "ro.product.device": device,
                    "sim.su": "0",
                    "sys.boot_completed": "1",
                },
                "uid": 0,
            }
        return {"lk": lk, "mode": "unauthorized"}
    return {**none, "why": f"system_{slot} holds no OS this simulator knows"}


def destroy() -> None:
    halt()
    with locked():
        if not STATE.exists():
            return
        state = load()
        pid = state.get("bootrom_pid")
        if pid and is_bootrom(pid=pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        detach_loops(container=state["container"])
        docker(
            arguments=["rm", "-f", state["container"]], capture_output=True, check=False
        )
        STATE.unlink()


def detach_loops(*, container: str) -> None:
    running = docker(
        arguments=["inspect", "-f", "{{.State.Running}}", container],
        capture_output=True,
        check=False,
        text=True,
    )
    if running.returncode:
        warn(
            text=f"container {container} is gone, so its loop devices could not be"
            " detached. losetup -a in a privileged container lists them."
        )
        return
    if running.stdout.strip() != "true":
        docker(arguments=["start", container], capture_output=True, check=False)
    detached = docker(
        arguments=["exec", container, "/sim/bin/sim-boot", "detach"],
        capture_output=True,
        check=False,
        text=True,
    )
    if not detached.returncode:
        return
    with tempfile.TemporaryDirectory() as folder:
        records = pathlib.Path(folder) / "loops"
        copied = docker(
            arguments=["cp", f"{container}:/sim/run/loops", str(records)],
            capture_output=True,
            check=False,
        )
        if copied.returncode:
            warn(
                text=f"the loop records of container {container} could not be read"
                f" ({detached.stderr.strip()}). losetup -a in a privileged container"
                " lists the loops."
            )
            return
        with records.open("rb") as source:
            helped = docker(
                arguments=[
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    "none",
                    "--privileged",
                    IMAGE,
                    "/bin/sh",
                    "-c",
                    DETACH_SHELL,
                ],
                capture_output=True,
                check=False,
                stdin=source,
                text=True,
            )
        if helped.returncode:
            warn(
                text=f"the loop devices of container {container} are still attached"
                f" ({helped.stderr.strip() or detached.stderr.strip()}). Records:"
                f" {'; '.join(records.read_text().splitlines())}"
            )


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
    if state["vars"]["unlock_status"] != "true":
        print(f"Erasing '{part}' FAILED (remote: '{LOCKED}')")
        return 1
    node = partition_node(part=part)
    size = partition_bytes(node=node, state=state)
    if size is None:
        print(f"Erasing '{part}' FAILED (remote: 'unknown partition')")
        return 1
    inside(
        command=f"blockdev --setrw {node} && dd if=/dev/zero of={node} bs=512"
        f" count={size // SECTOR} 2>/dev/null{protect(node=node)}",
        state=state,
    )
    print(f"Erasing '{part}' OKAY\nFinished. Total time: 0.050s")
    return 0


def fastboot(*, arguments: list[str]) -> int:  # ruff: ignore[complex-structure, too-many-return-statements]
    entry = {"argv": arguments, "tool": "fastboot"}
    sparse = None
    while arguments and arguments[0] in FASTBOOT_FLAGS:
        if arguments[0] == "-S" and len(arguments) > 1:
            sparse = sparse_bytes(text=arguments[1])
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
    entry["mode"] = state["mode"]
    if verb == "flash" and len(rest) > 1 and pathlib.Path(rest[1]).is_file():
        entry["md5"] = md5(data=pathlib.Path(rest[1]).read_bytes())
    record(entry=entry)
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
        return flash(image=rest[1], part=rest[0], sparse=sparse, state=state)
    if verb == "erase":
        return erase(part=rest[0], state=state)
    into = FASTBOOT_REBOOTS.get(" ".join(arguments))
    if into:
        request_reboot(into=into)
        print("Rebooting OKAY\nFinished. Total time: 0.001s")
        return 0
    print(f"fastboot: unknown command {verb}", file=sys.stderr)
    return 1


def fastbrick(*, image: str, sparse: int | None, state: dict) -> int:
    spec = DEVICES[state["device"]]
    description = state["vars"].get("lk_build_desc", "")
    wanted = spec["fastbricks"].get(description, "fastbrick.img")
    if pathlib.Path(image).name != wanted:
        print(
            "Sending 'brick' OKAY\nWriting 'brick' FAILED (remote: 'unknown partition')"
        )
        return 1
    write_amonet_v2(state=state)
    request_reboot(delay=BOOT_SECONDS + 2, into="recovery")
    print(sending(image=pathlib.Path(image), part="brick", sparse=sparse), flush=True)
    time.sleep(3600)
    return 0


def flash(*, image: str, part: str, sparse: int | None, state: dict) -> int:
    if part == "brick":
        return fastbrick(image=image, sparse=sparse, state=state)
    node = partition_node(part=part)
    size = partition_bytes(node=node, state=state)
    refusal = (
        LOCKED
        if state["vars"]["unlock_status"] != "true"
        else "unknown partition"
        if size is None
        else "size too large"
        if pathlib.Path(image).stat().st_size > size
        else None
    )
    said = sending(image=pathlib.Path(image), part=part, sparse=sparse)
    if refusal:
        print(f"{said} OKAY\nWriting '{part}' FAILED (remote: '{refusal}')")
        return 1
    write_image(local=pathlib.Path(image), node=node, state=state)
    print(f"{said} OKAY\nWriting '{part}' OKAY\nFinished. Total time: 0.100s")
    return 0


def halt() -> None:
    if not STATE.exists():
        return
    pid = load().get("bootrom_pid")
    if not pid:
        return
    if not is_bootrom(pid=pid):
        with locked():
            state = load()
            if state.get("bootrom_pid") == pid:
                state.pop("bootrom_pid", None)
                state.pop("port", None)
                save(state=state)
        return
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + HALT_SECONDS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.1)


def identify(*, prefixes: dict, table: dict) -> str | None:
    for name, images in table.items():
        for size, digest in images:
            if prefixes.get(str(size)) == digest:
                return name
    return None


def identity(*, path: pathlib.Path) -> tuple[int, int] | None:
    try:
        status = path.stat()
    except OSError:
        return None
    return status.st_dev, status.st_ino


def inside(*, check: bool = True, command: str, state: dict) -> str:
    return docker(
        arguments=[
            "exec",
            "-e",
            f"PATH={INSIDE_PATH}",
            state["container"],
            "/bin/sh",
            "-c",
            command,
        ],
        capture_output=True,
        check=check,
        text=True,
    ).stdout


def is_bootrom(*, pid: int) -> bool:
    said = subprocess.run(
        ["ps", "-ww", "-o", "args=", "-p", str(pid)],
        capture_output=True,
        check=False,
        text=True,
    ).stdout.strip()
    return said.endswith(f"{HERE / 'bootrom.py'} {WORK}")


def is_runner(*, pid: int) -> bool:
    said = subprocess.run(
        ["ps", "-ww", "-o", "args=", "-p", str(pid)],
        capture_output=True,
        check=False,
        text=True,
    ).stdout.split()
    return any(pathlib.Path(word).name == "run.sh" for word in said)


def known_images(*, cache: pathlib.Path, device: str) -> dict:
    with zipfile.ZipFile(cache / DEVICES[device]["amonet"]) as v2:
        lks = {"v2": [member(archive=v2, suffix="bin/lk.bin")]}
        recoveries = {"v2": [member(archive=v2, suffix="bin/twrp.img")]}
    if device == "biscuit":
        with zipfile.ZipFile(cache / "amonet-biscuit-v1.1.0.zip") as v1:
            lks["v1"] = [member(archive=v1, suffix="bin/lk.bin")]
            recoveries["v1"] = [member(archive=v1, suffix="bin/twrp.img")]
        recoveries["bboe"] = [(cache / "twrp-3.7.0_9-bboe2-biscuit.img").read_bytes()]
    lks["stock"] = [stock_lk(device=device)]
    return {
        "lk": {name: measured(images=images) for name, images in lks.items()},
        "recovery": {
            name: measured(images=images) for name, images in recoveries.items()
        },
    }


def link_downloads(*, cache: pathlib.Path) -> None:
    for download in sorted(cache.iterdir()):
        if not (download.is_file() and download.suffix in DOWNLOAD_SUFFIXES):
            continue
        copy = SIM_CACHE / TOOL_CACHE / download.name
        if copy.is_symlink():
            copy.unlink()
        source = download.stat()
        if copy.exists() and (copy.stat().st_size, copy.stat().st_mtime_ns) == (
            source.st_size,
            source.st_mtime_ns,
        ):
            continue
        copy.unlink(missing_ok=True)
        clone(source=download, target=copy)
        os.utime(copy, ns=(source.st_atime_ns, source.st_mtime_ns))


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
    made.add_argument("--device", choices=sorted(DEVICES), default="biscuit")
    made.add_argument("--runner", default=0, type=int)
    made.add_argument(
        "--start",
        choices=("fastboot", "no-light", "stock-booted", "twrp"),
        default="fastboot",
    )
    commands.add_parser("destroy")
    commands.add_parser("halt")
    commands.add_parser("plug")
    commands.add_parser("snapshot")
    commands.add_parser("status")
    table = commands.add_parser("table")
    table.add_argument("path", type=pathlib.Path)
    options = parser.parse_args()
    if options.action == "create":
        create(
            cache=pathlib.Path(options.cache),
            device=options.device,
            runner=options.runner,
            start=options.start,
        )
    elif options.action == "destroy":
        destroy()
    elif options.action == "halt":
        halt()
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


def measured(*, images: list[bytes]) -> list[list]:
    return [[len(data), md5(data=data)] for data in images]


def member(*, archive: zipfile.ZipFile, suffix: str) -> bytes:
    for name in archive.namelist():
        if name.endswith(suffix):
            return archive.read(name)
    raise KeyError(suffix)


def partition_bytes(*, node: str, state: dict) -> int | None:
    said = inside(
        check=False,
        command=f"[ -b {node} ] && blockdev --getsize64 {node}",
        state=state,
    ).strip()
    return int(said) if said.isdigit() else None


def partition_node(*, part: str) -> str:
    if part in SIDE_PARTITIONS:
        return f"/dev/block/mmcblk0{part}"
    return f"{BY_NAME}/{part}"


def plug() -> None:
    with locked():
        state = load()
        if state["mode"] == "none" and not state.get("booting"):
            boot(into="system", state=state)
            save(state=state)
        print(state["mode"])


def protect(*, node: str) -> str:
    if node.removeprefix("/dev/block/mmcblk0") in SIDE_PARTITIONS:
        return f"; blockdev --setro {node}"
    return ""


def push(*, local: pathlib.Path, remote: str, state: dict) -> int:
    if remote.endswith("/"):
        remote += local.name
    started = time.time()
    with local.open("rb") as source:
        copied = docker(
            arguments=[
                "exec",
                "-i",
                "-u",
                user(state=state),
                state["container"],
                "/bin/sh",
                "-c",
                PUSH_SHELL,
                "push",
                remote,
                str(state["outcome"]["uid"]),
            ],
            capture_output=True,
            check=False,
            stdin=source,
        )
    if copied.returncode:
        print(
            f"adb: error: failed to copy '{local}' to '{remote}': remote couldn't"
            " create file: Permission denied"
        )
        return 1
    if switched_during(started=started, state=state):
        inside(command=f"rm -f {shlex.quote(remote)}", state=state)
        record(
            entry={
                "call": {"argv": ["push", str(local), remote], "tool": "adb"},
                "event": "cut",
            }
        )
        print(f"adb: error: failed to read copy response: EOF\n{local}: 0 files pushed")
        return 1
    size = local.stat().st_size
    print(f"{local}: 1 file pushed, 0 skipped. 40.0 MB/s ({size} bytes in 0.010s)")
    return 0


def reboot(*, delay: float = BOOT_SECONDS, into: str, state: dict) -> None:
    state.update(booting={"at": time.time() + delay, "into": into}, mode="none")
    record(entry={"event": "reboot", "into": into})


def reboot_requested(*, state: dict) -> str | None:
    said = inside(
        check=False,
        command="[ -f /sim/run/request ] && { cat /sim/run/request;"
        " : > /sim/run/request; }",
        state=state,
    ).strip()
    return said or None


def received_stdin(*, marker: str, output: bytes) -> tuple[bytes, dict | None]:
    start = output.rfind(marker.encode())
    if start < 0:
        return output, None
    end = output.find(b"\n", start) + 1 or len(output)
    count, digest = output[start:end].split()[1:3]
    return output[:start] + output[end:], {
        "bytes": int(count),
        "md5": digest.decode(),
    }


def record(*, entry: dict) -> None:
    line = json.dumps({"time": round(time.time(), 3), **entry}) + "\n"
    WORK.mkdir(exist_ok=True, parents=True)
    descriptor = os.open(TRACE, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        view = memoryview(line.encode())
        while view:
            view = view[os.write(descriptor, view) :]
    finally:
        os.close(descriptor)


def refuse_real_caches() -> None:
    home = os.environ.get("HOME")
    if not home:
        message = "HOME is not set, so the real caches cannot be found"
        raise SystemExit(message)
    roots = {pathlib.Path(home) / ".cache"}
    if os.environ.get("XDG_CACHE_HOME"):
        roots.add(pathlib.Path(os.environ["XDG_CACHE_HOME"]))
    real = {
        identity(path=root / name) for root in roots for name in ("", TOOL_CACHE)
    } - {None}
    SIM_CACHE.mkdir(exist_ok=True, parents=True)
    if identity(path=SIM_CACHE) in real:
        message = (
            f"FIREBREAK_SIM_CACHE must not be {SIM_CACHE}: a run would write there"
        )
        raise SystemExit(message)
    folder = SIM_CACHE / TOOL_CACHE
    if folder.is_symlink():
        message = f"{folder} is a link: a run would write where it points"
        raise SystemExit(message)
    folder.mkdir(exist_ok=True)
    if identity(path=folder) in real:
        message = f"{folder} is a real cache: a run would write there"
        raise SystemExit(message)


def request_reboot(*, delay: float = BOOT_SECONDS, into: str) -> None:
    with locked():
        state = load()
        reboot(delay=delay, into=into, state=state)
        save(state=state)


def save(*, state: dict) -> None:
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=1, sort_keys=True))
    temporary.replace(STATE)


def seen(*, state: dict) -> str:
    usb = state.get("usb")
    if usb and usb["at"] <= time.time() < usb["until"]:
        return "none"
    return state["mode"]


def sending(*, image: pathlib.Path, part: str, sparse: int | None) -> str:
    size = image.stat().st_size
    if sparse and size > sparse:
        return f"Sending sparse '{part}' 1/{-(-size // sparse)} ({sparse // 1024} KB)"
    return f"Sending '{part}' ({size // 1024} KB)"


def settle(*, state: dict) -> dict:
    booting = state.get("booting")
    if booting and time.time() >= booting["at"]:
        boot(into=booting["into"], state=state)
        save(state=state)
    usb = state.get("usb")
    if usb and usb["props"] and time.time() >= usb["at"]:
        inside(
            command=" && ".join(
                f"setprop {key} {shlex.quote(value)}"
                for key, value in usb["props"].items()
            ),
            state=state,
        )
        usb["props"] = {}
        save(state=state)
    return state


def shell(*, entry: dict, rest: list[str], state: dict, verb: str) -> int:  # ruff: ignore[complex-structure, too-many-locals]
    device_protocol = state.get("shell_protocol", True)
    if verb == "exec-out":
        command = " ".join([*rest[:1], *(shell_quote(text=word) for word in rest[1:])])
        flags: set[str] = {"n"}
        protocol = False
    else:
        parsed = shell_options(words=rest)
        if isinstance(parsed, str):
            print(f"adb shell: invalid option -- '{parsed}'", file=sys.stderr)
            return 1
        flags, command = parsed
        protocol = device_protocol and "x" not in flags
        if not protocol and "T" in flags:
            print("error: device only supports allocating a pty", file=sys.stderr)
            return 1
        if not protocol and len("shell:" + command) > LEGACY_SERVICE_BYTES:
            print("error: shell command too long", file=sys.stderr)
            return 1
    program = (
        ["/sim/bin/sim-pty", command]
        if verb == "shell" and not device_protocol
        else ["/sim/path/sh", "-c", command]
    )
    forwarded = "n" not in flags
    marker = uuid.uuid4().hex
    if forwarded:
        program = ["/sim/bin/sim-stdin", marker, *program]
    started = time.time()
    process = subprocess.Popen(
        [
            "docker",
            "exec",
            "-i",
            "-e",
            "PATH=/sim/path",
            "-u",
            user(state=state),
            state["container"],
            *program,
        ],
        stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    if protocol and not forwarded:
        process.stdin.close()
    digest = hashlib.md5(usedforsecurity=False)
    counted = [0]
    done = threading.Event()
    feeder = threading.Thread(
        kwargs={
            "close": protocol,
            "counted": counted,
            "digest": digest,
            "done": done,
            "sink": process.stdin,
        },
        target=stream,
    )
    if forwarded:
        feeder.start()
    output = process.stdout.read()
    status = process.wait()
    done.set()
    if forwarded:
        feeder.join()
        output, received = received_stdin(marker=marker, output=output)
        record(
            entry={
                "bytes": counted[0],
                "call": {"argv": entry["argv"], "tool": "adb"},
                "event": "stdin",
                "md5": digest.hexdigest(),
                "received": received,
            }
        )
    with contextlib.suppress(OSError):
        process.stdin.close()
    requested = reboot_requested(state=state)
    if requested:
        request_reboot(into=requested)
    if switched_during(started=started, state=state):
        record(entry={"call": {"argv": [verb, *rest], "tool": "adb"}, "event": "cut"})
        sys.stdout.buffer.write(output[: len(output) // 2])
        return USB_CUT_STATUS if protocol else 0
    sys.stdout.buffer.write(output)
    return status if protocol else 0


def shell_options(*, words: list[str]) -> tuple[set[str], str] | str:
    flags = set()
    index = 0
    while index < len(words):
        word = words[index]
        if word == "--":
            index += 1
            break
        if not word.startswith("-") or word == "-":
            break
        index += 1
        letters = word[1:]
        for position, letter in enumerate(letters):
            if letter == "e":
                if position + 1 == len(letters):
                    index += 1
                break
            if letter not in ADB_SHELL_OPTIONS:
                return letter
            flags.add(letter)
    return flags, " ".join(words[index:])


def shell_quote(*, text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


def sim_boot(*, action: str, spec: dict | None = None, state: dict) -> str:
    arguments = ["exec", state["container"], "/sim/bin/sim-boot", action]
    if spec is not None:
        arguments.append(json.dumps(spec))
    return docker(arguments=arguments, capture_output=True, text=True).stdout


def sizes(*, table: dict) -> list[int]:
    return sorted({size for images in table.values() for size, _ in images})


def sparse_bytes(*, text: str) -> int:
    unit = FASTBOOT_SPARSE_UNITS.get(text[-1:].upper(), 1)
    return int(text.rstrip("GKMgkm")) * unit


def start_bootrom() -> None:
    with (WORK / "bootrom.log").open("a") as log:
        subprocess.Popen(
            [sys.executable, str(HERE / "bootrom.py"), str(WORK)],
            start_new_session=True,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            stdout=log,
        )


def stock_lk(*, device: str) -> bytes:
    return (
        (f"SIM STOCK LK {DEVICES[device]['stock_lk']}\0product\0{device.upper()}\0")
        .encode()
        .ljust(STOCK_LK_SIZE, b"\xa5")
    )


def stock_lks(*, device: str) -> list[list]:
    extracted = sorted((SIM_CACHE / TOOL_CACHE).glob(f"stock-{device}-*/lk.img"))
    return measured(
        images=[stock_lk(device=device), *(path.read_bytes() for path in extracted)]
    )


def stock_rpmb() -> bytes:
    return b"AMZN" + hashlib.sha256(b"firebreak-sim.rpmb").digest() * 7 + bytes(28)


def stream(
    *,
    close: bool,
    counted: list[int],
    digest: Hash,
    done: threading.Event,
    sink: BinaryIO,
) -> None:
    source = sys.stdin.fileno()
    target = sink.fileno()
    os.set_blocking(target, False)
    pending = b""
    ended = False
    while not done.is_set() and not (ended and not pending):
        readers = [] if ended or pending else [source]
        ready, writable, _ = select.select(
            readers, [target] if pending else [], [], STDIN_POLL_SECONDS
        )
        if source in ready:
            pending = os.read(source, STDIN_CHUNK)
            ended = not pending
        if target in writable:
            try:
                sent = os.write(target, pending)
            except BlockingIOError:
                continue
            except OSError:
                return
            digest.update(pending[:sent])
            counted[0] += sent
            pending = pending[sent:]
    if close and ended:
        with contextlib.suppress(OSError):
            sink.close()


def switched_during(*, started: float, state: dict) -> bool:
    usb = state.get("usb")
    return bool(usb) and started < usb["at"] <= time.time()


def user(*, state: dict) -> str:
    uid = state["outcome"]["uid"]
    return f"{uid}:{uid}"


def warn(*, text: str) -> None:
    print(f"\n*** WARNING: {text}\n", file=sys.stderr)


def write_amonet_v2(*, state: dict) -> None:
    spec = DEVICES[state["device"]]
    writes = []
    with (
        zipfile.ZipFile(pathlib.Path(state["cache"]) / spec["amonet"]) as v2,
        tempfile.TemporaryDirectory() as folder,
    ):
        upload = pathlib.Path(folder) / "brick"
        upload.mkdir()
        for target, suffix in (
            ("lk_a", "bin/lk.bin"),
            ("lk_b", "bin/lk.bin"),
            ("tee2", "bin/tz.img"),
            ("tee1", "bin/tee-payload.bin"),
            ("expdb", spec["kaeru"]),
            ("recovery", "bin/twrp.img"),
        ):
            (upload / target).write_bytes(member(archive=v2, suffix=suffix))
            node = f"{BY_NAME}/{target}"
            writes.append(
                f"blockdev --setrw {node} 2>/dev/null; dd if=/sim/brick/{target}"
                f" of={node} bs=512 conv=notrunc,fsync 2>/dev/null{protect(node=node)}"
            )
        docker(
            arguments=["cp", "-L", str(upload), f"{state['container']}:/sim/"],
            capture_output=True,
        )
    inside(command="; ".join([*writes, "rm -rf /sim/brick"]), state=state)


def write_image(*, local: pathlib.Path, node: str, seek: int = 0, state: dict) -> None:
    docker(
        arguments=["cp", "-L", str(local), f"{state['container']}:/sim/upload"],
        capture_output=True,
    )
    inside(
        command=f"blockdev --setrw {node} 2>/dev/null; dd if=/sim/upload"
        f" of={node} bs=512 seek={seek} conv=notrunc,fsync 2>/dev/null;"
        f" rm -f /sim/upload{protect(node=node)}",
        state=state,
    )


if __name__ == "__main__":
    with busy():
        sys.exit(main())
