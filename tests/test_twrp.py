from __future__ import annotations

import hashlib
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from firebreak import host, twrp

if TYPE_CHECKING:
    import pathlib

TABLE = """\
Number  Start (sector)    End (sector)  Size       Code  Name
   1            1024            2047   512.0 KiB   0700  boot_a
  12           65536          131071   32.0 MiB    8300  userdata
table-ok"""


class FakeAdb:
    def __init__(self) -> None:
        self.answers: dict[str, list[str | tuple[int, str] | Exception]] = {}
        self.asked: list[list[str]] = []
        self.raw = b""
        self.sent: list[bytes] = []

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
        returncode, text = answer if isinstance(answer, tuple) else (0, answer)
        return subprocess.CompletedProcess(
            args=words, returncode=returncode, stdout=text.encode()
        )

    def commands(self, *, holding: str) -> list[str]:
        return [words[-1] for words in self.asked if holding in words[-1]]


@pytest.fixture
def adb(*, monkeypatch: pytest.MonkeyPatch) -> FakeAdb:
    fake = FakeAdb()
    for module in (host, twrp):
        monkeypatch.setattr(name="command", target=module, value=fake.command)
    monkeypatch.setattr(name="sleep", target=time, value=lambda _: None)
    return fake


@pytest.fixture
def erased() -> pathlib.Path:
    twrp.ERASED.parent.mkdir(exist_ok=True, parents=True)
    twrp.ERASED.touch()
    return twrp.ERASED


