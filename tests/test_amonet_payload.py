from __future__ import annotations

import enum
import hashlib
import struct

import pytest
from conftest import FakePort, reply_write, sent_write, shook

from firebreak.amonet import payload as amonet_payload
from firebreak.mediatek import usbdl

BLOCK = bytes(range(256)) * 2
IMPORTED = frozenset({"RPMB_SIZE", "TYPE_CHECKING"})
MEASURED = {
    "ACKNOWLEDGEMENT": b"\xd0\xd0\xd0\xd0",
    "BLOCK_SIZE": 0x200,
    "PAYLOAD_MAGIC": 0xF00DD00D,
    "PAYLOAD_READY": b"\xb1\xb2\xb3\xb4",
}
MEASURED_ENUMS = {
    "Command": [
        ("READ_BLOCK", 0x1000),
        ("WRITE_BLOCK", 0x1001),
        ("SWITCH_PARTITION", 0x1002),
        ("READ_RPMB", 0x2000),
        ("WRITE_RPMB", 0x2001),
        ("REBOOT", 0x3000),
    ],
}
SYNTHETIC = b"payload!"


class Synthetic(amonet_payload.Payload):
    SHA256 = hashlib.sha256(SYNTHETIC).hexdigest()


def framed(*, arguments: tuple[int, ...] = (), command: int) -> bytes:
    return struct.pack(
        f">{2 + len(arguments)}I", amonet_payload.PAYLOAD_MAGIC, command, *arguments
    )


def jumped(*, ready: bytes) -> tuple[usbdl.Bootrom, FakePort]:
    words = usbdl.payload_words(data=SYNTHETIC)
    return shook(
        replies=reply_write(address=usbdl.PAYLOAD_LOAD_ADDRESS, words=words)
        + reply_write(
            address=usbdl.JUMP_REGISTER, end=False, words=(usbdl.PAYLOAD_LOAD_ADDRESS,)
        )
        + ready
    )


def payload_port(*, replies: bytes = b"") -> tuple[amonet_payload.Payload, FakePort]:
    port = FakePort(replies=replies)
    return amonet_payload.Payload(port=port, timeout=0), port


def test_every_constant_is_pinned_by_hand() -> None:
    assert {name for name in vars(amonet_payload) if name.isupper()} - IMPORTED == set(
        MEASURED
    )
    for name, value in MEASURED.items():
        assert getattr(amonet_payload, name) == value, name


def test_every_enum_is_pinned_by_hand_in_wire_order() -> None:
    found = {
        name: [
            (member, int(value)) for member, value in enumeration.__members__.items()
        ]
        for name, enumeration in vars(amonet_payload).items()
        if isinstance(enumeration, type) and issubclass(enumeration, enum.IntEnum)
    }
    assert found == MEASURED_ENUMS


def test_payload_reboots() -> None:
    payload, port = payload_port()
    payload.reboot()
    assert bytes(port.written) == framed(command=0x3000)
    assert port.replies == bytearray()


def test_payload_switch_partition() -> None:
    payload, port = payload_port()
    payload.switch_partition(partition=1)
    assert bytes(port.written) == framed(arguments=(1,), command=0x1002)
    assert port.replies == bytearray()


def test_payload_write_block() -> None:
    payload, port = payload_port(replies=amonet_payload.ACKNOWLEDGEMENT)
    payload.write_block(data=BLOCK, index=3)
    assert bytes(port.written) == framed(arguments=(3,), command=0x1001) + BLOCK
    with pytest.raises(expected_exception=ValueError, match="512 bytes, not 4"):
        payload.write_block(data=b"four", index=3)


def test_payload_write_block_refuses_a_bad_acknowledgement() -> None:
    payload, _ = payload_port(replies=b"nope")
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="write of block 3"
    ):
        payload.write_block(data=BLOCK, index=3)


def test_payload_write_rpmb() -> None:
    payload, port = payload_port()
    payload.write_rpmb(data=bytes(256))
    assert bytes(port.written) == framed(command=0x2001) + bytes(256)
    with pytest.raises(expected_exception=ValueError, match="256 bytes, not 4"):
        payload.write_rpmb(data=bytes(4))


def test_start_payload_refuses_a_payload_its_client_does_not_speak() -> None:
    bootrom, port = shook(replies=b"")
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError,
        match=f"SHA-256 {hashlib.sha256(b'other').hexdigest()}",
    ):
        amonet_payload.start_payload(
            bootrom=bootrom, client=Synthetic, payload=b"other"
        )
    assert bytes(port.written) == b""


def test_start_payload_refuses_a_wrong_ready_pattern() -> None:
    bootrom, _ = jumped(ready=b"\xb1\xb2\xb3\xff")
    with pytest.raises(
        expected_exception=amonet_payload.NotReadyError, match="ready pattern"
    ):
        amonet_payload.start_payload(
            bootrom=bootrom, client=Synthetic, payload=SYNTHETIC
        )


def test_start_payload_returns_the_client_on_the_same_port() -> None:
    bootrom, port = jumped(ready=amonet_payload.PAYLOAD_READY)
    payload = amonet_payload.start_payload(
        bootrom=bootrom, client=Synthetic, payload=SYNTHETIC
    )
    assert isinstance(payload, Synthetic)
    assert payload.port is port
    words = usbdl.payload_words(data=SYNTHETIC)
    assert bytes(port.written) == sent_write(
        address=usbdl.PAYLOAD_LOAD_ADDRESS, words=words
    ) + sent_write(address=usbdl.JUMP_REGISTER, words=(usbdl.PAYLOAD_LOAD_ADDRESS,))
    assert port.replies == bytearray()
