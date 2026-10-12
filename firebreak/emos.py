from __future__ import annotations

import os
import shlex
import subprocess
import time

from firebreak.cache import CACHE
from firebreak.host import (
    MORE_THAN_ONE,
    NO_ACCESS,
    USER_SERIAL,
    child,
    child_path,
    pyserial_wheel,
    rerun,
)
from firebreak.ui import ARGUMENTS, PROGRESS, FatalError, clock, show

EMOS_DEVICE_ID = (0x1949, 0x2007)


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
        raise FatalError(message=MORE_THAN_ONE)
    return output


def emos_recovery() -> None:
    answer = emos(action="recovery")
    if answer == "password":
        raise FatalError(
            message="emOS's console asks for a password. Type /init recovery at"
            " the console, or clear the console password in EchoMuse's"
            " dashboard, then run this again."
        )
    if answer == "denied":
        raise FatalError(message=NO_ACCESS + rerun())
    if answer != "recovery":
        raise FatalError(
            message="emOS's serial console did not answer. Run this again."
        )


def stage_emos() -> None:
    emos_recovery()
    PROGRESS.begin(estimate="40 s", label="waiting for recovery to start")
