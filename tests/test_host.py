from __future__ import annotations

import os
import pathlib
import shlex
import subprocess
import sys
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import host

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(autouse=True)
def no_waiting(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="sleep", target=host.time, value=lambda _: None)
    monkeypatch.setattr(name="USER_SERIAL", target=host, value=None)


def answers(
    *,
    monkeypatch: pytest.MonkeyPatch,
    replies: list[str | subprocess.CompletedProcess[str]],
) -> list[list[str]]:
    asked: list[list[str]] = []
    pending = list(replies)

    def run(*, arguments: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append([str(argument) for argument in arguments])
        reply = pending.pop(0) if len(pending) > 1 else pending[0]
        if isinstance(reply, subprocess.CompletedProcess):
            return reply
        return completed(standard_output=reply)

    monkeypatch.setattr(name="run", target=host, value=run)
    return asked


def completed(
    *, return_code: int = 0, standard_output: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[], returncode=return_code, stdout=standard_output
    )


def linux(
    *,
    group_id: int,
    groups: list[int],
    members: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = types.SimpleNamespace(gr_gid=group_id, gr_mem=members)
    monkeypatch.setattr(name="platform", target=host.sys, value="linux")
    monkeypatch.setattr(name="geteuid", target=os, value=lambda: 1000)
    monkeypatch.setattr(name="getgroups", target=os, value=lambda: groups)
    grp = types.ModuleType("grp")
    grp.getgrnam = lambda *, name: group if name == "plugdev" else None
    pwd = types.ModuleType("pwd")
    pwd.getpwuid = lambda _: types.SimpleNamespace(pw_name="me")
    monkeypatch.setitem(dic=sys.modules, name="grp", value=grp)
    monkeypatch.setitem(dic=sys.modules, name="pwd", value=pwd)


def pushing(
    *,
    md5: str,
    monkeypatch: pytest.MonkeyPatch,
    push: Callable[[], subprocess.CompletedProcess[str]],
) -> list[str]:
    reconnects: list[str] = []
    monkeypatch.setattr(name="run", target=host, value=lambda **_: push())
    monkeypatch.setattr(
        name="adb_shell", target=host, value=lambda **_: f"{md5}  /tmp/x"
    )
    monkeypatch.setattr(
        name="reconnect",
        target=host,
        value=lambda *, remote: reconnects.append(remote),
    )
    return reconnects


def test_adb_script(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    pushed = []
    monkeypatch.setattr(
        name="push_checked",
        target=host,
        value=lambda *, local, remote: pushed.append((local, remote)),
    )
    asked = answers(
        monkeypatch=monkeypatch,
        replies=[completed(return_code=0), completed(return_code=1)],
    )
    assert host.adb_script(body="echo hi\n", name="step.sh", work=tmp_path)
    assert (tmp_path / "step.sh").read_bytes() == b"echo hi\n"
    assert pushed == [
        (tmp_path / "step.sh", host.DOT_TEMPORARY_DIRECTORY / "root-step.sh")
    ]
    assert asked[0][:2] == ["adb", "shell"]
    assert not host.adb_script(body="exit 1\n", name="step.sh", work=tmp_path)


def test_adb_shell_drops_linker_noise(*, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(
        monkeypatch=monkeypatch, replies=["__bionic_open_tzdata: x\nuid=0\n"]
    )
    assert host.adb_shell(command="id") == "uid=0"
    assert asked == [["adb", "shell", "-n", "id"]]


@pytest.mark.parametrize(
    argnames=("output", "accepted"),
    argvalues=[
        ("Android Debug Bridge version 1.0.41\n", True),
        ("Android Debug Bridge version 1.0.36\n", True),
        ("Android Debug Bridge version 1.0.32\n", False),
        ("something else\n", False),
    ],
)
def test_check_adb(
    *, accepted: bool, monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    answers(monkeypatch=monkeypatch, replies=[output])
    if accepted:
        host.check_adb()
    else:
        with pytest.raises(expected_exception=SystemExit, match=r"this needs 1\.0\.36"):
            host.check_adb()


def test_check_user(*, monkeypatch: pytest.MonkeyPatch) -> None:
    linux(group_id=46, groups=[46], members=[], monkeypatch=monkeypatch)
    host.check_user()
    linux(group_id=46, groups=[], members=["me"], monkeypatch=monkeypatch)
    with pytest.raises(
        expected_exception=SystemExit, match="predates its user joining plugdev"
    ):
        host.check_user()
    linux(group_id=46, groups=[], members=[], monkeypatch=monkeypatch)
    with pytest.raises(
        expected_exception=SystemExit, match="cannot open the Dot over USB"
    ):
        host.check_user()


def test_check_user_elsewhere(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="geteuid", target=os, value=lambda: 1000)
    monkeypatch.setattr(name="platform", target=host.sys, value="darwin")
    host.check_user()


def test_check_user_refuses_root(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="geteuid", target=os, value=lambda: 0)
    with pytest.raises(expected_exception=SystemExit, match="not as root"):
        host.check_user()


def test_check_user_without_plugdev(*, monkeypatch: pytest.MonkeyPatch) -> None:
    linux(group_id=46, groups=[], members=[], monkeypatch=monkeypatch)

    def missing(**_: str) -> None:
        raise KeyError

    monkeypatch.setattr(name="getgrnam", target=sys.modules["grp"], value=missing)
    with pytest.raises(
        expected_exception=SystemExit, match="cannot open the Dot over USB"
    ):
        host.check_user()


def test_child() -> None:
    assert host.child(arguments=["find"], name="emos") == [
        sys.executable,
        "-m",
        "firebreak",
        "_child",
        "emos",
        "find",
    ]


def test_child_path_finds_the_package(*, tmp_path: pathlib.Path) -> None:
    wheel, package = host.child_path(wheel=tmp_path).split(sep=os.pathsep)
    assert wheel == str(tmp_path)
    assert (pathlib.Path(package) / "firebreak" / "__main__.py").is_file()
    assert host.child_path(wheel=None) == package


def test_command(*, capsys: pytest.CaptureFixture[str]) -> None:
    script = [sys.executable, "-c", "import sys; sys.exit(3)"]
    assert host.command(arguments=script).returncode == 3
    assert capsys.readouterr().out == ""
    host.ARGUMENTS.verbose = True
    host.command(arguments=script)
    shown = capsys.readouterr().out.splitlines()
    assert shown[0].endswith(f"$ {' '.join(script)}")
    assert shown[1].endswith("  exit 3")
    host.SESSION.probing = True
    host.command(arguments=script)
    assert capsys.readouterr().out == ""


def test_devices(*, monkeypatch: pytest.MonkeyPatch) -> None:
    answers(
        monkeypatch=monkeypatch, replies=["???? no permissions\n", "S1 device usb:1\n"]
    )
    assert host.devices(arguments=["adb", "devices"]) == "S1 device usb:1\n"


def test_devices_without_permission(*, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch=monkeypatch, replies=["???? no permissions\n"])
    with pytest.raises(
        expected_exception=SystemExit, match="cannot open the Dot over USB"
    ):
        host.devices(arguments=["adb", "devices"])
    assert len(asked) == 5


def test_getvar(*, monkeypatch: pytest.MonkeyPatch) -> None:
    answers(
        monkeypatch=monkeypatch,
        replies=["unlock_status: true\nlk_build_desc: abc \nFinished.\n"],
    )
    assert host.getvar(name="lk_build_desc") == "abc"
    assert host.getvar(name="product") == ""

    def slow(**_: object) -> None:
        raise subprocess.TimeoutExpired(cmd="fastboot", timeout=30)

    monkeypatch.setattr(name="run", target=host, value=slow)
    assert host.getvar(name="product") == ""


def test_in_fastboot(*, monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch=monkeypatch, replies=[""])
    assert not host.in_fastboot()
    answers(monkeypatch=monkeypatch, replies=["S1\tfastboot\n"])
    assert host.in_fastboot()
    answers(monkeypatch=monkeypatch, replies=["S1\tfastboot\nS2\tfastboot\n"])
    with pytest.raises(expected_exception=SystemExit, match="more than one Dot"):
        host.in_fastboot()
    monkeypatch.setattr(name="USER_SERIAL", target=host, value="S2")
    assert host.in_fastboot()
    monkeypatch.setattr(name="USER_SERIAL", target=host, value="S3")
    assert not host.in_fastboot()


def test_md5_mismatch(*, monkeypatch: pytest.MonkeyPatch) -> None:
    answers(monkeypatch=monkeypatch, replies=["abc  /dev/x\n"])
    assert host.md5_mismatch(command="md5sum /dev/x", want="abc") == ""
    assert host.md5_mismatch(command="md5sum /dev/x", want="def") == (
        ": read abc, expected def"
    )
    answers(monkeypatch=monkeypatch, replies=[""])
    assert host.md5_mismatch(command="md5sum /dev/x", want="def") == (
        ": read nothing, expected def"
    )


@pytest.mark.parametrize(
    argnames=("platform", "want"),
    argvalues=[
        ("linux", "/dev/ttyACM*"),
        ("darwin", "/dev/cu.usbmodem*"),
        ("win32", "COM port"),
    ],
)
def test_no_port_help(
    *, monkeypatch: pytest.MonkeyPatch, platform: str, want: str
) -> None:
    monkeypatch.setattr(name="platform", target=host.sys, value=platform)
    assert want in host.no_port_help()


@pytest.mark.parametrize(
    argnames=("name", "line", "want"),
    argvalues=[
        ("posix", "S1 device usb:1-1 product:x", True),
        ("posix", "192.168.1.40:5555 device product:x", False),
        ("nt", "S1 device product:x", True),
        ("nt", "S1 unauthorized", True),
        ("nt", "192.168.1.40:5555 device product:x", False),
        ("nt", "emulator-5554 device product:x", False),
        ("nt", "S1 offline", False),
    ],
)
def test_on_usb(
    *, line: str, monkeypatch: pytest.MonkeyPatch, name: str, want: bool
) -> None:
    monkeypatch.setattr(name="os", target=host, value=types.SimpleNamespace(name=name))
    assert host.on_usb(line=line) is want


def test_probe_serial_asks_for_the_module_the_child_imports() -> None:
    assert host.SERIAL_PROBE.endswith("import serial")
    assert host.probe_serial() is True
    renamed = host.SERIAL_PROBE.replace("import serial", "import pyserial")
    assert host.command(arguments=[sys.executable, "-c", renamed]).returncode != 0


def test_push_checked(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    local = tmp_path / "x"
    local.write_bytes(data=b"x")
    md5 = host.digest(kind="md5", path=local)
    reconnects = pushing(md5=md5, monkeypatch=monkeypatch, push=completed)
    host.push_checked(local=local, remote="/tmp/x")
    assert reconnects == []


@pytest.mark.parametrize(
    argnames=("return_code", "md5", "timeout", "said"),
    argvalues=[
        (1, "", False, "the last: adb: error"),
        (0, "0" * 32, False, "the last: its md5 read back"),
        (0, "", True, "the last: adb push did not"),
    ],
)
def test_push_checked_fails(  # ruff: ignore[too-many-arguments]
    *,
    md5: str,
    monkeypatch: pytest.MonkeyPatch,
    return_code: int,
    said: str,
    timeout: bool,
    tmp_path: pathlib.Path,
) -> None:
    local = tmp_path / "x"
    local.write_bytes(data=b"x")

    def push() -> subprocess.CompletedProcess[str]:
        if timeout:
            raise subprocess.TimeoutExpired(cmd=["adb", "push"], timeout=600)
        return completed(return_code=return_code, standard_output="adb: error")

    reconnects = pushing(md5=md5, monkeypatch=monkeypatch, push=push)
    with pytest.raises(expected_exception=SystemExit, match=said):
        host.push_checked(local=local, remote="/tmp/x")
    assert reconnects == ["/tmp/x", "/tmp/x"]


def test_pyserial_wheel_gives_the_wheel_when_the_child_cannot_import(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    wheel = tmp_path / "pyserial.whl"
    fetched, probes = [], []

    def fetch(*, download: object) -> pathlib.Path:
        fetched.append(download)
        return wheel

    def missing() -> bool:
        probes.append(False)
        return False

    monkeypatch.setattr(name="fetch", target=host, value=fetch)
    monkeypatch.setattr(name="probe_serial", target=host, value=missing)
    assert host.pyserial_wheel() == wheel
    assert host.pyserial_wheel() == wheel
    assert fetched == [host.PYSERIAL, host.PYSERIAL]
    assert len(probes) == 1

    host.SESSION.serial_ready = None
    monkeypatch.setattr(name="probe_serial", target=host, value=lambda: True)
    assert host.pyserial_wheel() is None
    assert fetched == [host.PYSERIAL, host.PYSERIAL]


def test_reconnect(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    asked = answers(monkeypatch=monkeypatch, replies=[""])
    host.reconnect(remote="/tmp/x")
    assert asked == [["adb", "wait-for-recovery"]]
    assert "/tmp/x did not arrive" in capsys.readouterr().out

    def slow(**_: object) -> None:
        raise subprocess.TimeoutExpired(cmd="adb", timeout=120)

    monkeypatch.setattr(name="run", target=host, value=slow)
    with pytest.raises(expected_exception=SystemExit, match="did not reconnect"):
        host.reconnect(remote="/tmp/x")


def test_rerun(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        name="argv", target=sys, value=["/src/firebreak/__main__.py", "stock"]
    )
    monkeypatch.setattr(name="executable", target=sys, value="/usr/bin/python3")
    assert host.rerun() == "sg plugdev -c '/usr/bin/python3 -m firebreak stock'"


def test_rerun_quotes_a_path_with_spaces(*, monkeypatch: pytest.MonkeyPatch) -> None:
    argv = ["/My Files/firebreak.pyz", "stock", "it's"]
    monkeypatch.setattr(name="argv", target=sys, value=argv)
    monkeypatch.setattr(name="executable", target=sys, value="/usr/bin/python3")
    command = shlex.split(s=host.rerun())
    assert command[:3] == ["sg", "plugdev", "-c"]
    assert shlex.split(s=command[3]) == ["/usr/bin/python3", *argv]


def test_run() -> None:
    script = "import sys; sys.stdout.write('a\\r\\nb\\n'); sys.exit(2)"
    result = host.run(arguments=[sys.executable, "-c", script])
    assert (result.returncode, result.stdout) == (2, "a\nb\n")
    with pytest.raises(expected_exception=SystemExit, match="failed:\na\nb"):
        host.run(arguments=[sys.executable, "-c", script], check=True)


def test_run_replaces_bytes_that_are_not_utf_8() -> None:
    script = "import sys; sys.stdout.buffer.write(bytes([97, 255, 98]))"
    assert host.run(arguments=[sys.executable, "-c", script]).stdout == "a\ufffdb"


def test_usb_serial(*, monkeypatch: pytest.MonkeyPatch) -> None:
    head = "List of devices attached\n"
    monkeypatch.setenv(name="ANDROID_SERIAL", value="old")
    answers(monkeypatch=monkeypatch, replies=[head])
    assert host.usb_serial() is None
    assert "ANDROID_SERIAL" not in os.environ
    answers(
        monkeypatch=monkeypatch,
        replies=[head + "S1 device usb:1 product:x\n10.0.0.2:5555 device\n"],
    )
    assert host.usb_serial() == "S1"
    assert os.environ["ANDROID_SERIAL"] == "S1"
    answers(
        monkeypatch=monkeypatch, replies=[head + "S1 device usb:1\nS2 recovery usb:2\n"]
    )
    with pytest.raises(expected_exception=SystemExit, match="more than one Dot"):
        host.usb_serial()


def test_usb_serial_finds_an_unauthorized_dot(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers(
        monkeypatch=monkeypatch,
        replies=["List of devices attached\nS1 unauthorized usb:1-1 transport_id:1\n"],
    )
    assert host.usb_serial() == "S1"


def test_usb_serial_from_the_environment(*, monkeypatch: pytest.MonkeyPatch) -> None:
    asked = answers(monkeypatch=monkeypatch, replies=[""])
    monkeypatch.setattr(name="USER_SERIAL", target=host, value="S9")
    assert host.usb_serial() == "S9"
    assert asked == [["adb", "devices", "-l"]]
    monkeypatch.setattr(name="USER_SERIAL", target=host, value="10.0.0.2:5555")
    with pytest.raises(expected_exception=SystemExit, match="names a network device"):
        host.usb_serial()
