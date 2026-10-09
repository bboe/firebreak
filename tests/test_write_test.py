from __future__ import annotations

import hashlib
import subprocess
from typing import TYPE_CHECKING

from firebreak import write_test

if TYPE_CHECKING:
    import pathlib

    import pytest

DF = (
    "Filesystem  1K-blocks  Used Available Use% Mounted on\n"
    "tmpfs  245760  0  {free}  0% /tmp"
)


class Dot:
    def __init__(self, *, answers: dict[str, str]) -> None:
        self.answers = answers
        self.asked: list[str] = []
        self.lines: list[tuple[str, object]] = []

    def ask(self, *, command: str, **_: object) -> str:
        self.asked.append(command)
        return next((said for key, said in self.answers.items() if key in command), "")

    def line(self, label: str, value: object) -> None:
        self.lines.append((label, value))

    def said(self, *, label: str) -> str:
        return str(dict(self.lines)[label])


def pushed(
    *, monkeypatch: pytest.MonkeyPatch, returncode: int = 0, stdout: str = ""
) -> list[bytes]:
    sent: list[bytes] = []

    def run(*, arguments: list[object], **_: object) -> subprocess.CompletedProcess:
        sent.append(arguments[2].read_bytes())
        return subprocess.CompletedProcess(
            args=arguments, returncode=returncode, stdout=stdout
        )

    monkeypatch.setattr(name="run", target=write_test, value=run)
    return sent


def test_a_card_answer_with_the_digest_off_the_last_line_did_not_run() -> None:
    dot = Dot(answers={"-O ^sparse_super": "card:0123  -\ndd: error"})
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert "the test did not run" in dict(dot.lines)


def test_a_card_format_that_says_more_after_its_word_is_not_fresh() -> None:
    want = write_test.repeat_md5(blocks=16, times=2)
    dot = Dot(
        answers={
            "-O ^sparse_super": f"card:{want}  -",
            "blockdev": "formatted\nmke2fs: warning",
        }
    )
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert dot.said(label="fresh filesystem").startswith("NO: formatted")


def test_a_card_test_skips_with_its_reason() -> None:
    for blocks, chunk, reason in (
        (0, 16, "no cache partition"),
        (48, 0, "nothing verified in RAM"),
        (20, 16, "holds under 32 MiB"),
    ):
        dot = Dot(answers={})
        write_test.emmc_leg(
            asked=dot.ask, blocks=blocks, chunk=chunk, line=dot.line, node="/n"
        )
        assert reason in dot.said(label="over the eMMC")
        assert dot.asked == []


def test_a_card_test_that_did_not_run_says_why() -> None:
    dot = Dot(answers={"-O ^sparse_super": "cache is still mounted\nexit 8"})
    write_test.SESSION.dd = "toybox dd"
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert dot.said(label="the test did not run").startswith("cache is still")
    assert "verdict" not in dict(dot.lines)
    assert "conv=notrunc" in next(
        command for command in dot.asked if "while" in command
    )


def test_a_card_that_gives_back_something_else_is_blamed() -> None:
    dot = Dot(answers={"-O ^sparse_super": "card:0123  -", "blockdev": "busy"})
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert dot.said(label="verdict").startswith("THE eMMC DID NOT GIVE BACK")
    assert dot.said(label="fresh filesystem").startswith("NO: busy. A Dot whose")


def test_a_card_that_gives_back_what_it_took_is_not_at_fault() -> None:
    want = write_test.repeat_md5(blocks=8, times=5)
    dot = Dot(
        answers={
            "blockdev": "formatted",
            "mke2fs -q -t ext4 -b 4096 -O": f"card:{want}  -",
        }
    )
    write_test.emmc_leg(
        asked=dot.ask, blocks=60, chunk=8, line=dot.line, node="/dev/block/mmcblk0p9"
    )
    assert dot.said(label="verdict").endswith("so the card is not at fault")
    assert dot.said(label="fresh filesystem") == "yes"
    (written,) = [command for command in dot.asked if "while" in command]
    assert " -lt 5 ];" in written
    assert "seek=$(( 16 + i * 8 ))" in written
    assert " skip=16 count=40 " in written
    assert "conv=notrunc" not in written
    assert "sync; echo 3 > /proc/sys/vm/drop_caches;" in written


