from __future__ import annotations

import enum
import hashlib
import struct

import pytest
from conftest import FakePort

from firebreak.amonet.payload import PAYLOAD_MAGIC, NotReadyError
from firebreak.kamakiri import donut_v1_0_0
from firebreak.mediatek.usbdl import (
    PAYLOAD_LOAD_ADDRESS,
    Connection,
    ProtocolMismatchError,
)

ACK = b"\xd0\xd0\xd0\xd0"
BLOCK = bytes(range(256)) * 2
IMPORTED = frozenset({
    "ACKNOWLEDGEMENT",
    "BLOCK_SIZE",
    "PAYLOAD_LOAD_ADDRESS",
    "RPMB_SIZE",
})
MEASURED = {
    "MAXIMUM_BLOCKS": 64,
    "STAGE1_SHA256": "dd5dddcde43eb9aec57351e9702226a4a47a560106d6d9fd62aa0cf9233617d6",
    "STAGE2_READY": b"\xb1\xb2\xb3\xb4",
}
MEASURED_ENUMS = {
    "DonutCommand": [
        ("KICK_WATCHDOG", 0x3001),
        ("LOAD_STAGE2", 0x4000),
        ("READ_BLOCKS", 0x1004),
        ("READ_MEMORY", 0x5000),
        ("START_STAGE2", 0x4001),
        ("WRITE_BLOCKS", 0x1003),
    ],
}
STAGE2 = b"stage two, the real one"


class Synthetic(donut_v1_0_0.Client):
    SHA256 = hashlib.sha256(STAGE2).hexdigest()


def framed(*, arguments: tuple[int, ...] = (), command: int) -> bytes:
    return struct.pack(f">{2 + len(arguments)}I", PAYLOAD_MAGIC, command, *arguments)


def payload_port(*, replies: bytes = b"") -> tuple[donut_v1_0_0.Client, FakePort]:
    port = FakePort(replies=replies)
    return donut_v1_0_0.Client(port=port, timeout=0), port


def stage1_port(*, replies: bytes = b"") -> tuple[Connection, FakePort]:
    port = FakePort(replies=replies)
    return Connection(port=port, timeout=0), port


def test_check_block_count() -> None:
    donut_v1_0_0.check_block_count(count=1)
    donut_v1_0_0.check_block_count(count=64)
    for count in (0, 65):
        with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
            donut_v1_0_0.check_block_count(count=count)


def test_every_constant_is_pinned_by_hand() -> None:
    names = {name for name in vars(donut_v1_0_0) if name.isupper()}
    assert names - IMPORTED == set(MEASURED)
    for name, value in MEASURED.items():
        assert getattr(donut_v1_0_0, name) == value, name


def test_every_enum_is_pinned_by_hand() -> None:
    found = {
        name: [
            (member, int(value)) for member, value in enumeration.__members__.items()
        ]
        for name, enumeration in vars(donut_v1_0_0).items()
        if isinstance(enumeration, type)
        and issubclass(enumeration, enum.IntEnum)
        and enumeration.__module__ == donut_v1_0_0.__name__
    }
    assert found == MEASURED_ENUMS


def test_kick_asks_for_nothing_back() -> None:
    payload, port = payload_port()
    payload.kick()
    assert bytes(port.written) == framed(command=0x3001)
    assert port.replies == bytearray()


def test_read_block_needs_no_flush_where_biscuit_s_does() -> None:
    payload, port = payload_port(replies=BLOCK)
    assert payload.read_block(index=7) == BLOCK
    assert bytes(port.written) == framed(arguments=(7,), command=0x1000)
    assert port.replies == bytearray()


def test_read_blocks() -> None:
    payload, port = payload_port(replies=BLOCK * 2)
    assert payload.read_blocks(count=2, index=9) == BLOCK * 2
    assert bytes(port.written) == framed(arguments=(9, 2), command=0x1004)
    for count in (0, 65):
        with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
            payload.read_blocks(count=count, index=0)


def test_read_rpmb() -> None:
    payload, port = payload_port(replies=b"AMZN" + bytes(252))
    assert payload.read_rpmb() == b"AMZN" + bytes(252)
    assert bytes(port.written) == framed(command=0x2000)


def test_rpmb_read_that_gets_nothing_names_the_rpmb() -> None:
    payload, _ = payload_port()
    with pytest.raises(expected_exception=ProtocolMismatchError, match="RPMB"):
        payload.read_rpmb()


def test_start_stage2_hands_back_a_client_on_the_same_port() -> None:
    stage1, port = stage1_port(replies=ACK + donut_v1_0_0.STAGE2_READY)
    live = donut_v1_0_0.start_stage2(client=Synthetic, stage1=stage1, stage2=STAGE2)
    assert isinstance(live, donut_v1_0_0.Client)
    assert live.port is port
    assert bytes(port.written) == (
        framed(arguments=(PAYLOAD_LOAD_ADDRESS, len(STAGE2)), command=0x4000)
        + STAGE2
        + framed(arguments=(PAYLOAD_LOAD_ADDRESS,), command=0x4001)
    )
    assert port.replies == bytearray()


def test_start_stage2_refuses_a_payload_it_does_not_speak() -> None:
    stage1, _ = stage1_port()
    with pytest.raises(expected_exception=ProtocolMismatchError, match="SHA-256"):
        donut_v1_0_0.start_stage2(
            client=Synthetic, stage1=stage1, stage2=b"some other payload"
        )


def test_start_stage2_says_when_stage1_will_not_take_it() -> None:
    stage1, _ = stage1_port(replies=b"nope")
    with pytest.raises(
        expected_exception=ProtocolMismatchError, match="did not take stage 2"
    ):
        donut_v1_0_0.start_stage2(client=Synthetic, stage1=stage1, stage2=STAGE2)


def test_start_stage2_says_when_stage2_never_answers() -> None:
    stage1, _ = stage1_port(replies=ACK + b"\x01\x02\x03\x04")
    with pytest.raises(expected_exception=NotReadyError, match="ready pattern"):
        donut_v1_0_0.start_stage2(client=Synthetic, stage1=stage1, stage2=STAGE2)


def test_the_client_is_tied_to_one_payload() -> None:
    assert donut_v1_0_0.Client.SHA256 == (
        "f17b6a7a537f1983d90c162f80d6cc042cc16ba7f22828448b8713b4b97f47fd"
    )
    assert donut_v1_0_0.Client.maximum_blocks == 64


def test_write_blocks() -> None:
    payload, port = payload_port(replies=ACK)
    payload.write_blocks(data=BLOCK * 3, index=5)
    assert bytes(port.written) == framed(arguments=(5, 3), command=0x1003) + BLOCK * 3
    with pytest.raises(expected_exception=ValueError, match="whole number of blocks"):
        payload.write_blocks(data=BLOCK + b"x", index=5)
    with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
        payload.write_blocks(data=BLOCK * 65, index=5)
