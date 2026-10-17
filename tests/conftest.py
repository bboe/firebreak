from __future__ import annotations

import struct
import subprocess
import sys
import time
import types
from typing import TYPE_CHECKING

import pytest

from firebreak import cache, host, ui
from firebreak.devices import BISCUIT
from firebreak.mediatek import gcpu, usbdl
from firebreak.unlocks.targets import DEFAULTS, TARGETS

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterator


class FakeAdb:
    def __init__(self) -> None:
        self.answers: dict[
            str, list[str | tuple[int, str] | Exception | Callable[[], str]]
        ] = {}
        self.asked: list[list[str]] = []
        self.raw = b""
        self.sent: list[bytes] = []

    def answer(self, *, words: list[str]) -> tuple[int, str]:
        answer = next(
            (
                said.pop(0) if len(said) > 1 else said[0]
                for key, said in self.answers.items()
                if key in words[-1]
            ),
            "",
        )
        if isinstance(answer, Exception):
            raise answer
        if callable(answer):
            answer = answer()
        return answer if isinstance(answer, tuple) else (0, answer)

    def command(
        self, *, arguments: list[object], standard_input: object = None, **_: object
    ) -> subprocess.CompletedProcess[bytes]:
        words = [str(word) for word in arguments]
        self.asked.append(words)
        if words[1] == "exec-out":
            return subprocess.CompletedProcess(
                args=words, returncode=0, stdout=self.raw
            )
        if hasattr(standard_input, "read"):
            self.sent.append(standard_input.read())
        returncode, text = self.answer(words=words)
        return subprocess.CompletedProcess(
            args=words, returncode=returncode, stdout=text.encode()
        )

    def commands(self, *, holding: str) -> list[str]:
        return [words[-1] for words in self.asked if holding in words[-1]]

    def stream(
        self, *, arguments: list[str], pieces: list[pathlib.Path], **_: object
    ) -> subprocess.CompletedProcess[str]:
        self.asked.append(arguments)
        self.sent.append(b"".join(piece.read_bytes() for piece in pieces))
        returncode, text = self.answer(words=arguments)
        return subprocess.CompletedProcess(
            args=arguments, returncode=returncode, stdout=text
        )


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
    ui.ARGUMENTS.target = TARGETS[BISCUIT][DEFAULTS[BISCUIT]]
    ui.ARGUMENTS.verbose = False
    vars(ui.SESSION).update(vars(ui.Session()))
    vars(ui.PROGRESS).update(vars(ui.Progress()))
    yield
    ui.PROGRESS.halt()


@pytest.fixture(autouse=True)
def no_real_cache(*, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    directory = tmp_path / "real-cache"
    directory.mkdir()
    for name, module in tuple(sys.modules.items()):
        if name != "firebreak" and not name.startswith("firebreak."):
            continue
        for attribute, value in (
            ("CACHE", directory),
            ("ERASED", directory / "boot0-erased"),
        ):
            if hasattr(module, attribute):
                monkeypatch.setattr(name=attribute, target=module, value=value)
    monkeypatch.setenv(name="HOME", value=str(tmp_path / "real-home"))
    monkeypatch.setenv(name="USERPROFILE", value=str(tmp_path / "real-home"))
    monkeypatch.setattr(name="get", target=cache.webbrowser, value=real_browser)


@pytest.fixture
def adb(*, monkeypatch: pytest.MonkeyPatch) -> FakeAdb:
    fake = FakeAdb()
    real = {"command": host.command, "stream": host.stream}
    for name, module in tuple(sys.modules.items()):
        if name != "firebreak" and not name.startswith("firebreak."):
            continue
        for attribute, value in real.items():
            if getattr(module, attribute, None) is value:
                monkeypatch.setattr(
                    name=attribute, target=module, value=getattr(fake, attribute)
                )
    monkeypatch.setattr(name="sleep", target=time, value=lambda _: None)
    return fake


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
