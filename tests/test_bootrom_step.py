from __future__ import annotations

import struct
import subprocess
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import bootrom_step
from firebreak.amonet.payload import BLOCK_SIZE, PAYLOAD_MAGIC, Command
from firebreak.android import gpt
from firebreak.bootrom import USER_AREA_SIGNATURE
from firebreak.devices import BISCUIT, RADAR, radar
from firebreak.devices.biscuit import (
    AMONET_V1_1_0_LK,
    UNLOCK_FROM_BOOTROM,
    UNLOCK_TO_FIREOS5,
    UNLOCK_TO_FIREOS6,
    UNLOCK_V2_FROM_BOOTROM,
)
from firebreak.mediatek.usbdl import (
    HandshakeTimeoutError,
    ProductId,
    ProtocolMismatchError,
    UsbdlError,
)
from firebreak.plan import Action
from firebreak.plugin import ClearBoot0Header, FastbootFlash
from firebreak.ui import FatalError, explained

if TYPE_CHECKING:
    import pathlib

    from typing_extensions import Self

ACTIONS = (
    Action(data=b"h", kind="ClearBoot0Header", label="clear", length=1, offset=0),
    Action(kind="Repartition", label="already has room", length=0),
    Action(expect=b"AMZN", kind="ZeroRpmb", label="rpmb"),
    Action(
        data=b"p",
        kind="Write",
        label="preloader",
        length=1,
        offset=0,
        unrecoverable=True,
    ),
    Action(kind="Reboot", label="reboot"),
    Action(data=b"t", kind="FastbootFlash", label="twrp", length=1, offset=0),
)
BISCUIT_LK = b"lk\0product\0BISCUIT\0rest"
BOOTROM = {"/dev/bootrom": ProductId.BOOTROM}
BOTH = {
    "/dev/a-preloader": ProductId.PRELOADER,
    "/dev/b-bootrom": ProductId.BOOTROM,
}
LK_FIRST = {"lk_a": 32768, "lk_b": 65536}
PAYLOAD = b"a payload"
PRELOADER = {"/dev/preloader": ProductId.PRELOADER}
REBOOT_COMMAND = PAYLOAD_MAGIC.to_bytes(4, "big") + Command.REBOOT.to_bytes(4, "big")
WRITES = ("clear", "rpmb", "preloader", "reboot")


class Connection:
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.closed = True

    def __init__(self, *, name: str) -> None:
        self.closed = False
        self.echo = b"\xf1"
        self.flushes = 0
        self.name = name
        self.timeout: float | None = None
        self.writes: list[bytes] = []

    def close(self) -> None:
        self.closed = True

    def read(self, *, size: int) -> bytes:
        return self.echo[:size]

    def reset_input_buffer(self) -> None:
        self.flushes += 1

    def write(self, *, data: bytes) -> None:
        self.writes.append(data)


class Live:
    def __init__(self, *, port: object, rig: Rig) -> None:
        self.port = port
        self.rig = rig

    def __str__(self) -> str:
        return "live"

    def probed_send(self, *, arguments: tuple[int, ...] = (), command: int) -> bool:
        self.rig.steps.append(f"probe {Command(command).name.lower()}")
        if not self.rig.probed:
            return False
        self.rig.steps.append(f"switch {arguments[0]}")
        return True

    def read_block(self, *, index: int) -> bytes:
        self.rig.steps.append(f"read block {index}")
        if self.rig.signature is None:
            message = "read fail"
            raise UsbdlError(message)
        return bytes(BLOCK_SIZE - len(self.rig.signature)) + self.rig.signature

    def switch_partition(self, *, partition: int) -> None:
        self.rig.steps.append(f"switch {partition}")


class Rig(types.SimpleNamespace):
    pass


class Client:
    rig: Rig = Rig()

    def __init__(self, *, port: Connection) -> None:
        self.port = port
        self.rig.clients.append(self)

    def disable_watchdog(self) -> None:
        self.rig.steps.append("watchdog")
        if self.rig.exploit_error is not None:
            raise self.rig.exploit_error

    def handshake(self) -> None:
        self.rig.steps.append("handshake")
        if self.rig.handshakes:
            error = self.rig.handshakes.pop(0)
            if error is not None:
                raise error

    def start_payload(self, *, payload: bytes) -> Live:
        self.rig.steps.append(f"payload {payload.decode()}")
        return Live(port=self.port, rig=self.rig)


