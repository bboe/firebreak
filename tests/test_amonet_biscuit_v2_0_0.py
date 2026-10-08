from __future__ import annotations

import enum
import struct

import pytest
from conftest import FakePort

from firebreak.amonet import biscuit_v2_0_0
from firebreak.amonet.payload import PAYLOAD_MAGIC
from firebreak.mediatek.usbdl import PAYLOAD_LOAD_ADDRESS, ProtocolMismatchError

BLOCK = bytes(range(256)) * 2
FLUSH = b"flsh"
IMPORTED = frozenset({"BLOCK_SIZE", "PAYLOAD_LOAD_ADDRESS", "RPMB_SIZE"})
MEASURED = {"FLUSH_LENGTH": 4, "MAXIMUM_BLOCKS": 64}
MEASURED_ENUMS = {
    "BiscuitCommand": [
        ("WRITE_BLOCKS", 0x1003),
        ("READ_BLOCKS", 0x1004),
        ("READ_MEMORY", 0x5000),
    ],
}


def framed(*, arguments: tuple[int, ...] = (), command: int) -> bytes:
    return struct.pack(f">{2 + len(arguments)}I", PAYLOAD_MAGIC, command, *arguments)


def payload_port(*, replies: bytes = b"") -> tuple[biscuit_v2_0_0.Client, FakePort]:
    port = FakePort(replies=replies)
    return biscuit_v2_0_0.Client(port=port, timeout=0), port


def test_check_block_count() -> None:
    biscuit_v2_0_0.check_block_count(count=1)
    biscuit_v2_0_0.check_block_count(count=64)
    for count in (0, 65):
        with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
            biscuit_v2_0_0.check_block_count(count=count)


def test_every_constant_is_pinned_by_hand() -> None:
    names = {name for name in vars(biscuit_v2_0_0) if name.isupper()}
    assert names - IMPORTED == set(MEASURED)
    for name, value in MEASURED.items():
        assert getattr(biscuit_v2_0_0, name) == value, name


def test_every_enum_is_pinned_by_hand_in_wire_order() -> None:
    found = {
        name: [
            (member, int(value)) for member, value in enumeration.__members__.items()
        ]
        for name, enumeration in vars(biscuit_v2_0_0).items()
        if isinstance(enumeration, type)
        and issubclass(enumeration, enum.IntEnum)
        and enumeration.__module__ == biscuit_v2_0_0.__name__
    }
    assert found == MEASURED_ENUMS


def test_read_block_flushes_the_pipe() -> None:
    payload, port = payload_port(replies=BLOCK + FLUSH)
    assert payload.read_block(index=7) == BLOCK
    assert bytes(port.written) == framed(arguments=(7,), command=0x1000) + framed(
        arguments=(PAYLOAD_LOAD_ADDRESS, 4), command=0x5000
    )
    assert port.replies == bytearray()


def test_read_blocks() -> None:
    payload, port = payload_port(replies=BLOCK * 2 + FLUSH)
    assert payload.read_blocks(count=2, index=9) == BLOCK * 2
    assert bytes(port.written) == framed(arguments=(9, 2), command=0x1004) + framed(
        arguments=(PAYLOAD_LOAD_ADDRESS, 4), command=0x5000
    )
    assert port.replies == bytearray()
    for count in (0, 65):
        with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
            payload.read_blocks(count=count, index=0)


def test_read_rpmb() -> None:
    payload, port = payload_port(replies=b"AMZN" + bytes(252) + FLUSH)
    assert payload.read_rpmb() == b"AMZN" + bytes(252)
    assert bytes(port.written) == framed(command=0x2000) + framed(
        arguments=(PAYLOAD_LOAD_ADDRESS, 4), command=0x5000
    )


def test_rpmb_read_that_gets_nothing_names_the_rpmb() -> None:
    payload, _ = payload_port()
    with pytest.raises(expected_exception=ProtocolMismatchError, match="RPMB"):
        payload.read_rpmb()


def test_the_client_is_tied_to_one_payload() -> None:
    assert biscuit_v2_0_0.Client.SHA256 == (
        "51401ef600f464ea3c32dada3c131e6b3776be2d6ccdf801ba94f1c3358ccf88"
    )
    assert biscuit_v2_0_0.Client.maximum_blocks == 64


def test_write_blocks() -> None:
    payload, port = payload_port(replies=b"\xd0\xd0\xd0\xd0")
    payload.write_blocks(data=BLOCK * 3, index=5)
    assert bytes(port.written) == framed(arguments=(5, 3), command=0x1003) + BLOCK * 3
    with pytest.raises(expected_exception=ValueError, match="whole number of blocks"):
        payload.write_blocks(data=BLOCK + b"x", index=5)
    with pytest.raises(expected_exception=ValueError, match="1 to 64 blocks"):
        payload.write_blocks(data=BLOCK * 65, index=5)
