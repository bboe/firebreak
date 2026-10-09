from __future__ import annotations

import struct
import sys
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import cache, twrp, ui
from firebreak.mediatek import gcpu, usbdl

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator


class FakePort:
    def __init__(self, *, replies: bytes = b"", short: bool = False) -> None:
        self.flushes = 0
        self.replies = bytearray(replies)
        self.short = short
        self.written = bytearray()

    def read(self, *, size: int) -> bytes:
        count = 1 if self.short else size
        taken = bytes(self.replies[:count])
        del self.replies[: len(taken)]
        return taken

    def reset_input_buffer(self) -> None:
        self.flushes += 1

    def write(self, *, data: bytes) -> int:
        self.written += data
        return len(data)


@pytest.fixture(autouse=True)
def fresh_session() -> Iterator[None]:
    ui.ARGUMENTS.verbose = False
    vars(ui.SESSION).update(vars(ui.Session()))
    vars(ui.PROGRESS).update(vars(ui.Progress()))
    yield
    ui.PROGRESS.halt()


@pytest.fixture(autouse=True)
def no_real_cache(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    directory = tmp_path / "real-cache"
    for module in (cache, sys.modules.get("firebreak.__main__")):
        if module is not None:
            monkeypatch.setattr(name="CACHE", target=module, value=directory)
            monkeypatch.setattr(
                name="ERASED", target=module, value=directory / "boot0-erased"
            )
    monkeypatch.setattr(name="CACHE", target=twrp, value=directory)
    monkeypatch.setattr(name="ERASED", target=twrp, value=directory / "boot0-erased")
    monkeypatch.setenv(name="HOME", value=str(tmp_path / "real-home"))
    monkeypatch.setenv(name="USERPROFILE", value=str(tmp_path / "real-home"))
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=real_browser)


def acquire_replies() -> bytes:
    return reply_write(
        address=gcpu.BASE + gcpu.Register.CONTROL, words=gcpu.ACQUIRE_VALUES
    )


def aes_replies(*, address: int, data: bytes, status: int = 1) -> bytes:
    return (
        clear_input_replies()
        + reply_write(
            address=gcpu.BASE + gcpu.Register.INPUT,
            words=gcpu.vector_words(data=data, decryption=gcpu.ZERO_DECRYPTION),
        )
        + reply_write(address=gcpu.BASE + gcpu.Register.SOURCE, words=(0, address, 1))
        + reply_write(
            address=gcpu.BASE + gcpu.Register.SLOT_POINTERS,
            words=gcpu.SLOT_POINTER_VALUES,
        )
        + function_replies(status=status)
    )


def clear_input_replies() -> bytes:
    return reply_write(
        address=gcpu.BASE + gcpu.Register.SLOTS, words=(0,) * gcpu.SLOT_WORDS
    )


def clear_replies() -> bytes:
    return (
        reply_write(
            address=gcpu.BASE + gcpu.Register.LENGTH, words=(0,) * gcpu.CLEAR_WORDS
        )
        + clear_input_replies()
    )


def function_replies(*, status: int) -> bytes:
    polls = reply_read(
        address=gcpu.BASE + gcpu.Register.INTERRUPT_STATUS, values=(0,)
    ) + reply_read(address=gcpu.BASE + gcpu.Register.INTERRUPT_STATUS, values=(status,))
    read_again = reply_read(
        address=gcpu.BASE + gcpu.Register.INTERRUPT_STATUS, values=(status,)
    )
    if status & gcpu.Interrupt.ERROR:
        tail = (
            b""
            if status & gcpu.Interrupt.FINISHED
            else reply_read(
                address=gcpu.BASE + gcpu.Register.INTERRUPT_STATUS, values=(status,)
            )
        )
    else:
        tail = reply_read(address=gcpu.BASE + gcpu.Register.MONITOR, values=(1,))
    return (
        reply_write(
            address=gcpu.BASE + gcpu.Register.INTERRUPT_CLEAR,
            words=(gcpu.Interrupt.BOTH,),
        )
        + reply_write(
            address=gcpu.BASE + gcpu.Register.INTERRUPT_ENABLE,
            words=(gcpu.Interrupt.BOTH,),
        )
        + reply_write(
            address=gcpu.BASE + gcpu.Register.COMMAND,
            words=(gcpu.DECRYPT_FUNCTION,),
        )
        + reply_write(address=gcpu.BASE + gcpu.Register.PROGRAM_CONTROL, words=(0,))
        + polls
        + read_again
        + tail
        + reply_write(
            address=gcpu.BASE + gcpu.Register.INTERRUPT_CLEAR,
            words=(gcpu.Interrupt.BOTH,),
        )
    )


def opened_a_browser(**options: str) -> None:
    message = f"a test opened the real browser at {options}"
    raise AssertionError(message)


def real_browser() -> types.SimpleNamespace:
    return types.SimpleNamespace(name="real-browser", open=opened_a_browser)


def reply_read(*, address: int, values: tuple[int, ...]) -> bytes:
    return (
        bytes([usbdl.BootromCommand.READ_WORDS])
        + struct.pack(">II", address, len(values))
        + usbdl.READ_STATUS
        + struct.pack(f">{len(values)}I", *values)
        + usbdl.READ_STATUS
    )


def reply_write(*, address: int, end: bool = True, words: tuple[int, ...]) -> bytes:
    return (
        bytes([usbdl.BootromCommand.WRITE_WORDS])
        + struct.pack(">II", address, len(words))
        + usbdl.WRITE_STATUS
        + b"".join(struct.pack(">I", word) for word in words)
        + (usbdl.WRITE_STATUS if end else b"")
    )


def sent_read(*, address: int, count: int) -> bytes:
    return bytes([usbdl.BootromCommand.READ_WORDS]) + struct.pack(">II", address, count)


def sent_write(*, address: int, words: tuple[int, ...]) -> bytes:
    return (
        bytes([usbdl.BootromCommand.WRITE_WORDS])
        + struct.pack(">II", address, len(words))
        + b"".join(struct.pack(">I", word) for word in words)
    )


def shook(*, replies: bytes) -> tuple[usbdl.Bootrom, FakePort]:
    port = FakePort(replies=replies)
    return usbdl.Bootrom(port=port, timeout=0), port