@pytest.fixture
def rig(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Rig:
    found = Rig(
        amonet=tmp_path / "amonet",
        clients=[],
        connections=[],
        erased=[],
        exploit_error=None,
        handshakes=[],
        lks=dict.fromkeys(LK_FIRST.values(), BISCUIT_LK),
        not_ready=False,
        now=[0.0],
        opened=[],
        payload=tmp_path / "payload.bin",
        ports=[BOOTROM],
        probed=True,
        refusals=0,
        resolved=ACTIONS,
        signature=USER_AREA_SIGNATURE,
        steps=[],
        table=lk_table(names=tuple(LK_FIRST)),
        tick=[0.5],
        write_error=None,
        written=[],
    )
    found.payload.write_bytes(data=PAYLOAD)

    def executed(*, actions: tuple[Action, ...], payload: Live) -> None:
        found.erased.append(bootrom_step.SESSION.boot0_erased)
        found.steps.append(f"execute {payload}")
        found.written.append(tuple(action.label for action in actions))
        if found.write_error is not None:
            raise found.write_error

    def monotonic() -> float:
        found.now[0] += found.tick[0]
        return found.now[0]

    def opened(*, name: str, write_timeout: float | None = None) -> Connection:
        found.opened.append((name, write_timeout))
        if found.refusals:
            found.refusals -= 1
            message = "denied"
            raise OSError(message)
        connection = Connection(name=name)
        found.connections.append(connection)
        return connection

    def ports() -> dict[str, int]:
        return found.ports[0] if len(found.ports) == 1 else found.ports.pop(0)

    def resolved(**_: object) -> tuple[Action, ...]:
        found.steps.append("resolve")
        return found.resolved

    monkeypatch.setattr(name="rig", target=Client, value=found)
    monkeypatch.setattr(name="Bootrom", target=bootrom_step, value=Client)
    monkeypatch.setattr(name="start_payload", target=bootrom_step, value=started)
    monkeypatch.setattr(
        name="countdown",
        target=bootrom_step,
        value=lambda: found.steps.append("countdown"),
    )
    monkeypatch.setattr(
        name="getvar",
        target=bootrom_step,
        value=lambda **_: "f379dba-20170906_000423",
    )
    monkeypatch.setattr(name="in_fastboot", target=bootrom_step, value=lambda: True)
    monkeypatch.setattr(name="mediatek_ports", target=bootrom_step, value=ports)
    monkeypatch.setattr(name="open_serial_port", target=bootrom_step, value=opened)
    monkeypatch.setattr(name="resolve", target=bootrom_step, value=resolved)
    monkeypatch.setattr(
        name="time",
        target=bootrom_step,
        value=types.SimpleNamespace(monotonic=monotonic, sleep=lambda _: None),
    )
    monkeypatch.setattr(
        name="path", target=bootrom_step.sys, value=[*bootrom_step.sys.path]
    )
    monkeypatch.setattr(
        name="defeat",
        target=bootrom_step.range_check,
        value=lambda **_: found.steps.append("range checks"),
    )
    monkeypatch.setattr(name="execute", target=bootrom_step.bootrom, value=executed)

    def read(*, count: int, first: int, **_: object) -> bytes:
        found.steps.append(f"read {count} at {first}")
        return found.lks[first] if first else found.table

    monkeypatch.setattr(name="read", target=bootrom_step.bootrom, value=read)
    return found


def lk_table(*, names: tuple[str, ...]) -> bytes:
    entries = b"".join(
        b"T" * 16
        + bytes([number]) * 16
        + struct.pack("<QQ", LK_FIRST[name], LK_FIRST[name] + 2047)
        + bytes(8)
        + name.encode(encoding="utf-16le").ljust(72, b"\0")
        for number, name in enumerate(names, start=1)
    ).ljust(gpt.ENTRIES_SIZE, b"\0")
    header = bytearray(92)
    header[:16] = b"EFI PART" + b"\0\0\1\0" + struct.pack("<I", 92)
    header[24:56] = struct.pack("<QQQQ", 1, 1000033, 34, 1000000)
    header[80:88] = struct.pack("<II", 128, 128)
    return gpt.rebuilt_gpt(entries=entries, raw=b"M" * 512 + bytes(header)).primary


def started(*, bootrom: Client, client: type, payload: bytes) -> Live:
    assert client is bootrom_step.Client
    if bootrom.rig.not_ready:
        message = "the payload's ready pattern: expected b'\\xb1', got b''"
        raise bootrom_step.NotReadyError(message)
    return bootrom.start_payload(payload=payload)


def step(  # ruff: ignore[too-many-arguments]
    *,
    erase: object = None,
    little_kernel: str = AMONET_V1_1_0_LK,
    rig: Rig,
    tail: int | None = None,
    unlock: object = UNLOCK_FROM_BOOTROM,
    wheel: pathlib.Path | None = None,
) -> bool:
    return bootrom_step.bootrom_step(
        amonet=rig.amonet,
        erase=erase,
        little_kernel=little_kernel,
        payload=rig.payload,
        tail=tail,
        unlock=unlock,
        wheel=wheel,
    )


def test_a_bootloader_for_another_product_names_the_echo_the_unlock_is_for(
    *, rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    with pytest.raises(FatalError, match="product BISCUIT, not RADAR") as caught:
        step(rig=rig, unlock=radar.BOOTROM_UNLOCK)
    assert "not an Echo (2nd Generation)" in caught.value.message
    assert rig.written == []


def test_a_bootloader_for_another_product_stops_the_run(*, rig: Rig) -> None:
    rig.lks[LK_FIRST["lk_a"]] = b"\0product\0RADAR\0"
    bootrom_step.SESSION.short = True
    with pytest.raises(FatalError, match="product RADAR, not BISCUIT") as caught:
        step(rig=rig)
    assert "not an Echo Dot (2nd Generation)" in caught.value.message
    assert "--device" in caught.value.message
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_bootloader_that_cannot_be_read_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def unreadable(*, first: int, **_: object) -> bytes:
        if first:
            message = "device not configured"
            raise OSError(message)
        return rig.table

    monkeypatch.setattr(name="read", target=bootrom_step.bootrom, value=unreadable)
    with pytest.raises(FatalError, match="lk_a could not be read"):
        step(rig=rig)
    assert rig.written == []


def test_a_bootrom_port_is_taken_over_a_preloader_in_the_same_pass(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    rig.ports = [{}, {}, BOTH]
    assert step(rig=rig) is True
    assert rig.opened == [("/dev/b-bootrom", bootrom_step.BOOTROM_WRITE_TIMEOUT)]
    assert "missed" not in capsys.readouterr().out


def test_a_bootrom_port_that_comes_and_goes_is_handshaked_once(*, rig: Rig) -> None:
    rig.ports = [BOOTROM, BOOTROM, {}, BOOTROM]
    assert step(rig=rig) is True
    assert rig.steps.count("handshake") == 1


def test_a_bootrom_that_does_not_answer_as_one_stops_the_run(*, rig: Rig) -> None:
    rig.handshakes = [ProtocolMismatchError("sent 0xa0, read b'\\x00'")]
    with pytest.raises(FatalError, match="did not answer as one"):
        step(rig=rig)
    assert rig.written == []
    assert rig.clients[0].port.closed is True


def test_a_bootrom_that_echoes_the_probe_is_handshaked_not_joined(*, rig: Rig) -> None:
    rig.probed = False
    assert step(rig=rig) is True
    assert "handshake" in rig.steps
    assert rig.written == [WRITES]


def test_a_bootrom_that_never_answers_a_handshake_stops_the_run(*, rig: Rig) -> None:
    rig.handshakes = [HandshakeTimeoutError("no answer within 10 seconds")] * 4
    rig.tick = [100.0]
    with pytest.raises(FatalError, match="never answered a handshake"):
        step(rig=rig)
    assert rig.steps.count("handshake") == 1
    assert rig.written == []


def test_a_bootrom_that_never_appears_stops_the_run(*, rig: Rig) -> None:
    rig.ports = [{}]
    with pytest.raises(FatalError, match="did not show up as a serial port"):
        step(rig=rig)
    assert rig.written == []


def test_a_chain_with_no_bootloader_to_check_takes_any_fastboot(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(
        name="getvar",
        target=bootrom_step,
        value=lambda **_: "63cb91b-20221007_072309",
    )
    assert step(little_kernel="", rig=rig, unlock=UNLOCK_V2_FROM_BOOTROM) is True
    assert rig.written == [WRITES]


def test_a_dead_emmc_stops_the_run_before_anything_is_written(*, rig: Rig) -> None:
    rig.signature = b"\x00\x00"
    with pytest.raises(FatalError, match="eMMC did not answer: block 0"):
        step(rig=rig)
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_dead_emmc_with_the_short_on_blames_the_short(*, rig: Rig) -> None:
    bootrom_step.SESSION.short = True
    rig.signature = None
    with pytest.raises(FatalError, match="most likely because the short"):
        step(rig=rig)
    assert rig.steps[-2:] == ["switch 0", "read block 0"]
    assert rig.written == []


def test_a_dot_whose_bootloaders_name_no_product_stops_the_run(*, rig: Rig) -> None:
    rig.lks = dict.fromkeys(LK_FIRST.values(), bytes(512))
    bootrom_step.SESSION.short = True
    with pytest.raises(FatalError, match="neither lk_a nor lk_b") as caught:
        step(rig=rig)
    assert "firebreak report and paste" in " ".join(
        explained(error=caught.value).split()
    )
    assert rig.written == []


def test_a_failed_erase_stops_the_run_with_its_own_message(*, rig: Rig) -> None:
    with pytest.raises(FatalError, match="boot0 did not erase"):
        step(erase=lambda: "boot0 did not erase", rig=rig)
    assert bootrom_step.SESSION.boot0_erased is True
    assert rig.clients == []


def test_a_failed_exploit_stops_the_run_with_nothing_written(*, rig: Rig) -> None:
    rig.exploit_error = OSError("device not configured")
    with pytest.raises(FatalError, match="exploit did not go through"):
        step(rig=rig)
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_failure_after_the_erase_says_only_boot0_was_erased(*, rig: Rig) -> None:
    rig.exploit_error = OSError("device not configured")
    with pytest.raises(FatalError) as failure:
        step(erase=lambda: "", rig=rig)
    said = explained(error=failure.value).replace("\n", " ")
    assert "Only boot0 was erased" in said
    assert "Nothing was written" not in said


def test_a_fastboot_check_that_times_out_is_tried_again(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([subprocess.TimeoutExpired(cmd="fastboot", timeout=30), True])

    def in_fastboot() -> bool:
        answer = next(answers)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(name="in_fastboot", target=bootrom_step, value=in_fastboot)
    monkeypatch.setattr(
        name="getvar",
        target=bootrom_step,
        value=lambda **_: "f379dba-20170906_000423",
    )
    monkeypatch.setattr(name="sleep", target=bootrom_step.time, value=lambda _: None)
    bootrom_step.await_amonet_fastboot(little_kernel=AMONET_V1_1_0_LK)


def test_a_foreign_bootloader_in_lk_b_alone_stops_the_run(*, rig: Rig) -> None:
    rig.lks[LK_FIRST["lk_b"]] = b"\0product\0RADAR\0"
    with pytest.raises(FatalError, match="names its product RADAR"):
        step(rig=rig)
    assert rig.written == []
    assert "resolve" not in rig.steps


def test_a_handshake_that_times_out_asks_for_a_replug_and_tries_again(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    rig.handshakes = [HandshakeTimeoutError("no answer within 10 seconds")]
    rig.ports = [BOOTROM, {}, BOOTROM, BOOTROM, {}, BOOTROM]
    assert step(rig=rig) is True
    assert rig.steps.count("handshake") == 2
    assert len(rig.clients) == 2
    assert rig.clients[0].port.closed is True
    assert "did not answer" in capsys.readouterr().out
    assert rig.written == [WRITES]


def test_a_handshake_that_times_out_with_the_short_on_stops_the_run(
    *, rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    rig.handshakes = [HandshakeTimeoutError("no answer within 10 seconds")]
    with pytest.raises(FatalError, match="bootrom did not answer"):
        step(rig=rig)
    assert rig.written == []


def test_a_held_payload_is_joined_without_a_poke_or_a_handshake(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(
        name="Client",
        target=bootrom_step,
        value=lambda *, port, **_: Live(port=port, rig=rig),
    )
    assert step(rig=rig) is True
    assert "handshake" not in rig.steps
    assert rig.opened == [("/dev/bootrom", bootrom_step.BOOTROM_WRITE_TIMEOUT)]
    assert rig.written == [WRITES]


def test_a_held_payload_is_waited_for_rather_than_dropped(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(
        name="Client",
        target=bootrom_step,
        value=lambda *, port, **_: Live(port=port, rig=rig),
    )
    rig.ports = [{}, {}, BOOTROM]
    assert step(rig=rig) is True
    assert "handshake" not in rig.steps
    assert rig.written == [WRITES]


def test_a_held_payload_wins_over_a_short(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(
        name="Client",
        target=bootrom_step,
        value=lambda *, port, **_: Live(port=port, rig=rig),
    )
    bootrom_step.SESSION.short = True
    assert step(rig=rig) is True
    assert "handshake" not in rig.steps
    assert rig.written == [WRITES]


def test_a_missed_short_is_counted_and_the_run_keeps_waiting(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    rig.ports = [{}, {}, PRELOADER, BOOTROM]
    assert step(rig=rig) is True
    assert "Short 1 missed" in capsys.readouterr().out
    assert rig.steps[:3] == ["handshake", "watchdog", "countdown"]
    assert rig.written == [WRITES]
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_missed_short_on_a_terminal_starts_a_new_line(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="isatty", target=bootrom_step.sys.stdout, value=lambda: True
    )
    bootrom_step.say_missed_short(count=2)
    out = capsys.readouterr().out
    assert out.startswith("\n")
    assert "Short 2 missed" in out


def test_a_payload_is_found_by_what_it_reads_not_by_what_it_echoes(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(
        name="mediatek_ports",
        target=bootrom_step,
        value=lambda: {"/dev/one": 0x2000, "/dev/two": 0x0003},
    )
    monkeypatch.setattr(
        name="open_bootrom",
        target=bootrom_step,
        value=lambda **options: (
            opened.append(options["name"]) or Connection(name=options["name"])
        ),
    )
    timeouts: list[float] = []
    monkeypatch.setattr(
        name="Client",
        target=bootrom_step,
        value=lambda *, port, timeout: (
            timeouts.append(timeout) or Live(port=port, rig=rig)
        ),
    )
    assert bootrom_step.answering_payload() is not None
    assert opened == ["/dev/two"]
    assert rig.steps[:3] == [
        "probe switch_partition",
        "switch 0",
        "read block 0",
    ]
    assert timeouts == [bootrom_step.READ_TIMEOUT]
    rig.signature = b"\x01\x02"
    assert bootrom_step.answering_payload() is None
    rig.signature = None
    assert bootrom_step.answering_payload() is None


def test_a_payload_that_never_starts_with_the_short_on_blames_the_short(
    *, rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    rig.not_ready = True
    with pytest.raises(FatalError, match="most likely because the short"):
        step(rig=rig)
    assert rig.written == []


def test_a_payload_whose_area_will_not_switch_is_passed_over(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def refuses(**_: object) -> None:
        raise bootrom_step.FatalError(message="block 0 of its user area ends")

    monkeypatch.setattr(
        name="mediatek_ports", target=bootrom_step, value=lambda: {"/dev/two": 0x0003}
    )
    monkeypatch.setattr(
        name="open_bootrom",
        target=bootrom_step,
        value=lambda **options: Connection(name=options["name"]),
    )
    monkeypatch.setattr(
        name="Client",
        target=bootrom_step,
        value=lambda *, port, **_: Live(port=port, rig=rig),
    )
    monkeypatch.setattr(name="switch", target=bootrom_step.bootrom, value=refuses)
    assert bootrom_step.answering_payload() is None


def test_a_plan_that_does_not_resolve_stops_before_anything_is_written(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def unresolvable(**_: object) -> None:
        message = "biscuit has no lk_c partition"
        raise KeyError(message)

    bootrom_step.SESSION.short = True
    monkeypatch.setattr(name="resolve", target=bootrom_step, value=unresolvable)
    with pytest.raises(
        FatalError,
        match=r"does not fit this Echo Dot \(2nd Generation\): biscuit has no",
    ):
        step(rig=rig)
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_plan_with_no_reboot_is_carried_out_whole(*, rig: Rig) -> None:
    kinds = [action.kind for action in ACTIONS]
    rig.resolved = ACTIONS[: kinds.index("Reboot")]
    assert step(rig=rig) is True
    assert rig.written == [WRITES[:-1]]


def test_a_port_that_will_not_open_is_named_once_after_a_second(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    rig.refusals = 3
    rig.tick = [0.4]
    assert step(erase=lambda: "", rig=rig) is True
    said = capsys.readouterr().out
    assert said.count("Cannot open") == 1
    assert "keeps trying" in said
    assert len(rig.opened) == 4


def test_a_preloader_means_boot0_is_intact_and_needs_no_bootrom_step(
    *, capsys: pytest.CaptureFixture[str], rig: Rig, tmp_path: pathlib.Path
) -> None:
    bootrom_step.SESSION.boot0_erased = True
    rig.ports = [{}, {}, {}, PRELOADER]
    wheel = tmp_path / "pyserial.whl"
    assert step(rig=rig, wheel=wheel) is False
    assert bootrom_step.SESSION.boot0_erased is False
    assert rig.written == []
    assert str(wheel) in bootrom_step.sys.path
    assert "boot0 is intact" in capsys.readouterr().out


def test_a_resumed_run_on_a_foreign_dot_says_only_boot0_was_erased(*, rig: Rig) -> None:
    rig.lks[LK_FIRST["lk_a"]] = b"\0product\0RADAR\0"
    bootrom_step.SESSION.boot0_erased = True
    with pytest.raises(FatalError) as caught:
        step(rig=rig)
    said = " ".join(explained(error=caught.value).split())
    assert "Only boot0 was erased. Unplug it" in said
    assert rig.written == []


def test_a_second_missed_short_warns_again_and_counts_it(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    bootrom_step.SESSION.short = True
    rig.ports = [{}, {}, PRELOADER, {}, PRELOADER, BOOTROM]
    assert step(rig=rig) is True
    said = capsys.readouterr().out
    assert "Short 1 missed" in said
    assert "Short 2 missed" in said


def test_a_serial_port_opens_at_the_bootrom_rate(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    import serial  # ruff: ignore[import-outside-top-level]

    opened: list[dict[str, object]] = []
    monkeypatch.setattr(
        name="Serial", target=serial, value=lambda **o: opened.append(o)
    )
    bootrom_step.open_serial_port(name="/dev/ttyACM0", write_timeout=2)
    assert opened == [
        {
            "baudrate": bootrom_step.BAUD_RATE,
            "port": "/dev/ttyACM0",
            "timeout": bootrom_step.READ_TIMEOUT,
            "write_timeout": 2,
        }
    ]


def test_a_stock_preloader_step_held_in_the_bootrom_sends_no_reboot(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    carried: list[tuple[Action, ...]] = []
    monkeypatch.setattr(
        name="execute",
        target=bootrom_step.bootrom,
        value=lambda *, actions, **_: carried.append(actions),
    )
    bootrom_step.SESSION.fastboot = True
    bootrom_step.SESSION.boot0_erased = True
    bootrom_step.stock_preloader(
        build="5.5.0.3", payload=rig.payload, preloader=b"P" * 1024, wheel=None
    )
    assert [action.kind for action in carried[0]] == ["ZeroRpmb", "Write"]
    assert bootrom_step.SESSION.boot0_erased is False
    assert bootrom_step.SESSION.held is True


def test_a_stock_preloader_step_that_meets_a_preloader_stops_the_run(
    *, rig: Rig
) -> None:
    bootrom_step.SESSION.boot0_erased = True
    rig.ports = [{}, {}, PRELOADER]
    with pytest.raises(FatalError, match="boot0 was not clear"):
        bootrom_step.stock_preloader(
            build="5.5.0.3", payload=rig.payload, preloader=b"P" * 512, wheel=None
        )
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is True


def test_a_stock_preloader_step_zeroes_the_rpmb_and_writes_boot0(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig, tmp_path: pathlib.Path
) -> None:
    carried: list[tuple[Action, ...]] = []
    monkeypatch.setattr(
        name="execute",
        target=bootrom_step.bootrom,
        value=lambda *, actions, **_: carried.append(actions),
    )
    bootrom_step.SESSION.boot0_erased = True
    wheel = tmp_path / "pyserial.whl"
    bootrom_step.stock_preloader(
        build="5.5.0.3", payload=rig.payload, preloader=b"P" * 1024, wheel=wheel
    )
    assert rig.steps == [
        "handshake",
        "watchdog",
        "range checks",
        f"payload {PAYLOAD.decode()}",
        "switch 0",
        "read block 0",
    ]
    assert carried == [
        (
            Action(expect=b"AMZN", kind="ZeroRpmb", label="zero the RPMB"),
            Action(
                data=b"P" * 1024,
                kind="Write",
                label="write the 5.5.0.3 preloader to boot0",
                length=1024,
                offset=0,
                target=bootrom_step.BOOT0,
            ),
            Action(kind="Reboot", label="rebooting into stock 5.5.0.3"),
        )
    ]
    assert rig.clients[0].port.closed
    assert bootrom_step.SESSION.boot0_erased is False
    assert str(wheel) in bootrom_step.sys.path


def test_a_table_that_cannot_be_read_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def unreadable(**_: object) -> None:
        message = "device not configured"
        raise OSError(message)

    monkeypatch.setattr(name="read", target=bootrom_step.bootrom, value=unreadable)
    with pytest.raises(FatalError, match="partition table could not be read"):
        step(rig=rig)
    assert rig.written == []
    assert bootrom_step.SESSION.boot0_erased is False


def test_a_table_without_an_lk_slot_stops_the_run(*, rig: Rig) -> None:
    rig.table = lk_table(names=("lk_a",))
    with pytest.raises(FatalError, match="partition table has no lk_b"):
        step(rig=rig)
    assert rig.written == []


def test_a_tail_makes_the_whole_total_known_once_the_chain_is_counted(
    *, rig: Rig
) -> None:
    assert bootrom_step.PROGRESS.steps == 0
    assert step(rig=rig, tail=16) is True
    assert (
        bootrom_step.PROGRESS.steps == 1 + 3 + bootrom_step.STEPS_AFTER_THE_CHAIN + 16
    )


def test_a_torn_table_is_left_to_the_plan_without_reading_an_lk(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def torn(**_: object) -> None:
        message = "the partition table is not intact"
        raise ValueError(message)

    table = bytearray(rig.table)
    table[2 * 512 + 40] ^= 1
    rig.table = bytes(table)
    monkeypatch.setattr(name="resolve", target=bootrom_step, value=torn)
    with pytest.raises(
        FatalError,
        match=r"does not fit this Echo Dot \(2nd Generation\): the partition",
    ):
        step(rig=rig)
    assert [entry for entry in rig.steps if entry.startswith("read ")] == [
        "read block 0",
        f"read {bootrom_step.TABLE_SECTORS} at 0",
    ]
    assert rig.written == []


def test_a_torn_table_names_no_echo(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    live = Live(port=Connection(name="/dev/one"), rig=rig)
    monkeypatch.setattr(name="gpt_intact", target=bootrom_step, value=lambda **_: False)
    assert bootrom_step.payload_device(live=live) is None


def test_keep_trying_with_the_short_on_warns_and_waits_on(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="isatty", target=bootrom_step.sys.stdout, value=lambda: True
    )
    bootrom_step.SESSION.short = True
    bootrom_step.keep_trying(message="Cannot open COM3")
    out = capsys.readouterr().out
    assert out.startswith("\n")
    assert "Cannot open COM3. The run keeps trying." in out
    assert "Waiting for the bootrom." in out


def test_no_port_at_all_stops_the_run_with_the_port_help(*, rig: Rig) -> None:
    rig.ports = [{}]
    rig.tick = [1000.0]
    with pytest.raises(FatalError, match="did not show up as a serial port"):
        step(rig=rig)
    assert rig.clients == []


def test_one_bootloader_cut_short_still_names_the_dot(*, rig: Rig) -> None:
    rig.lks[LK_FIRST["lk_a"]] = bytes(512)
    assert step(rig=rig) is True
    assert rig.written == [WRITES]


def test_the_bootloader_names_which_echo_is_in_the_bootrom(*, rig: Rig) -> None:
    live = Live(port=Connection(name="/dev/one"), rig=rig)
    assert bootrom_step.payload_device(live=live) is BISCUIT
    rig.lks[LK_FIRST["lk_a"]] = b"\0product\0RADAR\0"
    rig.lks[LK_FIRST["lk_b"]] = b"\0product\0RADAR\0"
    assert bootrom_step.payload_device(live=live) is RADAR


def test_the_bootrom_unlock_downloads_nothing_and_keeps_every_step() -> None:
    unlock = UNLOCK_FROM_BOOTROM
    whole = UNLOCK_TO_FIREOS5.plan
    assert not unlock.files
    assert UNLOCK_TO_FIREOS5.files
    assert [step.image for step in unlock.plan if isinstance(step, FastbootFlash)] == [
        "bin/tz.img",
        "bin/twrp.img",
    ]
    assert len(unlock.plan) == len(whole)
    swapped = [
        (before, after) for before, after in zip(whole, unlock.plan) if before != after
    ]
    assert [after.image for _, after in swapped] == ["bin/twrp.img"]
    assert unlock.version == "1.1.0"


@pytest.mark.parametrize("tty", [False, True])
def test_the_countdown_says_when_the_short_may_come_off(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, tty: bool
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(
        name="isatty", target=bootrom_step.sys.stdout, value=lambda: tty
    )
    monkeypatch.setattr(name="sleep", target=bootrom_step.time, value=slept.append)
    bootrom_step.countdown()
    out = capsys.readouterr().out
    assert "The short may come off now" in out
    if tty:
        assert slept == [1] * bootrom_step.SHORT_WAIT
        assert out.endswith("\n")
    else:
        assert slept == [bootrom_step.SHORT_WAIT]
        assert f"continuing in {bootrom_step.SHORT_WAIT} s." in out


def test_the_dot_that_never_reaches_fastboot_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(name="in_fastboot", target=bootrom_step, value=lambda: False)
    with pytest.raises(FatalError, match="did not come back in amonet's fastboot"):
        step(rig=rig)
    assert rig.written == [WRITES]


def test_the_erase_route_waits_for_the_port_without_poking_a_payload(
    *, rig: Rig
) -> None:
    rig.ports = [{}, BOOTROM]
    rig.tick = [20.0]
    assert step(erase=lambda: "", rig=rig) is True
    assert bootrom_step.SESSION.boot0_erased is False
    assert rig.opened == [("/dev/bootrom", bootrom_step.BOOTROM_WRITE_TIMEOUT)]
    assert rig.written == [WRITES]


def test_the_erased_marker_is_in_place_for_the_first_write(*, rig: Rig) -> None:
    assert step(rig=rig) is True
    assert rig.erased == [True]
    assert bootrom_step.SESSION.boot0_erased is False


def test_the_plan_is_carried_out_through_the_payload_and_stops_at_its_reboot(
    *, rig: Rig
) -> None:
    assert step(rig=rig) is True
    assert rig.steps == [
        "handshake",
        "watchdog",
        "range checks",
        f"payload {PAYLOAD.decode()}",
        "switch 0",
        "read block 0",
        f"read {bootrom_step.TABLE_SECTORS} at 0",
        *(
            f"read {bootrom_step.LK_PRODUCT_SECTORS} at {first}"
            for first in LK_FIRST.values()
        ),
        "resolve",
        "execute live",
    ]
    assert rig.written == [WRITES]
    assert rig.opened == [
        ("/dev/bootrom", bootrom_step.BOOTROM_WRITE_TIMEOUT),
        ("/dev/bootrom", bootrom_step.BOOTROM_WRITE_TIMEOUT),
    ]


def test_the_step_count_grows_with_the_steps_the_actions_take(*, rig: Rig) -> None:
    bootrom_step.PROGRESS.step = 4
    bootrom_step.PROGRESS.steps = 9
    assert step(rig=rig) is True
    assert bootrom_step.PROGRESS.steps == 12


def test_the_v2_bootrom_unlock_clears_boot0_before_amonet_s_own_plan() -> None:
    unlock = UNLOCK_V2_FROM_BOOTROM
    assert not unlock.files
    assert unlock.plan[0] == ClearBoot0Header()
    assert unlock.plan[1:] == UNLOCK_TO_FIREOS6.plan
    assert unlock.layout is UNLOCK_TO_FIREOS6.layout
