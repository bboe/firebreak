from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import pytest

from firebreak import lk_unlock
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

FIRE_OS_5_CHECK = bytes.fromhex(
    "08b500f0c9f9012801d0002008bdfff7c5fdd0f1010038bf002008bd"
)
LOCK_CHECK = bytes.fromhex("08b500f0b1f9012805d1f4f789f9b0fa80f0400908bd002008bd")
OFFSET = 0x40


def lk_image(*, code: bytes, path: pathlib.Path) -> pathlib.Path:
    header = struct.pack("<II", lk_unlock.MTK_MAGIC, len(code)) + b"LK"
    path.write_bytes(data=header.ljust(lk_unlock.HEADER, b"\0") + code)
    return path


def stock(*, check: bytes = LOCK_CHECK, copies: int = 1) -> bytes:
    code = bytearray(b"\xaa" * 0x400)
    for index in range(copies):
        at = OFFSET + index * 0x100
        code[at : at + len(check)] = check
    return bytes(code)


def test_head_returns_the_bootloader_unchanged_but_for_the_lock_check(
    tmp_path: pathlib.Path,
) -> None:
    code = stock()
    image = lk_image(code=code, path=tmp_path / "lk.img")
    patched = lk_unlock.head(image=image)
    assert len(patched) == OFFSET + lk_unlock.OVERSHOOT
    assert patched[:OFFSET] == code[:OFFSET]
    assert patched[OFFSET : OFFSET + len(lk_unlock.UNLOCKED)] == lk_unlock.UNLOCKED
    assert (
        patched[OFFSET + len(lk_unlock.UNLOCKED) :]
        == (code[OFFSET + len(lk_unlock.UNLOCKED) : OFFSET + lk_unlock.OVERSHOOT])
    )


def test_little_kernel_refuses_a_file_shorter_than_the_header(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "lk.img"
    path.write_bytes(data=b"\0" * 8)
    with pytest.raises(FatalError, match="too short"):
        lk_unlock.little_kernel(image=path)


def test_little_kernel_refuses_a_size_past_the_end_of_the_file(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "lk.img"
    header = struct.pack("<II", lk_unlock.MTK_MAGIC, 1 << 20)
    path.write_bytes(data=header.ljust(lk_unlock.HEADER, b"\0") + b"\xaa" * 0x10)
    with pytest.raises(FatalError, match="not a bootloader image"):
        lk_unlock.little_kernel(image=path)


def test_little_kernel_refuses_an_image_without_the_mtk_magic(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "lk.img"
    path.write_bytes(data=b"\0" * (lk_unlock.HEADER + 0x100))
    with pytest.raises(FatalError, match="not a bootloader image"):
        lk_unlock.little_kernel(image=path)


def test_little_kernel_returns_the_payload_after_the_header(
    tmp_path: pathlib.Path,
) -> None:
    code = stock()
    image = lk_image(code=code, path=tmp_path / "lk.img")
    assert lk_unlock.little_kernel(image=image) == code


def test_located_finds_a_fire_os_5_lock_check() -> None:
    assert lk_unlock.located(code=stock(check=FIRE_OS_5_CHECK), name="lk.img") == (
        OFFSET
    )


def test_located_finds_the_lock_check() -> None:
    assert lk_unlock.located(code=stock(), name="lk.img") == OFFSET


def test_located_refuses_a_bootloader_with_more_than_one_lock_check() -> None:
    with pytest.raises(FatalError, match="2 lock checks"):
        lk_unlock.located(code=stock(copies=2), name="lk.img")


def test_located_refuses_a_bootloader_without_a_lock_check() -> None:
    with pytest.raises(FatalError, match="0 lock checks"):
        lk_unlock.located(code=b"\xaa" * 0x400, name="lk.img")


def test_the_payload_constants_match_the_dot_they_were_measured_on() -> None:
    assert lk_unlock.DOWNLOAD_SIZE == 0x6D00000
    assert lk_unlock.DOWNLOAD_SIZE % lk_unlock.CHUNK == 0
    assert lk_unlock.OVERSHOOT == 0x24
    assert all(len(shape) < lk_unlock.OVERSHOOT for shape in lk_unlock.LOCK_CHECKS)


def test_the_payload_overruns_the_buffer_by_the_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="CHUNK", target=lk_unlock, value=0x100)
    monkeypatch.setattr(name="DOWNLOAD_SIZE", target=lk_unlock, value=0x200)
    image = lk_image(code=stock(), path=tmp_path / "lk.img")
    path = lk_unlock.write(image=image, path=tmp_path / "unlock.img")
    assert path.stat().st_size > lk_unlock.DOWNLOAD_SIZE


def test_write_fills_the_download_buffer_then_lands_the_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(name="CHUNK", target=lk_unlock, value=0x100)
    monkeypatch.setattr(name="DOWNLOAD_SIZE", target=lk_unlock, value=0x250)
    image = lk_image(code=stock(), path=tmp_path / "lk.img")
    path = lk_unlock.write(image=image, path=tmp_path / "unlock.img")
    written = path.read_bytes()
    assert len(written) == 0x250 + OFFSET + lk_unlock.OVERSHOOT
    assert written[:0x250] == bytes(0x250)
    assert written[0x250:] == lk_unlock.head(image=image)
