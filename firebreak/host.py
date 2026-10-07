from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
import sys
import time
from typing import BinaryIO

from firebreak.cache import digest
from firebreak.ui import ARGS, PROGRESS, SESSION, _die, clock, program, show

AS_ROOT = (
    "run this as your own user, not as root or with sudo: the downloads would"
    " belong to root, and on Linux udev rules let a user open the Dot"
)
DOT_TMP = pathlib.PurePosixPath("/tmp")  # ruff: ignore[hardcoded-temp-file]
MORE_THAN_ONE = (
    "more than one Dot on USB: set ANDROID_SERIAL to one's serial (adb"
    " devices lists them)"
)
NEW_GROUP = """this shell predates its user joining plugdev. Log in again, or run:

adb kill-server
"""
NO_ACCESS = """this user cannot open the Dot over USB. These commands let it:

sudo groupadd -f plugdev
sudo tee /etc/udev/rules.d/51-echo-dot.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="1949", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="4ee2", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="d001", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", ATTR{idProduct}=="0c01", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0e8d", ATTRS{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1949", ATTRS{idProduct}=="2007", MODE="0660", GROUP="plugdev", TAG+="uaccess"
EOF
sudo udevadm control --reload
sudo udevadm trigger
sudo usermod -aG plugdev "$USER"
adb kill-server

Then run it again with the new group, which a new login also has:

"""  # ruff: ignore[line-too-long]
PUSH_TRIES = 3
USER_SERIAL = os.environ.get("ANDROID_SERIAL")


def adb_script(*, body: str, name: str, work: pathlib.Path) -> bool:
    local = work / name
    with local.open("w", newline="\n") as f:
        f.write(body)
    remote = DOT_TMP / "root-step.sh"
    push_checked(local=local, remote=remote)
    command = f"sh {remote}; s=$?; rm -f {remote}; exit $s"
    return run(args=["adb", "shell", command], timeout=300).returncode == 0


def adb_shell(*, command: str, timeout: float = 300) -> str:
    out = run(args=["adb", "shell", "-n", command], timeout=timeout).stdout
    return "\n".join(
        line for line in out.split("\n") if not line.startswith("__bionic_open_tzdata")
    ).strip()


def check_adb() -> None:
    words = run(args=["adb", "version"], timeout=30).stdout.split()
    version = (
        words[4] if words[:4] == ["Android", "Debug", "Bridge", "version"] else "?"
    )
    parts = version.split(".")
    if not all(part.isdigit() for part in parts) or tuple(map(int, parts)) < (1, 0, 36):
        _die(
            message=f"adb reports version {version}; this needs 1.0.36"
            " (platform-tools r24) or newer"
        )


def check_user() -> None:
    if os.name != "nt" and os.geteuid() == 0:
        _die(message=AS_ROOT)
    if not sys.platform.startswith("linux"):
        return
    import grp  # ruff: ignore[import-outside-top-level]
    import pwd  # ruff: ignore[import-outside-top-level]

    try:
        plugdev = grp.getgrnam("plugdev")
    except KeyError:
        _die(message=NO_ACCESS + rerun())
    if plugdev.gr_gid in os.getgroups():
        return
    if pwd.getpwuid(os.getuid()).pw_name in plugdev.gr_mem:
        _die(message=NEW_GROUP + rerun())
    _die(message=NO_ACCESS + rerun())


def child(name: str, *args: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "firebreak",
        "_child",
        name,
        *args,
    ]


def child_path(wheel: pathlib.Path) -> str:
    return os.pathsep.join((
        str(wheel),
        str(pathlib.Path(__file__).resolve().parents[1]),
    ))