def test_a_card_that_refuses_a_write_is_blamed() -> None:
    dot = Dot(
        answers={
            "-O ^sparse_super": "dd: write error: I/O error\n"
            + write_test.CARD_WRITE_FAILED,
            "blockdev": "formatted",
        }
    )
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert dot.said(label="verdict").startswith("THE eMMC REFUSED A WRITE")
    assert "the test did not run" not in dict(dot.lines)
    assert dot.said(label="fresh filesystem") == "yes"
    (written,) = [command for command in dot.asked if "while" in command]
    assert f"|| {{ echo {write_test.CARD_WRITE_FAILED}; exit 9; }};" in written


def test_a_card_write_that_does_not_answer_is_left_unformatted() -> None:
    dot = Dot(answers={"-O ^sparse_super": "<timed out>"})
    write_test.emmc_leg(asked=dot.ask, blocks=48, chunk=16, line=dot.line, node="/n")
    assert "dd may still be writing cache" in dot.said(label="the test did not finish")
    assert not any("blockdev" in command for command in dot.asked)


def test_a_pattern_is_every_byte_and_a_word_cut_to_size(
    *, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "pattern"
    digest = write_test.pattern_file(blocks=2, path=path)
    data = path.read_bytes()
    assert len(data) == 2 * write_test.MEBIBYTE
    assert data.startswith(write_test.PATTERN * 2)
    assert digest == hashlib.md5(data, usedforsecurity=False).hexdigest()
    assert (
        write_test.repeat_md5(blocks=1, times=2)
        == hashlib.md5(
            data[: write_test.MEBIBYTE] * 2, usedforsecurity=False
        ).hexdigest()
    )


def test_usb_that_carries_the_pattern_is_not_at_fault(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent = pushed(monkeypatch=monkeypatch, stdout="1 file pushed, 0 skipped.\n")
    want = write_test.repeat_md5(blocks=write_test.USB_BLOCKS, times=1)
    dot = Dot(
        answers={
            "df -k": DF.format(free=240 * 1024),
            "md5sum": f"{want}  /tmp/usb-test",
        }
    )
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == write_test.USB_BLOCKS
    assert len(sent[0]) == write_test.USB_BLOCKS * write_test.MEBIBYTE
    assert dot.said(label="verdict").endswith("not at fault")
    assert not list(write_test.CACHE.glob("usb-test*"))


def test_usb_that_fails_the_push_blames_the_cable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed(monkeypatch=monkeypatch, returncode=1, stdout="adb: error: closed\n")
    dot = Dot(answers={"df -k": DF.format(free=100 * 1024)})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
    assert dot.said(label="adb push said") == "adb: error: closed"
    assert dot.said(label="verdict").startswith("USB DID NOT CARRY IT")
    assert not any("md5sum" in command for command in dot.asked)


def test_usb_that_mangles_the_pattern_blames_the_cable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed(monkeypatch=monkeypatch)
    dot = Dot(answers={"df -k": DF.format(free=100 * 1024), "md5sum": "0" * 32 + "  -"})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
    assert dot.said(label="verdict").startswith("USB DID NOT CARRY IT")


def test_usb_that_times_out_blames_the_cable(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(**_: object) -> None:
        raise subprocess.TimeoutExpired(cmd=["adb"], timeout=1)

    monkeypatch.setattr(name="run", target=write_test, value=run)
    dot = Dot(answers={"df -k": DF.format(free=100 * 1024)})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
    assert "did not finish" in dot.said(label="adb push said")


def test_usb_whose_md5sum_gives_no_digest_did_not_run(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed(monkeypatch=monkeypatch)
    dot = Dot(answers={"df -k": DF.format(free=100 * 1024), "md5sum": "<timed out>"})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
    assert "<timed out>" in dot.said(label="the test did not run")
    assert "verdict" not in dict(dot.lines)


def test_usb_with_just_enough_ram_pushes_the_least(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    pushed(monkeypatch=monkeypatch)
    want = write_test.repeat_md5(blocks=write_test.USB_LEAST, times=1)
    free = (write_test.USB_LEAST + write_test.USB_SPARE) * 1024
    dot = Dot(answers={"df -k": DF.format(free=free), "md5sum": f"{want}  -"})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == write_test.USB_LEAST


def test_usb_with_too_little_ram_is_skipped() -> None:
    dot = Dot(answers={"df -k": DF.format(free=47 * 1024)})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
    assert "only 47 MiB free" in dot.said(label="over USB")

    dot = Dot(answers={"df -k": "df: /tmp: No such file"})
    assert write_test.usb_leg(asked=dot.ask, line=dot.line) == 0
