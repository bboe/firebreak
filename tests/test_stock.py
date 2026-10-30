from __future__ import annotations

import hashlib
import pathlib
import subprocess
import types
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak import stock
from firebreak.android.gpt import Partition
from firebreak.devices import BISCUIT, RADAR, TARGETS
from firebreak.survey import PROPERTIES
from firebreak.ui import FatalError

if TYPE_CHECKING:
    from conftest import FakeAdb

BOOT0_SECTORS = 8
PARTITIONS = {
    "boot_a": Partition(first=100, number=1, sectors=64),
    "boot_b": Partition(first=200, number=2, sectors=64),
    "cache": Partition(first=300, number=3, sectors=64),
    "expdb": Partition(first=400, number=4, sectors=8),
    "lk_a": Partition(first=500, number=5, sectors=8),
    "lk_b": Partition(first=600, number=6, sectors=8),
    "misc": Partition(first=700, number=7, sectors=4),
    "system_a": Partition(first=800, number=8, sectors=64),
    "system_b": Partition(first=900, number=9, sectors=64),
    "tee1": Partition(first=1000, number=10, sectors=8),
    "tee2": Partition(first=1100, number=11, sectors=8),
    "userdata": Partition(first=1200, number=12, sectors=4096),
}
PRELOADER = b"P" * (BOOT0_SECTORS * 512)
RAW = b"M" * 512 + b"H" * 512 + b"E" * 16384


@pytest.fixture
def restored(*, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch) -> FakeAdb:
    adb.answers["sgdisk --verify"] = ["No problems found"]
    adb.answers["grep -c"] = ["0"]
    adb.answers[f" {PARTITIONS['userdata'].size // 1024} mmcblk0p12$"] = ["12"]
    adb.answers["echo formatted"] = ["formatted"]
    adb.answers["slot_suffix"] = ["_a"]
    adb.answers["md5sum /dev/block/mmcblk0boot0"] = [md5(data=PRELOADER) + "  boot0"]
    monkeypatch.setattr(name="clear_boot0", target=stock, value=lambda: None)
    monkeypatch.setattr(name="unmount", target=stock, value=lambda **_: None)
    return adb


