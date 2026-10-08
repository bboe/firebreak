from __future__ import annotations

from conftest import acquire_replies, aes_replies, clear_replies, sent_write, shook

from firebreak.mediatek import gcpu, range_check, usbdl

MEASURED = {
    "ADDRESS": 0x102868,
    "DATA": bytes.fromhex("00" * 12 + "80" + "00" * 3),
}


def test_constants_match_the_measured_values() -> None:
    for name, value in MEASURED.items():
        assert getattr(range_check, name) == value, name


def test_defeat_clears_and_acquires_twice() -> None:
    bootrom, port = shook(
        replies=(clear_replies() + acquire_replies()) * 2
        + bytes([usbdl.BootromCommand.EXTENDED, usbdl.CACHE_DISABLE_SUBCOMMAND])
        + b"\0\0\0"
        + aes_replies(address=range_check.ADDRESS, data=range_check.DATA)
    )
    range_check.defeat(bootrom=bootrom)
    assert port.replies == bytearray()
    assert (
        bytes(port.written).count(sent_write(address=gcpu.BASE, words=(0x1F, 0x12000)))
        == 2
    )
    assert sent_write(
        address=gcpu.BASE + gcpu.Register.SOURCE,
        words=(0, range_check.ADDRESS, 1),
    ) in bytes(port.written)


def test_every_constant_is_pinned_by_hand() -> None:
    imported = frozenset({"TYPE_CHECKING"})
    assert {name for name in vars(range_check) if name.isupper()} - imported == set(
        MEASURED
    )