@pytest.fixture
def image(*, tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "image.img"
    path.write_bytes(b"I" * 8192)
    return path


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest() + "  -"


def test_a_block_device_check_names_each_wrong_node(*, adb: FakeAdb) -> None:
    adb.answers["nodes-ok"] = [f"{twrp.DISK}p3=no nodes-ok"]
    wrong = twrp.check_nodes(want={f"{twrp.DISK}p3": 512, f"{twrp.DISK}p5": 1024})
    assert wrong == f"{twrp.DISK}p3 reads no, not 512 bytes"


def test_a_block_device_check_naming_a_node_not_asked_about_is_read_again(
    *, adb: FakeAdb
) -> None:
    adb.answers["nodes-ok"] = [f"{twrp.DISK}p9=no nodes-ok", " nodes-ok"]
    assert twrp.check_nodes(want={f"{twrp.DISK}p3": 512}) == ""
    assert len(adb.commands(holding="wait-for-recovery")) == 1


def test_a_block_device_check_that_never_answers_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["nodes-ok"] = ["b= nodes-"]
    with pytest.raises(SystemExit) as stopped:
        twrp.check_nodes(want={f"{twrp.DISK}p3": 512})
    assert "which of its partitions are block devices: 'b= nodes-'" in " ".join(
        str(stopped.value).split()
    )
    assert len(adb.commands(holding="nodes-ok")) == twrp.PUSH_TRIES
    assert len(adb.commands(holding="wait-for-recovery")) == twrp.PUSH_TRIES - 1


def test_a_block_device_check_with_every_node_right_says_nothing(
    *, adb: FakeAdb
) -> None:
    adb.answers["nodes-ok"] = [" nodes-ok"]
    assert twrp.check_nodes(want={f"{twrp.DISK}p3": 512}) == ""
    (asked,) = adb.commands(holding="nodes-ok")
    assert f"for p in {twrp.DISK}p3:512;" in asked


def test_a_cleared_boot0_goes_on(*, adb: FakeAdb, erased: pathlib.Path) -> None:
    adb.answers["force_ro"] = ["4096 0"]
    twrp.clear_boot0()
    assert erased.exists()


@pytest.mark.parametrize(
    argnames=("answer", "started", "said"),
    argvalues=[
        ("left:/cache ", False, "still mounted: /cache; nothing was written"),
        ("left:/cache ", True, "still mounted: /cache; do not reboot"),
        ("umount: busy", False, "did not answer what is mounted"),
    ],
    ids=["mounted", "mounted-mid-restore", "no-answer"],
)
def test_a_mount_left_behind_stops_it(
    *, adb: FakeAdb, answer: str, said: str, started: bool
) -> None:
    adb.answers["left:"] = [answer]
    with pytest.raises(SystemExit) as stopped:
        twrp.unmount(started=started)
    assert said in " ".join(str(stopped.value).split())


def test_a_partition_field_is_read_from_sgdisk(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --info=12"] = [
        (
            "Partition GUID code: 0FC63DAF-8483 (Linux filesystem)\n"
            "Partition unique GUID: 'ABCD-1234'\nfield-ok"
        )
    ]
    assert twrp.partition_field(name="Partition GUID code", number=12) == (
        "0FC63DAF-8483"
    )
    assert twrp.partition_field(name="Partition unique GUID", number=12) == (
        "ABCD-1234"
    )


def test_a_partition_field_sgdisk_does_not_print_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --info=12"] = ["First sector: 65536\nfield-ok"]
    with pytest.raises(SystemExit, match="printed no Partition GUID code"):
        twrp.partition_field(name="Partition GUID code", number=12)


def test_a_partition_field_that_never_arrives_whole_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --info=12"] = ["Partition GUID code: 0FC6"]
    with pytest.raises(SystemExit, match="did not answer in full"):
        twrp.partition_field(name="Partition GUID code", number=12)
    assert len(adb.commands(holding="sgdisk")) == twrp.PUSH_TRIES


def test_a_partition_table_cut_short_is_read_again(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --print"] = [TABLE[:40], TABLE]
    assert twrp.partition_table() == TABLE.removesuffix("\ntable-ok")
    assert len(adb.commands(holding="wait-for-recovery")) == 1


def test_a_partition_table_is_read_by_name(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --print"] = [TABLE]
    assert twrp.partitions() == {
        "boot_a": (1, 1024, 2047),
        "userdata": (12, 65536, 131071),
    }


def test_a_partition_table_that_never_arrives_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --print"] = ["Problem opening /dev/block/mmcblk0"]
    with pytest.raises(SystemExit, match="did not print"):
        twrp.partition_table()
    assert len(adb.commands(holding="sgdisk")) == twrp.PUSH_TRIES


def test_a_partition_table_without_a_userdata_row_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --print"] = ["Disk userdata\ntable-ok"]
    with pytest.raises(SystemExit, match="no userdata"):
        twrp.partitions()


def test_a_partition_table_without_userdata_is_read_again(*, adb: FakeAdb) -> None:
    adb.answers["sgdisk --print"] = ["Number  Start\ntable-ok", TABLE]
    assert twrp.partition_table() == TABLE.removesuffix("\ntable-ok")
    assert len(adb.commands(holding="wait-for-recovery")) == 1


def test_a_sector_read_returns_whole_sectors(*, adb: FakeAdb) -> None:
    adb.raw = b"S" * 1024
    assert twrp.read_sectors(count=2, start=34) == b"S" * 1024
    (asked,) = adb.commands(holding="if=")
    assert f"dd if={twrp.DISK} bs=512 skip=34 count=2" in asked


def test_a_short_sector_read_stops_it(*, adb: FakeAdb) -> None:
    adb.raw = b"S" * 1000
    with pytest.raises(SystemExit, match="read 1000 bytes"):
        twrp.read_sectors(count=2, start=0)


def test_a_staged_write_lands_through_dd(*, adb: FakeAdb, image: pathlib.Path) -> None:
    adb.answers["md5sum"] = [md5(data=b"old"), md5(data=image.read_bytes())]
    adb.answers["of=" + twrp.DISK] = ["written"]
    adb.answers["flushed"] = ["flushed"]
    twrp.write(estimate="5 s", label="table", path=image, sector=8)
    (written,) = adb.commands(holding="of=" + twrp.DISK)
    assert written.startswith(
        f"dd if={twrp.DOT_TEMPORARY_DIRECTORY / image.name} of={twrp.DISK} bs=4096"
        " seek=1 && rm -f"
    )


def test_a_staged_write_that_dd_does_not_finish_stops_it(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers["of=" + twrp.DISK] = ["dd: write error"]
    with pytest.raises(SystemExit, match="table failed"):
        twrp.write(estimate="5 s", label="table", path=image, sector=1)
    assert "bs=512 seek=1" in adb.commands(holding="of=" + twrp.DISK)[0]


def test_a_staged_write_that_does_not_reach_the_dot_stops_it(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers[str(twrp.DOT_TEMPORARY_DIRECTORY / image.name)] = [(1, "no space")]
    with pytest.raises(SystemExit, match="did not reach the Dot"):
        twrp.write(estimate="5 s", label="table", path=image, sector=8)


def test_a_system_image_that_never_finishes_keeps_the_cache(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    (image.parent / "md5").write_text("old 2\n")
    adb.answers["echo ready"] = ["ready"]
    adb.answers["gunzip"] = [subprocess.TimeoutExpired(cmd=["adb"], timeout=600)]
    with pytest.raises(SystemExit, match="did not finish"):
        twrp.write_system(blocks=2, image=image, system="/s", want="new")
    assert (image.parent / "md5").exists()


def test_a_system_image_that_never_verifies_is_discarded(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    (image.parent / "md5").write_text("old 2\n")
    adb.answers["echo ready"] = ["ready"]
    adb.answers["md5sum"] = [md5(data=b"old")]
    with pytest.raises(SystemExit, match="cached image was discarded"):
        twrp.write_system(blocks=2, image=image, system="/s", want="new")
    assert not (image.parent / "md5").exists()


def test_a_system_partition_left_mounted_stops_it(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["echo ready"] = ["umount: /system_root: busy"]
    with pytest.raises(SystemExit, match="stayed mounted"):
        twrp.write_system(blocks=2, image=image, system="/s", want="new")
    assert adb.sent == []


def test_a_write_already_in_place_is_skipped(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=image.read_bytes())]
    twrp.write(estimate="5 s", label="table", number=7, path=image, sector=8)
    assert [words for words in adb.asked if words[1] == "push"] == []
    assert len(adb.commands(holding="md5sum")) == 1


def test_a_write_by_partition_checks_where_it_starts(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers["/start"] = ["9"]
    with pytest.raises(SystemExit, match="starts at 9, not 8"):
        twrp.write(estimate="5 s", label="boot", number=7, path=image, sector=8)
    assert [words for words in adb.asked if words[1] == "push"] == []


def test_a_write_by_partition_is_pushed_to_its_node(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old"), md5(data=image.read_bytes())]
    adb.answers["/start"] = ["8"]
    adb.answers["flushed"] = ["flushed"]
    twrp.write(estimate="5 s", label="boot", number=7, path=image, sector=8)
    assert ["adb", "push", str(image), f"{twrp.DISK}p7"] in adb.asked


def test_a_write_by_partition_that_push_refuses_stops_it(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers["/start"] = ["8"]
    adb.answers[f"{twrp.DISK}p7"] = [(1, "remote write failed")]
    with pytest.raises(SystemExit, match="remote write failed"):
        twrp.write(estimate="5 s", label="boot", number=7, path=image, sector=8)


def test_a_write_that_does_not_flush_stops_it(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers["of=" + twrp.DISK] = ["written"]
    with pytest.raises(SystemExit, match="could not be flushed"):
        twrp.write(estimate="5 s", label="table", path=image, sector=8)


def test_a_write_that_does_not_verify_stops_it(
    *, adb: FakeAdb, erased: pathlib.Path, image: pathlib.Path
) -> None:
    del erased
    adb.answers["md5sum"] = [md5(data=b"old")]
    adb.answers["of=" + twrp.DISK] = ["written"]
    adb.answers["flushed"] = ["flushed"]
    with pytest.raises(SystemExit, match="did not verify") as stopped:
        twrp.write(estimate="5 s", label="table", path=image, sector=8)
    assert "boot0 has no preloader" in " ".join(str(stopped.value).split())


def test_a_write_with_a_matching_head_still_checks_the_whole(
    *, adb: FakeAdb, image: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="HEAD_CHECK", target=twrp, value=4096)
    head = md5(data=image.read_bytes()[:4096])
    adb.answers["md5sum"] = [head, md5(data=b"old"), md5(data=image.read_bytes())]
    adb.answers["of=" + twrp.DISK] = ["written"]
    adb.answers["flushed"] = ["flushed"]
    twrp.write(estimate="5 s", label="table", path=image, sector=8)
    reads = adb.commands(holding="md5sum")
    assert "count=1 " in reads[0]
    assert "count=2 " in reads[1]
    assert len(adb.commands(holding="of=" + twrp.DISK)) == 1


def test_an_uncleared_boot0_header_stops_before_the_bootrom_fallback(
    *, adb: FakeAdb, erased: pathlib.Path
) -> None:
    adb.answers["force_ro"] = ["4096 12"]
    with pytest.raises(SystemExit, match="did not clear") as stopped:
        twrp.clear_boot0()
    assert not erased.exists()
    assert "nothing else was written" in " ".join(str(stopped.value).split())


def test_an_unread_boot0_says_the_dot_cannot_start(
    *, adb: FakeAdb, erased: pathlib.Path
) -> None:
    del erased
    adb.answers["force_ro"] = [""]
    with pytest.raises(SystemExit, match="did not read back") as stopped:
        twrp.clear_boot0()
    assert "boot0 has no preloader" in " ".join(str(stopped.value).split())


def test_nothing_mounted_goes_on(*, adb: FakeAdb) -> None:
    adb.answers["left:"] = ["left: "]
    twrp.unmount()


def test_the_system_image_is_streamed_until_it_verifies(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    system = "/dev/block/platform/mtk-msdc.0/by-name/system_a"
    adb.answers["echo ready"] = ["ready"]
    adb.answers["gunzip"] = [(1, "gzip: invalid magic"), (0, "")]
    adb.answers["md5sum"] = [md5(data=b"old"), md5(data=b"new")]
    twrp.write_system(blocks=2, image=image, system=system, want=md5(data=b"new")[:32])
    assert adb.sent == [image.read_bytes()] * 3
    assert len(adb.commands(holding="wait-for-recovery")) == 2
    assert f"dd if={system} bs=4096 count=2" in adb.commands(holding="md5sum")[0]


def test_toybox_writes_a_staged_image_without_truncating(
    *, adb: FakeAdb, image: pathlib.Path
) -> None:
    twrp.SESSION.dd = "toybox dd"
    adb.answers["md5sum"] = [md5(data=b"old"), md5(data=image.read_bytes())]
    adb.answers["of=" + twrp.DISK] = ["written"]
    adb.answers["flushed"] = ["flushed"]
    twrp.write(estimate="5 s", label="table", path=image, sector=8)
    (written,) = adb.commands(holding="of=" + twrp.DISK)
    assert written.startswith("toybox dd if=")
    assert "bs=4096 seek=1 conv=notrunc && rm -f" in written


def test_twrp_is_ready_once_it_runs_with_mtp(*, adb: FakeAdb) -> None:
    adb.answers["ro.twrp.version"] = ["", "3.7.0_9-0"]
    adb.answers["sys.usb.config"] = ["mtp,adb"]
    twrp.wait_for_twrp()
    assert len(adb.commands(holding="ro.twrp.version")) == 2


def test_twrp_that_does_not_finish_starting_stops_it(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = iter(range(0, 1000, 20))
    monkeypatch.setattr(name="monotonic", target=time, value=lambda: next(clock))
    adb.answers["ro.twrp.version"] = ["3.7.0_9-0"]
    adb.answers["sys.usb.config"] = ["adb"]
    with pytest.raises(SystemExit, match="within 30 seconds"):
        twrp.wait_for_twrp()


def test_twrp_that_never_comes_up_stops_it(*, adb: FakeAdb) -> None:
    adb.answers["wait-for-recovery"] = [
        subprocess.TimeoutExpired(cmd=["adb"], timeout=300)
    ]
    with pytest.raises(SystemExit, match="within 5 minutes"):
        twrp.wait_for_twrp()
