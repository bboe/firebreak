from __future__ import annotations

import pathlib
import struct

import pytest

from firebreak.cache import CACHE
from firebreak.mediatek.gcpu import BASE, Register

ACQUIRE_LITERALS = (BASE + Register.CONTROL + 4, BASE)
ACQUIRE_ROUTINE = bytes.fromhex(
    "08b5fff79dff094b094a1868116840f4803021f01f011160186041f01f011160"
    "1a6842f400521a6008bd"
)
DERIVED_REGISTERS = frozenset({
    Register.INPUT,
    Register.PROGRAM_CONTROL,
    Register.SLOTS,
})
ENGINE_LITERALS = (
    BASE + Register.INTERRUPT_ENABLE,
    BASE + Register.INTERRUPT_CLEAR,
    BASE + Register.COMMAND,
    BASE + Register.INTERRUPT_STATUS,
    BASE + Register.INTERRUPT_STATUS,
    BASE + Register.MONITOR,
)
ENGINE_ROUTINE = bytes.fromhex(
    "12490323124a13600b600021114ba3f50063c3f800081048196003680e49002b"
    "fbd0980709d5d80702d40b68002bfcd003234ff0ff301360704708490b68db07"
    "fcd50323002013607047"
)
ENGINE_WINDOW = 0x1000
PRELOADERS = sorted(CACHE.glob("*/preloader.img")) + sorted(
    CACHE.glob("*/amonet/bin/preloader.img")
)
SLOT_ROUTINE = bytes.fromhex("8000002300f18152194602f58632d1500433102bfbd17047")


@pytest.fixture(
    ids=lambda path: "none" if path is None else path.relative_to(CACHE).parts[0],
    params=PRELOADERS or [None],
)
def preloader(request: pytest.FixtureRequest) -> bytes:
    if request.param is None:
        pytest.skip("no preloader image in the cache")
    return pathlib.Path(request.param).read_bytes()


def literal_words(*, image: bytes, routine: bytes) -> list[int]:
    start = image.index(routine)
    assert start % 4 == 0
    found = []
    offset = 0
    while offset < len(routine) - 1:
        halfword = struct.unpack_from("<H", routine, offset)[0]
        if halfword >= 0xE800:
            offset += 4
            continue
        if 0x4800 <= halfword < 0x5000:
            pool = (start + offset + 4) & ~0x3
            found.append(
                struct.unpack_from("<I", image, pool + (halfword & 0xFF) * 4)[0]
            )
        offset += 2
    return found


def test_the_preloader_acquires_the_engine_through_two_control_registers(
    preloader: bytes,
) -> None:
    assert literal_words(image=preloader, routine=ACQUIRE_ROUTINE) == list(
        ACQUIRE_LITERALS
    )


def test_the_preloader_holds_every_register_but_the_derived_three(
    preloader: bytes,
) -> None:
    assert {
        BASE + member for member in Register if member not in DERIVED_REGISTERS
    } <= window_words(image=preloader)


def test_the_preloader_runs_the_engine_routine_the_client_reimplements(
    preloader: bytes,
) -> None:
    assert literal_words(image=preloader, routine=ENGINE_ROUTINE) == list(
        ENGINE_LITERALS
    )


def test_the_three_routines_appear_in_both_copies_of_the_image(
    preloader: bytes,
) -> None:
    for routine in (ACQUIRE_ROUTINE, ENGINE_ROUTINE, SLOT_ROUTINE):
        assert preloader.count(routine) == 2


def window_words(*, image: bytes) -> set[int]:
    return {
        word
        for offset in range(0, len(image) - 3, 4)
        if BASE
        <= (word := struct.unpack_from("<I", image, offset)[0])
        < BASE + ENGINE_WINDOW
    }
