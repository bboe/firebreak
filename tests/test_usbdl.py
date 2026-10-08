from __future__ import annotations

import enum
import struct
import sys
import types

import pytest
from conftest import FakePort, reply_read, reply_write, sent_read, sent_write, shook

from firebreak.mediatek import usbdl
from firebreak.sizes import padded

IMPORTED = frozenset({"TYPE_CHECKING"})
MEASURED = {
    "BAUD_RATE": 115200,
    "CACHE_DISABLE_SUBCOMMAND": 0xB1,
    "HANDSHAKE": ((0xA0, 0x5F), (0x0A, 0xF5), (0x50, 0xAF), (0x05, 0xFA)),
    "HANDSHAKE_TIMEOUT": 10,
    "JUMP_REGISTER": 0x1028A8,
    "MEDIATEK_VENDOR_ID": 0x0E8D,
    "MESSAGE_LIMIT": 64,
    "PAYLOAD_LOAD_ADDRESS": 0x201000,
    "PORT_POLL_INTERVAL": 0.25,
    "READ_STATUS": b"\x00\x00",
    "READ_TIMEOUT": 5,
    "WATCHDOG_DISABLE_ADDRESS": 0x10007000,
    "WATCHDOG_DISABLE_VALUE": 0x22000000,
    "WORD_MASK": 0xFFFFFFFF,
    "WORD_SIZE": 4,
    "WRITE_STATUS": b"\x00\x01",
}
MEASURED_ENUMS = {
    "BootromCommand": [
        ("EXTENDED", 0xC8),
        ("READ_WORDS", 0xD1),
        ("WRITE_WORDS", 0xD4),
    ],
    "ProductId": [("BOOTROM", 0x0003), ("PRELOADER", 0x2000)],
}


class FakeSerialError(Exception):
    pass


def fake_serial(
    *, monkeypatch: pytest.MonkeyPatch, opened: list[dict[str, object]], ports: list
) -> types.ModuleType:
    def comports() -> list:
        return ports.pop(0) if ports else []

    def serial_port(**options: object) -> object:
        opened.append(options)
        name = options["port"]
        if name == "/dev/busy":
            raise FakeSerialError(name)
        if name == "/dev/denied":
            raise PermissionError(name)
        return types.SimpleNamespace(**options)

    module = types.ModuleType("serial")
    tools = types.ModuleType("serial.tools")
    list_ports = types.ModuleType("serial.tools.list_ports")
    list_ports.comports = comports
    tools.list_ports = list_ports
    module.tools = tools
    module.Serial = serial_port
    module.SerialException = FakeSerialError
    for name, value in (
        ("serial", module),
        ("serial.tools", tools),
        ("serial.tools.list_ports", list_ports),
    ):
        monkeypatch.setitem(dic=sys.modules, name=name, value=value)
    return module


def port_entry(*, device: str, product: int | None, vendor: int | None) -> object:
    return types.SimpleNamespace(device=device, pid=product, vid=vendor)


def test_constants_match_the_measured_values() -> None:
    assert {name: getattr(usbdl, name) for name in MEASURED} == MEASURED
    assert all(sent ^ answer == 0xFF for sent, answer in usbdl.HANDSHAKE)


def test_disable_watchdog() -> None:
    bootrom, port = shook(
        replies=reply_write(
            address=usbdl.WATCHDOG_DISABLE_ADDRESS,
            words=(usbdl.WATCHDOG_DISABLE_VALUE,),
        )
    )
    bootrom.disable_watchdog()
    assert bytes(port.written) == sent_write(
        address=usbdl.WATCHDOG_DISABLE_ADDRESS, words=(usbdl.WATCHDOG_DISABLE_VALUE,)
    )
    assert port.replies == bytearray()


def test_every_constant_is_pinned_by_hand() -> None:
    assert {name for name in vars(usbdl) if name.isupper()} - IMPORTED == set(MEASURED)


def test_every_enum_is_pinned_by_hand_in_wire_order() -> None:
    found = {
        name: [
            (member, int(value)) for member, value in enumeration.__members__.items()
        ]
        for name, enumeration in vars(usbdl).items()
        if isinstance(enumeration, type)
        and issubclass(enumeration, (enum.IntEnum, enum.IntFlag))
    }
    assert found == MEASURED_ENUMS


def test_handshake_flushes_and_repeats_its_first_step() -> None:
    bootrom, port = shook(replies=b"\x11\x5f\xf5\xaf\xfa")
    bootrom.handshake()
    assert bytes(port.written) == b"\xa0\xa0\x0a\x50\x05"
    assert port.flushes == 1


def test_handshake_gives_up_without_an_answer(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="HANDSHAKE_TIMEOUT", target=usbdl, value=0)
    bootrom, _ = shook(replies=b"")
    with pytest.raises(expected_exception=usbdl.HandshakeTimeoutError, match="replug"):
        bootrom.handshake()


def test_handshake_refuses_a_wrong_later_answer() -> None:
    bootrom, _ = shook(replies=b"\x5f\xf6")
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="handshake step 0x0a"
    ):
        bootrom.handshake()


def test_handshake_walks_the_four_steps() -> None:
    bootrom, port = shook(replies=b"\x5f\xf5\xaf\xfa")
    bootrom.handshake()
    assert bytes(port.written) == b"\xa0\x0a\x50\x05"
    assert port.flushes == 0
    assert port.replies == bytearray()