def command(  # ruff: ignore[too-many-arguments]
    *,
    args: list[str | pathlib.PurePath],
    cwd: pathlib.Path | None = None,
    stderr: int | None = None,
    stdin: int | BinaryIO | None = None,
    stdout: int | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[bytes]:
    loud = ARGS.verbose and not SESSION.probing
    if loud:
        show(text=f"{clock()} $ {' '.join(map(str, args))}")
    result = subprocess.run(
        args,
        check=False,
        cwd=cwd,
        stderr=stderr,
        stdin=stdin,
        stdout=stdout,
        timeout=timeout,
    )
    if loud:
        show(text=f"{clock()}   exit {result.returncode}")
    return result


def devices(args: list[str]) -> str:
    for _ in range(5):
        out = run(args=args, timeout=30).stdout
        lines = out.splitlines()
        if not any("no permissions" in line for line in lines) or any(
            line.split()[1:2] in (["device"], ["recovery"], ["fastboot"])
            for line in lines
        ):
            return out
        time.sleep(1)
    _die(message=NO_ACCESS + rerun())
    return ""


def getvar(name: str) -> str:
    try:
        out = run(args=["fastboot", "getvar", name], timeout=30).stdout
    except subprocess.TimeoutExpired:
        return ""
    for line in out.splitlines():
        if line.startswith(name + ":"):
            return line[len(name) + 1 :].strip()
    return ""


def in_fastboot() -> bool:
    out = devices(["fastboot", "devices"])
    serials = [
        line.split()[0]
        for line in out.splitlines()
        if line.split()[1:2] == ["fastboot"]
    ]
    if USER_SERIAL:
        return USER_SERIAL in serials
    if len(serials) > 1:
        _die(message=MORE_THAN_ONE)
    return bool(serials)


def md5_mismatch(*, command: str, want: str) -> str:
    got = [*adb_shell(command=command).split("\n")[-1].split(" "), ""][0]
    return "" if got == want else f": read {got or 'nothing'}, expected {want}"


def no_port_help() -> str:
    if sys.platform.startswith("linux"):
        return (
            "No new /dev/ttyACM* port could be opened. Stop ModemManager if it runs,\n"
            "and check that /etc/udev/rules.d/51-echo-dot.rules has this line:\n\n"
            'SUBSYSTEM=="tty", ATTRS{idVendor}=="0e8d", ATTRS{idProduct}=="0003",'
            ' MODE="0660", GROUP="plugdev", TAG+="uaccess"'
        )
    if sys.platform == "darwin":
        return "No new /dev/cu.usbmodem* port appeared."
    return "No new COM port appeared. Windows may need a driver for USB ID 0e8d:0003."


def on_usb(line: str) -> bool:
    if os.name != "nt":
        return " usb:" in line
    parts = line.split()
    return (
        parts[1:2] in (["device"], ["recovery"], ["unauthorized"])
        and ":" not in parts[0]
        and not parts[0].startswith("emulator-")
    )


def push_checked(*, local: pathlib.Path, remote: str | pathlib.PurePosixPath) -> None:
    for attempt in range(PUSH_TRIES):
        if attempt:
            reconnect(remote)
        try:  # ruff: ignore[too-many-statements-in-try-clause]
            result = run(args=["adb", "push", local, remote], timeout=600)
            if result.returncode != 0:
                said = result.stdout
                continue
            if adb_shell(command=f"md5sum {remote}", timeout=300).split(" ")[
                0
            ] == digest(kind="md5", path=local):
                return
            said = "its md5 read back did not match"
        except subprocess.TimeoutExpired as error:
            said = (
                f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
    _die(
        message=f"{remote} did not arrive intact after {PUSH_TRIES} tries;"
        f" the last: {said}"
    )


def reconnect(remote: str | pathlib.PurePosixPath) -> None:
    PROGRESS.note(
        f"{remote} did not arrive; waiting for the Dot to reconnect to try again."
    )
    try:
        run(args=["adb", "wait-for-recovery"], timeout=120)
    except subprocess.TimeoutExpired:
        _die(message="the Dot did not reconnect over USB in recovery")
    time.sleep(5)


def rerun() -> str:
    command = shlex.join([*program(), *sys.argv[1:]])
    return "sg plugdev -c " + shlex.quote(command)


def run(
    *,
    args: list[str | pathlib.PurePath],
    check: bool = False,
    cwd: pathlib.Path | None = None,
    stdin: BinaryIO | int = subprocess.DEVNULL,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    result = command(
        args=args,
        cwd=cwd,
        stderr=subprocess.STDOUT,
        stdin=stdin,
        stdout=subprocess.PIPE,
        timeout=timeout,
    )
    result.stdout = result.stdout.decode("utf-8", "replace").replace("\r", "")
    if check and result.returncode != 0:
        _die(message=f"{' '.join(map(str, args))} failed:\n{result.stdout}")
    return result


def usb_serial() -> str | None:
    if USER_SERIAL:
        if ":" in USER_SERIAL:
            _die(
                message="ANDROID_SERIAL names a network device;"
                " this needs the Dot on USB"
            )
        devices(["adb", "devices", "-l"])
        return USER_SERIAL
    out = devices(["adb", "devices", "-l"])
    usb = [
        line.split()[0]
        for line in out.splitlines()[1:]
        if on_usb(line) and "no permissions" not in line
    ]
    if len(usb) > 1:
        _die(message=MORE_THAN_ONE)
    if usb:
        os.environ["ANDROID_SERIAL"] = usb[0]
        return usb[0]
    os.environ.pop("ANDROID_SERIAL", None)
    return None
