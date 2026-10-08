from __future__ import annotations

import enum

import pytest
from conftest import aes_replies, function_replies, shook

from firebreak.mediatek import gcpu, usbdl

IMPORTED = frozenset({"TYPE_CHECKING", "WORD_MASK", "WORD_SIZE"})
MEASURED = {
    "ACQUIRE_VALUES": (0x1F, 0x12000),
    "BASE": 0x10210000,
    "CLEAR_WORDS": 9,
    "DECRYPT_FUNCTION": 126,
    "SLOT_POINTER_VALUES": (18, 26, 26),
    "SLOT_WORDS": 16,
    "TIMEOUT": 5,
    "ZERO_DECRYPTION": bytes.fromhex("4dd12bdf0ec7d26c482490b3482a1b1f"),
}
MEASURED_ENUMS = {
    "Interrupt": [("FINISHED", 0x1), ("ERROR", 0x2), ("BOTH", 0x3)],
    "Register": [
        ("CONTROL", 0x0000),
        ("PROGRAM_CONTROL", 0x0400),
        ("MONITOR", 0x0418),
        ("INTERRUPT_STATUS", 0x0800),
        ("INTERRUPT_CLEAR", 0x0804),
        ("INTERRUPT_ENABLE", 0x0808),
        ("COMMAND", 0x0C00),
        ("SOURCE", 0x0C04),
        ("DESTINATION", 0x0C08),
        ("LENGTH", 0x0C0C),
        ("SLOT_POINTERS", 0x0C14),
        ("SLOTS", 0x0C48),
        ("INPUT", 0x0C68),
    ],
}
SAMPLE = bytes.fromhex("00" * 12 + "80" + "00" * 3)
TARGET = 0x100000


def test_aes_write_refuses_a_failed_function() -> None:
    bootrom, _ = shook(replies=aes_replies(address=TARGET, data=bytes(16), status=2))
    with pytest.raises(expected_exception=usbdl.ProtocolMismatchError, match="refused"):
        gcpu.aes_write(address=TARGET, bootrom=bootrom, data=bytes(16))


def test_call_function_gives_up_on_a_wedged_engine(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="TIMEOUT", target=gcpu, value=0)
    bootrom, _ = shook(replies=function_replies(status=1))
    with pytest.raises(
        expected_exception=usbdl.ProtocolMismatchError, match="left INTERRUPT_STATUS"
    ):
        gcpu.call_function(bootrom=bootrom, number=gcpu.DECRYPT_FUNCTION)


def test_call_function_raises_on_each_refusal() -> None:
    for status in (2, 3):
        bootrom, port = shook(replies=function_replies(status=status))
        with pytest.raises(
            expected_exception=usbdl.ProtocolMismatchError,
            match=f"function 126 reported status {status:#010x}",
        ):
            gcpu.call_function(bootrom=bootrom, number=gcpu.DECRYPT_FUNCTION)
        assert port.replies == bytearray()


def test_call_function_returns_when_the_engine_finishes() -> None:
    bootrom, port = shook(replies=function_replies(status=1))
    assert gcpu.call_function(bootrom=bootrom, number=gcpu.DECRYPT_FUNCTION) is None
    assert port.replies == bytearray()


def test_constants_match_the_measured_values() -> None:
    for name, value in MEASURED.items():
        assert getattr(gcpu, name) == value, name


def test_every_constant_is_pinned_by_hand() -> None:
    assert {name for name in vars(gcpu) if name.isupper()} - IMPORTED == set(MEASURED)


def test_every_enum_is_pinned_by_hand_in_wire_order() -> None:
    found = {
        name: [
            (member, int(value)) for member, value in enumeration.__members__.items()
        ]
        for name, enumeration in vars(gcpu).items()
        if isinstance(enumeration, type)
        and issubclass(enumeration, (enum.IntEnum, enum.IntFlag))
    }
    assert found == MEASURED_ENUMS


def test_the_collapsed_writes_cover_adjacent_registers() -> None:
    word = usbdl.WORD_SIZE
    assert gcpu.Register.SOURCE + word == gcpu.Register.DESTINATION
    assert gcpu.Register.SOURCE + 2 * word == gcpu.Register.LENGTH
    assert 0x0C00 + 5 * word == gcpu.Register.SLOT_POINTERS
    first, second, third = gcpu.SLOT_POINTER_VALUES
    assert 0x0C00 + first * word == gcpu.Register.SLOTS
    assert 0x0C00 + second * word == gcpu.Register.INPUT
    assert second == third
    cleared = range(
        gcpu.Register.SLOTS,
        gcpu.Register.SLOTS + gcpu.SLOT_WORDS * word,
        word,
    )
    assert gcpu.Register.INPUT in cleared
    assert list(
        range(
            gcpu.Register.LENGTH,
            gcpu.Register.LENGTH + gcpu.CLEAR_WORDS * word,
            word,
        )
    ) == [
        0x0C0C,
        0x0C10,
        0x0C14,
        0x0C18,
        0x0C1C,
        0x0C20,
        0x0C24,
        0x0C28,
        0x0C2C,
    ]


def test_vector_words() -> None:
    assert gcpu.vector_words(data=SAMPLE, decryption=gcpu.ZERO_DECRYPTION) == (
        0xDF2BD14D,
        0x6CD2C70E,
        0xB3902448,
        0x1F1B2AC8,
    )
    with pytest.raises(
        expected_exception=ValueError, match="4 bytes and the decryption"
    ):
        gcpu.vector_words(data=bytes(4), decryption=bytes(16))