def test_mediatek_ports_keeps_only_mediatek(*, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_serial(
        monkeypatch=monkeypatch,
        opened=[],
        ports=[
            [
                port_entry(device="/dev/other", product=0x1234, vendor=0x1111),
                port_entry(device="/dev/bootrom", product=0x0003, vendor=0x0E8D),
                port_entry(device="/dev/preloader", product=0x2000, vendor=0x0E8D),
                port_entry(device="/dev/unknown", product=None, vendor=0x0E8D),
            ]
        ],
    )
    assert usbdl.mediatek_ports() == {
        "/dev/bootrom": 0x0003,
        "/dev/preloader": 0x2000,
        "/dev/unknown": None,
    }


def test_padded_rounds_up_to_whole_words() -> None:
    assert [padded(length=length, unit=usbdl.WORD_SIZE) for length in range(9)] == [
        0,
        4,
        4,
        4,
        4,
        8,
        8,
        8,
        8,
    ]


def test_payload_words_pads_and_keeps_the_file_order() -> None:
    assert usbdl.payload_words(data=b"\x01\x02\x03\x04") == (0x04030201,)
    assert usbdl.payload_words(data=b"\x01\x02") == (0x00000201,)
    assert usbdl.payload_words(data=b"") == ()


def test_read_exactly_bounds_the_read_and_not_only_a_stall() -> None:
    port = FakePort(replies=b"abcd", short=True)
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="read 1 of 4 bytes"
    ):
        usbdl.Connection(port=port, timeout=0).read_exactly(label="four", length=4)


def test_read_exactly_cuts_a_long_partial_read_out_of_its_message() -> None:
    port = FakePort(replies=b"x" * 200)
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError,
        match=f"got b'{'x' * usbdl.MESSAGE_LIMIT}'[.][.][.]",
    ):
        usbdl.Connection(port=port, timeout=0).read_exactly(label="long", length=400)


def test_read_exactly_gathers_short_reads() -> None:
    port = FakePort(replies=b"abcd", short=True)
    assert (
        usbdl.Connection(port=port, timeout=usbdl.READ_TIMEOUT).read_exactly(
            label="four", length=4
        )
        == b"abcd"
    )


def test_read_exactly_reports_a_timeout() -> None:
    port = FakePort(replies=b"ab")
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="read 2 of 4 bytes"
    ):
        usbdl.Connection(port=port, timeout=0).read_exactly(label="four", length=4)


def test_read_words() -> None:
    bootrom, port = shook(replies=reply_read(address=0x1234, values=(0xAABBCCDD, 1)))
    assert bootrom.read_words(address=0x1234, count=2) == (0xAABBCCDD, 1)
    assert bytes(port.written) == sent_read(address=0x1234, count=2)


def test_read_words_refuses_a_wrong_status() -> None:
    bootrom, _ = shook(
        replies=bytes([usbdl.BootromCommand.READ_WORDS])
        + struct.pack(">II", 0x1234, 1)
        + usbdl.WRITE_STATUS
    )
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="argument status"
    ):
        bootrom.read_words(address=0x1234, count=1)


def test_run_payload_uploads_it_and_skips_the_jump_status() -> None:
    words = usbdl.payload_words(data=b"payload!")
    bootrom, port = shook(
        replies=reply_write(address=usbdl.PAYLOAD_LOAD_ADDRESS, words=words)
        + reply_write(
            address=usbdl.JUMP_REGISTER, end=False, words=(usbdl.PAYLOAD_LOAD_ADDRESS,)
        )
    )
    bootrom.run_payload(payload=b"payload!")
    assert bytes(port.written) == sent_write(
        address=usbdl.PAYLOAD_LOAD_ADDRESS, words=words
    ) + sent_write(address=usbdl.JUMP_REGISTER, words=(usbdl.PAYLOAD_LOAD_ADDRESS,))
    assert port.replies == bytearray()


def test_send_extended_discards_three_bytes() -> None:
    bootrom, port = shook(
        replies=bytes([usbdl.BootromCommand.EXTENDED, usbdl.CACHE_DISABLE_SUBCOMMAND])
        + b"\x01\x02\x03"
    )
    bootrom.disable_caches()
    assert bytes(port.written) == bytes([
        usbdl.BootromCommand.EXTENDED,
        usbdl.CACHE_DISABLE_SUBCOMMAND,
    ])
    assert port.replies == bytearray()


def test_verify_says_what_it_sent() -> None:
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError,
        match=r"step: sent b'\\x01', expected b'\\x01', got b'\\x02'",
    ):
        usbdl.verify(expected=b"\x01", label="step", received=b"\x02", sent=b"\x01")


def test_write_words_names_the_word_a_mismatch_landed_on() -> None:
    bootrom, _ = shook(replies=reply_write(address=0x1234, end=False, words=(7, 0)))
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="word 1 at 0x1238"
    ):
        bootrom.write_words(address=0x1234, words=(7, 8))


def test_write_words_refuses_a_bad_echo() -> None:
    bootrom, _ = shook(replies=bytes([usbdl.BootromCommand.WRITE_WORDS]) + b"\0\0\0\0")
    with pytest.raises(expected_exception=usbdl.ProtocolMismatchError, match="address"):
        bootrom.write_words(address=0x1234, words=(0,))


def test_write_words_sends_each_word() -> None:
    bootrom, port = shook(replies=reply_write(address=0x1234, words=(7, 8)))
    bootrom.write_words(address=0x1234, words=(7, 8))
    assert bytes(port.written) == sent_write(address=0x1234, words=(7, 8))
    assert port.replies == bytearray()