@pytest.fixture
def twrp(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> list[dict[str, object]]:
    monkeypatch.setenv(name="ANDROID_SERIAL", value="G000")
    monkeypatch.setattr(name="build", target=stock.ARGUMENTS, value="8146")
    monkeypatch.setattr(
        name="target", target=stock.ARGUMENTS, value=TARGETS[BISCUIT]["stock"]
    )
    monkeypatch.setattr(name="made_for", target=stock, value=lambda **_: "biscuit")
    adb.answers["sys.usb.config"] = ["mtp,adb"]
    adb.answers["ro.twrp.version"] = ["3.7.0_9-0"]
    adb.answers["toybox dd --help"] = ["yes"]
    adb.answers["for t in sgdisk"] = ["tools:"]
    adb.answers["ro.product.device"] = ["biscuit\ndevice-named"]
    adb.answers["echo block"] = ["block"]
    adb.answers["mmcblk0boot0/size"] = [str(BOOT0_SECTORS)]
    adb.answers["slot_suffix"] = ["_a"]

    def extract(*, update: pathlib.Path, work: pathlib.Path) -> None:
        del update
        for name, size in (
            ("boot.img", 1024),
            ("lk.img", 1024),
            ("system.img", 4096),
            ("tee.img", 1024),
        ):
            (work / name).write_bytes(b"x" * size)
        (work / "preloader.img").write_bytes(PRELOADER)

    restores: list[dict[str, object]] = []
    monkeypatch.setattr(
        name="download", target=stock.updates, value=lambda **_: tmp_path / "ota.bin"
    )
    monkeypatch.setattr(name="extract", target=stock, value=extract)
    monkeypatch.setattr(name="gpt_intact", target=stock, value=lambda **_: True)
    monkeypatch.setattr(name="read_sectors", target=stock, value=lambda **_: RAW)
    monkeypatch.setattr(
        name="stock_gpt",
        target=stock,
        value=lambda **_: types.SimpleNamespace(
            backup=b"B" * 512,
            backup_sector=9999,
            partitions=PARTITIONS,
            primary=b"A" * 512,
        ),
    )
    monkeypatch.setattr(
        name="restore", target=stock, value=lambda **options: restores.append(options)
    )
    return restores


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def test_a_bootrom_build_writes_its_preloader_through_the_bootrom(
    *, monkeypatch: pytest.MonkeyPatch, restored: FakeAdb, tmp_path: pathlib.Path
) -> None:
    writes = wrote(monkeypatch=monkeypatch)
    finished: list[dict[str, object]] = []
    monkeypatch.setattr(
        name="amonet_payload",
        target=stock,
        value=lambda: tmp_path / "payload.bin",
    )
    monkeypatch.setattr(name="pyserial_wheel", target=stock, value=lambda: None)
    monkeypatch.setattr(
        name="stock_preloader",
        target=stock,
        value=lambda **options: finished.append(options),
    )
    (tmp_path / "preloader.img").write_bytes(b"P" * 1024)
    stock.SESSION.boot0_erased = True
    stock.restore(
        backup_sector=9999,
        build="5.5.0.3",
        files=written(tmp_path=tmp_path),
        parts=PARTITIONS,
        work=tmp_path,
    )
    assert finished == [
        {
            "build": "5.5.0.3",
            "payload": tmp_path / "payload.bin",
            "preloader": b"P" * 1024,
            "wheel": None,
        }
    ]
    assert writes[-1][0] == "write TEE image to tee1 (primary)"
    assert not any("pl.img" in " ".join(asked) for asked in restored.asked)
    assert restored.asked[-1][-1] == "reboot"
    assert stock.SESSION.boot0_erased is True


def test_a_fire_os_5_restore_reboots_without_waiting(
    *, monkeypatch: pytest.MonkeyPatch, restored: FakeAdb, tmp_path: pathlib.Path
) -> None:
    wrote(monkeypatch=monkeypatch)
    stock.restore(
        backup_sector=9999,
        build="5.5.5.4",
        files=written(tmp_path=tmp_path),
        parts=PARTITIONS,
        work=tmp_path,
    )
    assert "rebooting into stock 5.5.5.4" in stock.PROGRESS.line
    assert restored.asked[-1][-1] == "reboot"


def test_a_restore_can_leave_the_dot_in_fastboot(
    *, monkeypatch: pytest.MonkeyPatch, restored: FakeAdb, tmp_path: pathlib.Path
) -> None:
    wrote(monkeypatch=monkeypatch)
    monkeypatch.setattr(name="fastboot", target=stock.SESSION, value=True)
    monkeypatch.setattr(name="wait_for_fastboot", target=stock, value=lambda: None)
    stock.restore(
        backup_sector=9999,
        build="8338",
        files=written(tmp_path=tmp_path),
        parts=PARTITIONS,
        work=tmp_path,
    )
    assert "rebooting into fastboot" in stock.PROGRESS.line
    assert restored.asked[-1][-2:] == ["reboot", "bootloader"]


@pytest.mark.parametrize(
    ("key", "answer", "said"),
    [
        ("sgdisk --verify", "Problem: bad", "sgdisk does not accept the new table"),
        ("grep -c", "2", "still sees amonet's partitions"),
        (f" {PARTITIONS['userdata'].size // 1024} mmcblk0p12$", "", "not its stock"),
        ("echo formatted", "mke2fs: failed", "did not format"),
        (
            "pl.img",
            (1, "adb: error"),
            r"the preloader did not reach the Echo Dot \(2nd Generation\)",
        ),
        (
            "md5sum /dev/block/mmcblk0boot0",
            "0" * 32 + "  boot0",
            "boot0 does not match the 8146 preloader: read 000",
        ),
    ],
)
def test_a_restore_that_goes_wrong_says_do_not_reboot(  # ruff: ignore[too-many-arguments]
    *,
    answer: str | tuple[int, str],
    key: str,
    monkeypatch: pytest.MonkeyPatch,
    restored: FakeAdb,
    said: str,
    tmp_path: pathlib.Path,
) -> None:
    wrote(monkeypatch=monkeypatch)
    restored.answers[key] = [answer]
    with pytest.raises(FatalError, match=said) as stopped:
        stock.restore(
            backup_sector=9999,
            build="8146",
            files=written(tmp_path=tmp_path),
            parts=PARTITIONS,
            work=tmp_path,
        )
    assert "do not reboot" in stopped.value.message
    assert stock.SESSION.boot0_erased is True


def test_a_restore_that_times_out_rebooting_still_finishes(
    *, monkeypatch: pytest.MonkeyPatch, restored: FakeAdb, tmp_path: pathlib.Path
) -> None:
    wrote(monkeypatch=monkeypatch)
    restored.answers["reboot"] = [subprocess.TimeoutExpired(cmd="adb", timeout=60)]
    stock.restore(
        backup_sector=9999,
        build="8146",
        files=written(tmp_path=tmp_path),
        parts=PARTITIONS,
        work=tmp_path,
    )
    assert stock.PROGRESS.open


def test_a_restore_writes_in_order_and_starts_stock(
    *, monkeypatch: pytest.MonkeyPatch, restored: FakeAdb, tmp_path: pathlib.Path
) -> None:
    writes = wrote(monkeypatch=monkeypatch)
    stock.restore(
        backup_sector=9999,
        build="8146",
        files=written(tmp_path=tmp_path),
        parts=PARTITIONS,
        work=tmp_path,
    )
    assert writes == [
        ("write the system image to system_a", 8, "system", 800),
        ("write the system image to system_b", 9, "system", 900),
        ("write boot image to boot_a", 1, "boot", 100),
        ("write boot image to boot_b", 2, "boot", 200),
        ("write misc, slot a marked good", 7, "misc", 700),
        ("write the stock table (backup)", None, "gpt-backup.bin", 9999),
        ("write the stock table (primary)", None, "gpt-primary.bin", 0),
        ("write LK image to lk_b (spare slot)", 6, "lk", 600),
        ("write TEE image to tee2 (backup)", 11, "tee", 1100),
        ("zero expdb (amonet kaeru payload)", 4, "expdb", 400),
        ("write LK image to lk_a (live slot)", 5, "lk", 500),
        ("write TEE image to tee1 (primary)", 10, "tee", 1000),
    ]
    assert stock.SESSION.boot0_erased is False
    assert restored.commands(holding="if=/tmp/pl.img of=/dev/block/mmcblk0boot0 ")
    assert restored.asked[-1][-1] == "reboot"


@pytest.mark.parametrize(
    ("raised", "finished", "said"),
    [
        (
            subprocess.TimeoutExpired(cmd=["adb", "push"], timeout=120),
            False,
            "adb push did not finish in 120 seconds. Do not reboot",
        ),
        (KeyboardInterrupt(), False, "stopped part way. Do not reboot"),
        (KeyboardInterrupt(), True, "stopped; stock 8146 is in place"),
    ],
)
def test_a_stock_stage_that_stops_part_way_says_whether_to_reboot(
    *,
    finished: bool,
    monkeypatch: pytest.MonkeyPatch,
    raised: BaseException,
    said: str,
    twrp: list[dict[str, object]],
) -> None:
    del twrp

    def restore(**_: object) -> None:
        stock.PROGRESS.steps = 16
        stock.PROGRESS.step = 16 if finished else 3
        raise raised

    monkeypatch.setattr(name="restore", target=stock, value=restore)
    with pytest.raises(FatalError, match=said):
        stock.stage_restore()


def test_chain_writes_put_the_live_lk_slot_after_the_spare(*, adb: FakeAdb) -> None:
    adb.answers["slot_suffix"] = ["_b"]
    assert [step.partition for step in stock.chain_writes()] == [
        "lk_a",
        "tee2",
        "expdb",
        "lk_b",
        "tee1",
    ]
    adb.answers["slot_suffix"] = ["_a"]
    labels = [step.label for step in stock.chain_writes()]
    assert labels[0] == "write LK image to lk_b (spare slot)"
    assert labels[3] == "write LK image to lk_a (live slot)"


@pytest.mark.parametrize(
    ("properties", "made"),
    [
        (b"ro.product.device=radar_puffin\n", "radar"),
        (b"ro.product.device=biscuit\n", "biscuit"),
        (b"ro.product.model=AEORD\n", ""),
    ],
)
def test_made_for_names_the_device_an_ota_is_for(
    *, made: str, properties: bytes, tmp_path: pathlib.Path
) -> None:
    update = tmp_path / "ota.bin"
    with zipfile.ZipFile(file=update, mode="w") as archive:
        archive.writestr(data=properties, zinfo_or_arcname=PROPERTIES)
    assert stock.made_for(update=update) == made


def test_the_stock_stage_builds_its_images_from_the_dot(
    *,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
    twrp: list[dict[str, object]],
) -> None:
    del tmp_path
    stock.stage_restore()
    work = stock.CACHE / "stock-biscuit-8146"
    assert len(twrp) == 1
    options = twrp[0]
    assert options["backup_sector"] == 9999
    assert options["build"] == "8146"
    files = options["files"]
    assert files["gpt-primary.bin"].read_bytes() == b"A" * 512
    assert files["gpt-backup.bin"].read_bytes() == b"B" * 512
    assert files["boot"].stat().st_size == PARTITIONS["boot_a"].size
    assert files["expdb"].read_bytes() == bytes(PARTITIONS["expdb"].size)
    misc = files["misc"].read_bytes()
    assert misc[0x360:0x367] == b"\0ABB\x01\x8f\0"
    assert len(misc) == PARTITIONS["misc"].size
    assert (work / "current-gpt-G000.bin").read_bytes() == RAW
    assert (work / "boot0.img").read_bytes() == PRELOADER
    assert stock.SESSION.dd == "toybox dd"
    out = capsys.readouterr().out
    assert (
        "stock partition table built from this Echo Dot (2nd Generation)'s own table"
        in out
    )
    assert "Starting now." in out


def test_the_stock_stage_can_be_cancelled_in_its_countdown(
    *, monkeypatch: pytest.MonkeyPatch, twrp: list[dict[str, object]]
) -> None:
    slept: list[float] = []

    def interrupt(seconds: float) -> None:
        slept.append(seconds)
        if len(slept) > 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(name="sleep", target=stock.time, value=interrupt)
    with pytest.raises(FatalError, match="stopped; nothing was written"):
        stock.stage_restore()
    assert twrp == []


def test_the_stock_stage_checks_the_device_of_the_target(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    twrp: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        name="target", target=stock.ARGUMENTS, value=TARGETS[RADAR]["stock"]
    )
    monkeypatch.setattr(name="made_for", target=stock, value=lambda **_: "radar")
    with pytest.raises(FatalError, match="not an Echo \\(2nd Generation\\)"):
        stock.stage_restore()
    adb.answers["ro.product.device"] = ["radar\ndevice-named"]
    stock.stage_restore()
    assert twrp


def test_the_stock_stage_counts_down_before_it_writes(
    *,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
    twrp: list[dict[str, object]],
) -> None:
    del tmp_path, twrp
    stock.stage_restore()
    out = capsys.readouterr().out
    assert "Starting in 10 s. Ctrl-C cancels." in out
    assert "Starting now." in out


def test_the_stock_stage_gives_up_on_a_twrp_that_never_starts(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, twrp: list[dict[str, object]]
) -> None:
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(name="monotonic", target=stock.time, value=lambda: next(clock))
    adb.answers["ro.twrp.version"] = [""]
    with pytest.raises(FatalError, match="within 30 seconds"):
        stock.stage_restore()
    assert twrp == []


def test_the_stock_stage_keeps_the_first_table_it_saved(
    *, twrp: list[dict[str, object]]
) -> None:
    saved = stock.CACHE / "stock-biscuit-8146" / "current-gpt-G000.bin"
    saved.parent.mkdir(parents=True)
    saved.write_bytes(b"first")
    stock.stage_restore()
    assert saved.read_bytes() == b"first"
    assert twrp


def test_the_stock_stage_pads_the_preloader_to_a_larger_boot0(
    *, adb: FakeAdb, tmp_path: pathlib.Path, twrp: list[dict[str, object]]
) -> None:
    del tmp_path
    adb.answers["mmcblk0boot0/size"] = [str(4 * BOOT0_SECTORS)]
    stock.stage_restore()
    boot0 = (stock.CACHE / "stock-biscuit-8146" / "boot0.img").read_bytes()
    assert boot0 == PRELOADER + bytes(3 * len(PRELOADER))
    assert len(twrp) == 1


def test_the_stock_stage_reads_the_backup_table_when_the_primary_is_damaged(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, twrp: list[dict[str, object]]
) -> None:
    reads: list[dict[str, int]] = []
    tail = b"T" * (32 * 512) + b"h" * 512

    def read_sectors(**options: int) -> bytes:
        reads.append(options)
        return RAW if options["start"] == 0 else tail

    monkeypatch.setattr(name="gpt_intact", target=stock, value=lambda **_: False)
    monkeypatch.setattr(name="read_sectors", target=stock, value=read_sectors)
    adb.answers["blockdev --getsize64"] = [str(1000 * 512)]
    stock.stage_restore()
    assert reads[1] == {"count": 33, "start": 1000 - 33}
    saved = stock.CACHE / "stock-biscuit-8146" / "current-gpt-G000.bin"
    assert saved.read_bytes() == RAW[:512] + b"h" * 512 + b"T" * (32 * 512)
    assert twrp


def test_the_stock_stage_refuses_an_image_too_big_for_its_partition(
    *, monkeypatch: pytest.MonkeyPatch, twrp: list[dict[str, object]]
) -> None:
    small = dict(PARTITIONS, tee1=Partition(first=1000, number=10, sectors=1))
    monkeypatch.setattr(
        name="stock_gpt",
        target=stock,
        value=lambda **_: types.SimpleNamespace(
            backup=b"", backup_sector=1, partitions=small, primary=b""
        ),
    )
    with pytest.raises(FatalError, match=r"tee\.img does not fit tee1"):
        stock.stage_restore()
    assert twrp == []


def test_the_stock_stage_refuses_an_ota_made_for_another_device(
    *, monkeypatch: pytest.MonkeyPatch, twrp: list[dict[str, object]]
) -> None:
    monkeypatch.setattr(name="made_for", target=stock, value=lambda **_: "radar")
    with pytest.raises(FatalError, match="OTA 8146 is for 'radar', not biscuit"):
        stock.stage_restore()
    assert not twrp


def test_the_stock_stage_waits_for_twrp_to_finish_starting(
    *, adb: FakeAdb, twrp: list[dict[str, object]]
) -> None:
    adb.answers["ro.twrp.version"] = ["", "3.2.3-0"]
    adb.answers["sys.usb.config"] = ["", "mtp"]
    stock.stage_restore()
    assert len(adb.commands(holding="ro.twrp.version")) == 3
    assert twrp


def test_the_stock_stage_with_no_wait_skips_the_countdown(
    *,
    capsys: pytest.CaptureFixture[str],
    tmp_path: pathlib.Path,
    twrp: list[dict[str, object]],
) -> None:
    del tmp_path, twrp
    stock.SESSION.no_wait = True
    stock.stage_restore()
    out = capsys.readouterr().out
    assert "Starting in" not in out
    assert "Starting now." in out
    assert "Starting now.  " not in out


@pytest.mark.parametrize(
    ("key", "answer", "said"),
    [
        (
            "ro.twrp.version",
            "2.8.7.0",
            r"this needs a TWRP for this Echo Dot \(2nd Generation\)",
        ),
        ("for t in sgdisk", "nothing", "did not answer which tools it has: nothing"),
        ("for t in sgdisk", "tools: sgdisk", "this TWRP has no sgdisk"),
        ("ro.product.device", "crown\ndevice-named", "the device 'crown'"),
        ("ro.product.device", "biscuit", "which device this is came back cut"),
        ("echo block", "", "is not a block device"),
        ("mmcblk0boot0/size", "4", r"preloader\.img does not fit boot0 \(4 sectors\)"),
        (
            "blockdev --getsize64",
            "",
            r"could not read the Echo Dot \(2nd Generation\)'s disk size",
        ),
    ],
)
def test_the_stock_stage_writes_nothing_to_a_dot_it_cannot_check(  # ruff: ignore[too-many-arguments]
    *,
    adb: FakeAdb,
    answer: str,
    key: str,
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    twrp: list[dict[str, object]],
) -> None:
    if key == "blockdev --getsize64":
        monkeypatch.setattr(name="gpt_intact", target=stock, value=lambda **_: False)
    adb.answers[key] = [answer]
    with pytest.raises(FatalError, match=said):
        stock.stage_restore()
    assert twrp == []


def test_waiting_for_fastboot_gives_up_when_the_dot_never_arrives(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = iter([0.0, 1.0, 1000.0])
    monkeypatch.setattr(name="end", target=stock.PROGRESS, value=lambda **_: None)
    monkeypatch.setattr(name="in_fastboot", target=stock, value=lambda: False)
    monkeypatch.setattr(name="monotonic", target=stock.time, value=lambda: next(clock))
    monkeypatch.setattr(name="sleep", target=stock.time, value=lambda _: None)
    with pytest.raises(FatalError, match="did not reach fastboot"):
        stock.wait_for_fastboot()


def test_waiting_for_fastboot_returns_once_the_dot_arrives(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([False, True])
    monkeypatch.setattr(name="end", target=stock.PROGRESS, value=lambda **_: None)
    monkeypatch.setattr(name="in_fastboot", target=stock, value=lambda: next(answers))
    monkeypatch.setattr(name="sleep", target=stock.time, value=lambda _: None)
    stock.wait_for_fastboot()


def test_waiting_for_fastboot_rides_out_a_slow_fastboot_devices(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers: list[object] = [
        subprocess.TimeoutExpired(cmd=["fastboot", "devices"], timeout=30),
        False,
        True,
    ]

    def asked() -> bool:
        answer = answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return bool(answer)

    monkeypatch.setattr(name="end", target=stock.PROGRESS, value=lambda **_: None)
    monkeypatch.setattr(name="in_fastboot", target=stock, value=asked)
    monkeypatch.setattr(name="sleep", target=stock.time, value=lambda _: None)
    stock.wait_for_fastboot()
    assert answers == []


def written(*, tmp_path: pathlib.Path) -> dict[str, pathlib.Path]:
    files = {}
    for name in ("boot", "expdb", "gpt-backup.bin", "gpt-primary.bin", "lk"):
        files[name] = tmp_path / name
    for name in ("misc", "system", "tee"):
        files[name] = tmp_path / name
    (tmp_path / "boot0.img").write_bytes(PRELOADER)
    return files


def wrote(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, object, str, object]]:
    writes: list[tuple[str, object, str, object]] = []

    def write(**options: object) -> None:
        path = options["path"]
        assert isinstance(path, pathlib.Path)
        writes.append((
            str(options["label"]),
            options.get("number"),
            path.name,
            options["sector"],
        ))

    monkeypatch.setattr(name="write", target=stock, value=write)
    return writes
