from __future__ import annotations

import types
from typing import TYPE_CHECKING

import pytest

from firebreak import __main__ as main
from firebreak.amonet.payload import BLOCK_SIZE, PAYLOAD_MAGIC, Command
from firebreak.bootrom import USER_AREA_SIGNATURE
from firebreak.mediatek.usbdl import (
    HandshakeTimeoutError,
    ProductId,
    ProtocolMismatchError,
    UsbdlError,
)
from firebreak.plan import Action

if TYPE_CHECKING:
    import pathlib

    from typing_extensions import Self

ACTIONS = (
    Action(data=b"h", kind="ClearBoot0Header", label="clear", length=1, offset=0),
    Action(kind="ShuffleGpt", label="already has room", length=0),
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
BOOTROM = {"/dev/bootrom": ProductId.BOOTROM}
BOTH = {
    "/dev/a-preloader": ProductId.PRELOADER,
    "/dev/b-bootrom": ProductId.BOOTROM,
}
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
        self.name = name
        self.writes: list[bytes] = []

    def close(self) -> None:
        self.closed = True

    def write(self, *, data: bytes) -> None:
        self.writes.append(data)


class Live:
    def __init__(self, *, rig: Rig) -> None:
        self.rig = rig

    def __str__(self) -> str:
        return "live"

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
        return Live(rig=self.rig)


@pytest.fixture
def rig(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Rig:
    found = Rig(
        amonet=tmp_path / "amonet",
        clients=[],
        connections=[],
        erased=[],
        exploit_error=None,
        handshakes=[],
        not_ready=False,
        now=[0.0],
        opened=[],
        payload=tmp_path / "payload.bin",
        ports=[BOOTROM],
        refusals=0,
        resolved=ACTIONS,
        signature=USER_AREA_SIGNATURE,
        steps=[],
        tick=[0.5],
        write_error=None,
        written=[],
    )
    found.payload.write_bytes(data=PAYLOAD)
    main.ERASED.parent.mkdir(parents=True)

    def executed(*, actions: tuple[Action, ...], payload: Live) -> None:
        found.erased.append(main.ERASED.exists())
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
    monkeypatch.setattr(name="Bootrom", target=main, value=Client)
    monkeypatch.setattr(name="start_payload", target=main, value=started)
    monkeypatch.setattr(
        name="countdown", target=main, value=lambda: found.steps.append("countdown")
    )
    monkeypatch.setattr(
        name="getvar", target=main, value=lambda **_: main.LK.FIREOS5.value
    )
    monkeypatch.setattr(name="in_fastboot", target=main, value=lambda: True)
    monkeypatch.setattr(name="mediatek_ports", target=main, value=ports)
    monkeypatch.setattr(name="open_serial_port", target=main, value=opened)
    monkeypatch.setattr(name="resolve", target=main, value=resolved)
    monkeypatch.setattr(
        name="time",
        target=main,
        value=types.SimpleNamespace(monotonic=monotonic, sleep=lambda _: None),
    )
    monkeypatch.setattr(name="path", target=main.sys, value=[*main.sys.path])
    monkeypatch.setattr(
        name="defeat",
        target=main.range_check,
        value=lambda **_: found.steps.append("range checks"),
    )
    monkeypatch.setattr(name="execute", target=main.bootrom, value=executed)
    monkeypatch.setattr(name="read", target=main.bootrom, value=lambda **_: b"table")
    return found


def started(*, bootrom: Client, client: type, payload: bytes) -> Live:
    assert client is main.Client
    if bootrom.rig.not_ready:
        message = "the payload's ready pattern: expected b'\\xb1', got b''"
        raise main.NotReadyError(message)
    return bootrom.start_payload(payload=payload)


def step(*, erase: object = None, rig: Rig, wheel: pathlib.Path | None = None) -> bool:
    return main.bootrom_step(
        amonet=rig.amonet, erase=erase, payload=rig.payload, wheel=wheel
    )


def test_a_bootrom_port_is_taken_over_a_preloader_in_the_same_pass(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    main.SESSION.short = True
    rig.ports = [{}, BOTH]
    assert step(rig=rig) is True
    assert rig.opened == [("/dev/b-bootrom", main.BOOTROM_WRITE_TIMEOUT)]
    assert "missed" not in capsys.readouterr().out


def test_a_bootrom_that_does_not_answer_as_one_stops_the_run(*, rig: Rig) -> None:
    rig.handshakes = [ProtocolMismatchError("sent 0xa0, read b'\\x00'")]
    with pytest.raises(SystemExit, match="did not answer as one"):
        step(rig=rig)
    assert rig.written == []
    assert rig.clients[0].port.closed is True


def test_a_bootrom_that_never_answers_a_handshake_stops_the_run(*, rig: Rig) -> None:
    rig.handshakes = [HandshakeTimeoutError("no answer within 10 seconds")] * 4
    rig.tick = [100.0]
    with pytest.raises(SystemExit, match="never answered a handshake"):
        step(rig=rig)
    assert rig.steps.count("handshake") == 1
    assert rig.written == []


def test_a_dead_emmc_stops_the_run_before_anything_is_written(*, rig: Rig) -> None:
    rig.signature = b"\x00\x00"
    with pytest.raises(SystemExit, match="eMMC did not answer: block 0"):
        step(rig=rig)
    assert rig.written == []
    assert not main.ERASED.exists()


def test_a_dead_emmc_with_the_short_on_blames_the_short(*, rig: Rig) -> None:
    main.SESSION.short = True
    rig.signature = None
    with pytest.raises(SystemExit, match="most likely because the short"):
        step(rig=rig)
    assert rig.steps[-2:] == ["switch 0", "read block 0"]
    assert rig.written == []


def test_a_failed_erase_stops_the_run_with_its_own_message(*, rig: Rig) -> None:
    with pytest.raises(SystemExit, match="boot0 did not erase"):
        step(erase=lambda: "boot0 did not erase", rig=rig)
    assert main.ERASED.exists()
    assert rig.clients == []


def test_a_failed_exploit_stops_the_run_with_nothing_written(*, rig: Rig) -> None:
    rig.exploit_error = OSError("device not configured")
    with pytest.raises(SystemExit, match="exploit did not go through"):
        step(rig=rig)
    assert rig.written == []
    assert not main.ERASED.exists()


def test_a_failure_after_the_erase_says_only_boot0_was_erased(*, rig: Rig) -> None:
    rig.exploit_error = OSError("device not configured")
    with pytest.raises(SystemExit) as failure:
        step(erase=lambda: "", rig=rig)
    said = str(failure.value).replace("\n", " ")
    assert "Only boot0 was erased" in said
    assert "Nothing was written" not in said


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
    main.SESSION.short = True
    rig.handshakes = [HandshakeTimeoutError("no answer within 10 seconds")]
    with pytest.raises(SystemExit, match="bootrom did not answer"):
        step(rig=rig)
    assert rig.written == []


def test_a_missed_short_is_counted_and_the_run_keeps_waiting(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    main.SESSION.short = True
    rig.ports = [{}, PRELOADER, BOOTROM]
    assert step(rig=rig) is True
    assert "Short 1 missed" in capsys.readouterr().out
    assert rig.steps[:3] == ["handshake", "watchdog", "countdown"]
    assert rig.written == [WRITES]
    assert not main.ERASED.exists()


def test_a_payload_that_never_starts_with_the_short_on_blames_the_short(
    *, rig: Rig
) -> None:
    main.SESSION.short = True
    rig.not_ready = True
    with pytest.raises(SystemExit, match="most likely because the short"):
        step(rig=rig)
    assert rig.written == []


def test_a_plan_that_does_not_resolve_stops_before_anything_is_written(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def unresolvable(**_: object) -> None:
        message = "biscuit has no lk_c partition"
        raise KeyError(message)

    main.SESSION.short = True
    monkeypatch.setattr(name="resolve", target=main, value=unresolvable)
    with pytest.raises(SystemExit, match="does not fit this Dot: biscuit has no"):
        step(rig=rig)
    assert rig.written == []
    assert not main.ERASED.exists()


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
    main.ERASED.touch()
    rig.ports = [{}, {}, PRELOADER]
    wheel = tmp_path / "pyserial.whl"
    assert step(rig=rig, wheel=wheel) is False
    assert not main.ERASED.exists()
    assert rig.written == []
    assert str(wheel) in main.sys.path
    assert "boot0 is intact" in capsys.readouterr().out


def test_a_second_missed_short_warns_again_and_counts_it(
    *, capsys: pytest.CaptureFixture[str], rig: Rig
) -> None:
    main.SESSION.short = True
    rig.ports = [{}, PRELOADER, {}, PRELOADER, BOOTROM]
    assert step(rig=rig) is True
    said = capsys.readouterr().out
    assert "Short 1 missed" in said
    assert "Short 2 missed" in said


def test_a_table_that_cannot_be_read_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    def unreadable(**_: object) -> None:
        message = "device not configured"
        raise OSError(message)

    monkeypatch.setattr(name="read", target=main.bootrom, value=unreadable)
    with pytest.raises(SystemExit, match="partition table could not be read"):
        step(rig=rig)
    assert rig.written == []
    assert not main.ERASED.exists()


def test_no_port_at_all_stops_the_run_with_the_port_help(*, rig: Rig) -> None:
    rig.ports = [{}]
    rig.tick = [1000.0]
    with pytest.raises(SystemExit, match="did not show up as a serial port"):
        step(rig=rig)
    assert rig.clients == []


def test_the_dot_that_never_reaches_fastboot_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, rig: Rig
) -> None:
    monkeypatch.setattr(name="in_fastboot", target=main, value=lambda: False)
    with pytest.raises(SystemExit, match=r"did not come back in v1\.1\.0's fastboot"):
        step(rig=rig)
    assert rig.written == [WRITES]


def test_the_erase_route_waits_for_the_port_without_poking_a_payload(
    *, rig: Rig
) -> None:
    rig.ports = [{}, BOOTROM]
    rig.tick = [20.0]
    assert step(erase=lambda: "", rig=rig) is True
    assert not main.ERASED.exists()
    assert rig.opened == [("/dev/bootrom", main.BOOTROM_WRITE_TIMEOUT)]
    assert rig.written == [WRITES]


def test_the_erased_marker_is_in_place_for_the_first_write(*, rig: Rig) -> None:
    assert step(rig=rig) is True
    assert rig.erased == [True]
    assert not main.ERASED.exists()


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
        "resolve",
        "execute live",
    ]
    assert rig.written == [WRITES]
    assert rig.opened == [
        ("/dev/bootrom", main.POKE_WRITE_TIMEOUT),
        ("/dev/bootrom", main.BOOTROM_WRITE_TIMEOUT),
    ]


def test_the_resume_poke_reboots_every_mediatek_port(*, rig: Rig) -> None:
    rig.ports = [{**BOOTROM, **PRELOADER}]
    assert step(rig=rig) is True
    assert [connection.writes for connection in rig.connections[:2]] == [
        [REBOOT_COMMAND],
        [REBOOT_COMMAND],
    ]
    assert rig.opened[:2] == [
        ("/dev/bootrom", main.POKE_WRITE_TIMEOUT),
        ("/dev/preloader", main.POKE_WRITE_TIMEOUT),
    ]


def test_the_resume_poke_waits_for_the_payload_to_go(*, rig: Rig) -> None:
    rig.ports = [BOOTROM, BOOTROM, {}, BOOTROM]
    assert step(rig=rig) is True
    assert rig.steps.count("handshake") == 1


def test_the_step_count_grows_with_the_actions(*, rig: Rig) -> None:
    main.PROGRESS.step = 4
    main.PROGRESS.steps = 9
    assert step(rig=rig) is True
    assert main.PROGRESS.steps == 12
