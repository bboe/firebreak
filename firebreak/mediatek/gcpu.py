from __future__ import annotations

import enum
import struct
import time
from typing import TYPE_CHECKING

from firebreak.mediatek.usbdl import WORD_MASK, WORD_SIZE, ProtocolMismatchError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from firebreak.mediatek.usbdl import Bootrom

ACQUIRE_VALUES = (0x1F, 0x12000)
BASE = 0x10210000
CLEAR_WORDS = 9
DECRYPT_FUNCTION = 126
SLOT_POINTER_VALUES = (18, 26, 26)
SLOT_WORDS = 16
TIMEOUT = 5
# https://github.com/xyzz/amonet/blob/45c54ebcb4f013a894b753c982ecf90f0464af3b/modules/load_payload.py#L52
ZERO_DECRYPTION = bytes.fromhex("4dd12bdf0ec7d26c482490b3482a1b1f")


class Interrupt(enum.IntFlag):
    FINISHED = 0x1
    ERROR = 0x2
    BOTH = FINISHED | ERROR


class Register(enum.IntEnum):
    CONTROL = 0x0000
    PROGRAM_CONTROL = 0x0400
    MONITOR = 0x0418
    INTERRUPT_STATUS = 0x0800
    INTERRUPT_CLEAR = 0x0804
    INTERRUPT_ENABLE = 0x0808
    COMMAND = 0x0C00
    SOURCE = 0x0C04
    DESTINATION = 0x0C08
    LENGTH = 0x0C0C
    SLOT_POINTERS = 0x0C14
    SLOTS = 0x0C48
    INPUT = 0x0C68


def acquire(*, bootrom: Bootrom) -> None:
    write(bootrom=bootrom, register=Register.CONTROL, words=ACQUIRE_VALUES)


def aes_write(*, address: int, bootrom: Bootrom, data: bytes) -> None:
    clear_input(bootrom=bootrom)
    write(
        bootrom=bootrom,
        register=Register.INPUT,
        words=vector_words(data=data, decryption=ZERO_DECRYPTION),
    )
    write(bootrom=bootrom, register=Register.SOURCE, words=(0, address, 1))
    write(bootrom=bootrom, register=Register.SLOT_POINTERS, words=SLOT_POINTER_VALUES)
    try:
        call_function(bootrom=bootrom, number=DECRYPT_FUNCTION)
    except ProtocolMismatchError as error:
        message = (
            f"the crypto engine refused to write {data!r} to {address:#x}: {error}"
        )
        raise ProtocolMismatchError(message) from error


def call_function(*, bootrom: Bootrom, number: int) -> None:
    write(bootrom=bootrom, register=Register.INTERRUPT_CLEAR, words=(Interrupt.BOTH,))
    write(bootrom=bootrom, register=Register.INTERRUPT_ENABLE, words=(Interrupt.BOTH,))
    write(bootrom=bootrom, register=Register.COMMAND, words=(number,))
    write(bootrom=bootrom, register=Register.PROGRAM_CONTROL, words=(0,))
    wait(bootrom=bootrom, mask=WORD_MASK, register=Register.INTERRUPT_STATUS)
    status = bootrom.read_words(address=BASE + Register.INTERRUPT_STATUS, count=1)[0]
    refused = bool(status & Interrupt.ERROR)
    if refused:
        if not status & Interrupt.FINISHED:
            wait(bootrom=bootrom, mask=WORD_MASK, register=Register.INTERRUPT_STATUS)
    else:
        wait(bootrom=bootrom, mask=Interrupt.FINISHED, register=Register.MONITOR)
    write(bootrom=bootrom, register=Register.INTERRUPT_CLEAR, words=(Interrupt.BOTH,))
    if refused:
        message = f"function {number} reported status {status:#010x}"
        raise ProtocolMismatchError(message)


def clear(*, bootrom: Bootrom) -> None:
    write(bootrom=bootrom, register=Register.LENGTH, words=(0,) * CLEAR_WORDS)
    clear_input(bootrom=bootrom)


def clear_input(*, bootrom: Bootrom) -> None:
    write(bootrom=bootrom, register=Register.SLOTS, words=(0,) * SLOT_WORDS)


def vector_words(*, data: bytes, decryption: bytes) -> tuple[int, ...]:
    if len(data) != len(decryption):
        message = (
            f"the AES input is {len(data)} bytes and the decryption"
            f" {len(decryption)} bytes"
        )
        raise ValueError(message)
    layout = f"<{len(data) // WORD_SIZE}I"
    return tuple(
        target ^ mask
        for target, mask in zip(
            struct.unpack(layout, data), struct.unpack(layout, decryption)
        )
    )


def wait(*, bootrom: Bootrom, mask: int, register: Register) -> None:
    deadline = time.monotonic() + TIMEOUT
    address = BASE + register
    while not bootrom.read_words(address=address, count=1)[0] & mask:
        if time.monotonic() >= deadline:
            message = (
                f"the crypto engine left {register.name} ({address:#x}) without"
                f" {mask:#x} set after {TIMEOUT} seconds"
            )
            raise ProtocolMismatchError(message)


def write(*, bootrom: Bootrom, register: Register, words: Sequence[int]) -> None:
    bootrom.write_words(address=BASE + register, words=words)
