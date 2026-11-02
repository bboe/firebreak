from __future__ import annotations

import struct

import pytest
from conftest import FakePort, reply_da, reply_read, sent_da, sent_read

from firebreak.amonet.payload import NotReadyError
from firebreak.mediatek import kamakiri, usbdl

CODING = bytes(range(7))
SEND = 0x1234
STAGE1 = b"stage one"


class FakeUsb:
    def __init__(self) -> None:
        self.coding = CODING
        self.descriptors = 0
        self.walked: list[int] = []

    def configuration_descriptor(self) -> bytes:
        self.descriptors += 1
        return bytes(9)

    def line_coding(self) -> bytes:
        return self.coding

    def set_line_coding(self, *, data: bytes) -> None:
        assert data[:7] == CODING
        assert data[7] == 0
        self.walked.append(struct.unpack("<I", data[8:])[0])


def nudge_replies() -> bytes:
    return reply_da(data=b"\0", length=1, offset=0) + reply_read(
        address=kamakiri.WATCHDOG_RESTART, values=(0,)
    )


def nudge_sent() -> bytes:
    return sent_da(length=1, offset=0) + sent_read(
        address=kamakiri.WATCHDOG_RESTART, count=1
    )


def started(*, ready: bytes = kamakiri.STAGE1_READY) -> tuple[FakePort, FakeUsb]:
    replies = (
        nudge_replies()
        + reply_da(
            data=struct.pack("<I", SEND),
            length=4,
            offset=kamakiri.POINTER_USBDL - kamakiri.NEAR,
        )
        + nudge_replies()
        + reply_da(
            length=len(STAGE1),
            offset=kamakiri.PAYLOAD_ADDRESS - kamakiri.NEAR,
            write=True,
        )
        + nudge_replies()
        + reply_da(
            end=False,
            length=4,
            offset=SEND + kamakiri.POINTER_SKEW - kamakiri.NEAR,
            write=True,
        )
        + ready
    )
    return FakePort(replies=replies), FakeUsb()


def test_a_near_offset_walks_one_step_further_and_subtracts_nothing() -> None:
    port = FakePort(
        replies=nudge_replies() + reply_da(data=b"wxyz", length=4, offset=0)
    )
    usb = FakeUsb()
    exploit = kamakiri.Exploit(bootrom=usbdl.Bootrom(port=port, timeout=0), port=usb)
    assert exploit.read(length=4, offset=0) == b"wxyz"
    assert usb.walked == [
        kamakiri.POINTER_DA + offset for offset in kamakiri.ASCENT
    ] + [kamakiri.POINTER_DA + offset for offset in kamakiri.LONG_DESCENT]
    assert bytes(port.written) == nudge_sent() + sent_da(length=4, offset=0)


def test_every_control_transfer_is_paired_with_a_descriptor_read() -> None:
    port, usb = started()
    kamakiri.start_stage1(
        bootrom=usbdl.Bootrom(port=port, timeout=0), port=usb, stage1=STAGE1
    )
    assert usb.descriptors == len(usb.walked)


def test_nudge_swallows_a_bootrom_that_will_not_answer_it() -> None:
    port = FakePort()
    exploit = kamakiri.Exploit(
        bootrom=usbdl.Bootrom(port=port, timeout=0), port=FakeUsb()
    )
    exploit.nudge()
    assert bytes(port.written) == bytes([usbdl.BootromCommand.COMMAND_DA])


def test_stage1_that_never_answers_is_named() -> None:
    port, usb = started(ready=b"\x00\x00\x00\x00")
    with pytest.raises(expected_exception=NotReadyError, match="ready pattern"):
        kamakiri.start_stage1(
            bootrom=usbdl.Bootrom(port=port, timeout=0), port=usb, stage1=STAGE1
        )


def test_stage1_too_large_for_its_room_is_refused() -> None:
    _, usb = started()
    with pytest.raises(expected_exception=ValueError, match="is the room"):
        kamakiri.start_stage1(
            bootrom=usbdl.Bootrom(port=FakePort(), timeout=0),
            port=usb,
            stage1=bytes(kamakiri.STAGE1_LIMIT),
        )


def test_start_stage1_reads_the_send_pointer_then_redirects_it() -> None:
    port, usb = started()
    kamakiri.start_stage1(
        bootrom=usbdl.Bootrom(port=port, timeout=0), port=usb, stage1=STAGE1
    )
    assert usb.walked == walked_once() * 3
    assert bytes(port.written) == (
        nudge_sent()
        + sent_da(length=4, offset=kamakiri.POINTER_USBDL - kamakiri.NEAR)
        + nudge_sent()
        + sent_da(
            data=STAGE1,
            length=len(STAGE1),
            offset=kamakiri.PAYLOAD_ADDRESS - kamakiri.NEAR,
            write=True,
        )
        + nudge_sent()
        + sent_da(
            data=struct.pack("<I", kamakiri.PAYLOAD_ADDRESS),
            length=4,
            offset=SEND + kamakiri.POINTER_SKEW - kamakiri.NEAR,
            write=True,
        )
    )
    assert port.replies == bytearray()


def walked_once() -> list[int]:
    return [kamakiri.POINTER_DA + offset for offset in kamakiri.ASCENT] + [
        kamakiri.POINTER_DA + offset for offset in kamakiri.SHORT_DESCENT
    ]
