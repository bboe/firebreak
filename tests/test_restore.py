from __future__ import annotations

import gzip
import hashlib
import json
import struct
import types
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak import restore, twrp
from firebreak.devices import BISCUIT, RADAR
from firebreak.ui import SESSION, FatalError

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

    from conftest import FakeAdb

BOOT0 = b"P" * 1024
KB = b"K" * 2048
LK = b"L" * 1500
SYSTEM_TAIL = b"T" * 548
TABLE = b"G" * 512


@pytest.fixture
def reached(*, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    writes: list[dict] = []
    for name, value in (
        ("clear_boot0", lambda: None),
        ("detect_dd", lambda **_: None),
        ("identity", lambda: ("G0SERIAL", "cafe")),
        ("attached_serial", lambda: None),
        ("known_device", lambda: RADAR),
        ("twrp_entry", lambda **_: None),
        ("unmount", lambda **_: None),
        ("wait_for_twrp_start", lambda: None),
        ("write", lambda **options: writes.append(options)),
    ):
        monkeypatch.setattr(name=name, target=restore, value=value)
    return writes


def area(
    *, extents: list[dict], first: int | None, held: bytes, name: str, node: str
) -> dict:
    return {
        "extents": extents,
        "first": first,
        "md5": hashlib.md5(held, usedforsecurity=False).hexdigest(),
        "name": name,
        "node": node,
        "sha256": hashlib.sha256(held).hexdigest(),
        "size": len(held),
    }


def copied(*, data: bytes, folder: pathlib.Path, name: str) -> dict:
    (folder / f"{name}.gz").write_bytes(data=gzip.compress(data=data))
    return {"file": f"{name}.gz", "kind": "copy", "length": len(data)}


def idme(*, count: bytes, size: int = 8) -> bytes:
    field = (
        b"bootcount".ljust(16, b"\0")
        + struct.pack("<III", size, 1, 0x124)
        + count.ljust(size, b"\0")
    )
    return b"I" * 64 + field + b"manufacturing".ljust(16, b"\0") + b"\0" * 64


def made(*, cache: pathlib.Path, folder: pathlib.Path) -> dict:
    folder.mkdir()
    update = cache / "update.bin"
    with zipfile.ZipFile(file=update, mode="w") as archive:
        archive.writestr(data=LK, zinfo_or_arcname="images/lk.bin")
    ota = {
        "name": update.name,
        "sha256": hashlib.sha256(update.read_bytes()).hexdigest(),
        "url": "https://example.invalid/update.bin",
    }
    manifest = {
        "areas": [
            area(
                extents=[copied(data=TABLE, folder=folder, name="gpt-primary")],
                first=0,
                held=TABLE,
                name="gpt-primary",
                node=twrp.DISK,
            ),
            area(
                extents=[copied(data=BOOT0, folder=folder, name="boot0")],
                first=None,
                held=BOOT0,
                name="boot0",
                node=f"{twrp.DISK}boot0",
            ),
            area(
                extents=[
                    {
                        "build": "8149",
                        "image": "lk",
                        "kind": "ota",
                        "length": len(LK),
                        "ota": ota,
                        "sha256": hashlib.sha256(LK).hexdigest(),
                    },
                    copied(data=SYSTEM_TAIL, folder=folder, name="lk_a"),
                ],
                first=48,
                held=LK + SYSTEM_TAIL,
                name="lk_a",
                node=f"{twrp.DISK}p3",
            ),
            area(
                extents=[copied(data=TABLE[::-1], folder=folder, name="gpt-backup")],
                first=67,
                held=TABLE[::-1],
                name="gpt-backup",
                node=twrp.DISK,
            ),
        ],
        "cid": "cafe",
        "device": "radar",
        "format": restore.FORMAT,
        "gaps": [],
        "serial": "G0SERIAL",
    }
    (folder / restore.MANIFEST).write_text(data=json.dumps(manifest))
    return manifest


def marked(md5: str) -> str:
    return f"{md5}  -\n{twrp.MD5_OK}"


def test_attached_serial_reads_adb_then_fastboot(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="usb_serial", target=restore, value=lambda: "G0ADB")
    assert restore.attached_serial() == "G0ADB"
    monkeypatch.setattr(name="usb_serial", target=restore, value=lambda: None)
    for listed, serial in (
        ("G0FB\tfastboot\n", "G0FB"),
        ("", None),
        ("G1\tfastboot\nG2\tfastboot\n", None),
    ):
        monkeypatch.setattr(
            name="devices",
            target=restore,
            value=lambda listed=listed, **_: listed,
        )
        assert restore.attached_serial() == serial


def test_built_needs_every_byte(*, tmp_path: pathlib.Path) -> None:
    held = {
        "extents": [copied(data=b"short", folder=tmp_path, name="kb")],
        "name": "kb",
        "sha256": "",
        "size": 5,
    }
    held["extents"][0]["length"] = 6
    with pytest.raises(FatalError, match="1 bytes short"):
        restore.built(area=held, device=RADAR, folder=tmp_path, work=tmp_path)
    held["extents"][0]["length"] = 5
    with pytest.raises(FatalError, match="does not rebuild"):
        restore.built(area=held, device=RADAR, folder=tmp_path, work=tmp_path)


def test_built_stops_on_a_damaged_copy(*, tmp_path: pathlib.Path) -> None:
    held = {
        "extents": [copied(data=KB, folder=tmp_path, name="kb")],
        "name": "kb",
        "sha256": "",
        "size": len(KB),
    }
    (tmp_path / "kb.gz").write_bytes(data=gzip.compress(data=KB)[:-12])
    with pytest.raises(FatalError, match="kb could not be rebuilt"):
        restore.built(area=held, device=RADAR, folder=tmp_path, work=tmp_path)
    (tmp_path / "kb.gz").write_bytes(data=b"not gzip")
    with pytest.raises(FatalError, match="kb could not be rebuilt"):
        restore.built(area=held, device=RADAR, folder=tmp_path, work=tmp_path)
    (tmp_path / "kb.gz").unlink()
    with pytest.raises(FatalError, match="kb could not be rebuilt"):
        restore.built(area=held, device=RADAR, folder=tmp_path, work=tmp_path)


def test_counted_on_keeps_the_echo_s_boot_count(
    *, adb: FakeAdb, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "boot1.img"
    held = area(
        extents=[],
        first=None,
        held=idme(count=b"284"),
        name="boot1",
        node=f"{twrp.DISK}boot1",
    )

    def pulled(*, count: bytes, size: int = 8) -> Callable[[], str]:
        def write() -> str:
            (tmp_path / "boot1.now").write_bytes(data=idme(count=count, size=size))
            return ""

        return write

    path.write_bytes(data=idme(count=b"284"))
    adb.answers["boot1.now"] = [pulled(count=b"1557")]
    kept = restore.counted_on(area=held, path=path)
    assert path.read_bytes() == idme(count=b"1557")
    assert (
        kept["md5"]
        == hashlib.md5(idme(count=b"1557"), usedforsecurity=False).hexdigest()
    )
    assert kept["sha256"] == held["sha256"]
    path.write_bytes(data=idme(count=b"284"))
    adb.answers["boot1.now"] = [pulled(count=b"12345678")]
    assert restore.counted_on(area=held, path=path)["md5"] != held["md5"]
    assert path.read_bytes() == idme(count=b"12345678")
    for count, size in ((b"bad", 8), (b"123456789", 9)):
        path.write_bytes(data=idme(count=b"284"))
        adb.answers["boot1.now"] = [pulled(count=count, size=size)]
        assert restore.counted_on(area=held, path=path) is held
        assert path.read_bytes() == idme(count=b"284")
    adb.answers["boot1.now"] = [(1, "no such file")]
    assert restore.counted_on(area=held, path=path) is held
    path.write_bytes(data=b"no field here")
    adb.answers["boot1.now"] = [pulled(count=b"9")]
    assert restore.counted_on(area=held, path=path) is held
    assert restore.bootcount(image=b"bootcount\0") is None
    assert restore.bootcount(image=idme(count=b"1")[:-90]) is None


def test_loaded_reads_only_its_own_format(*, tmp_path: pathlib.Path) -> None:
    with pytest.raises(FatalError, match="could not be read"):
        restore.loaded(folder=tmp_path)
    (tmp_path / restore.MANIFEST).write_text(data='{"format": 0}')
    with pytest.raises(FatalError, match="is format 0"):
        restore.loaded(folder=tmp_path)
    manifest = made(cache=restore.CACHE, folder=tmp_path / "backup")
    del manifest["areas"][1]["md5"]
    (tmp_path / "backup" / restore.MANIFEST).write_text(data=json.dumps(manifest))
    with pytest.raises(FatalError, match="missing fields"):
        restore.loaded(folder=tmp_path / "backup")


def test_ota_image_checks_the_image_it_extracts(*, tmp_path: pathlib.Path) -> None:
    manifest = made(cache=restore.CACHE, folder=tmp_path / "backup")
    extent = manifest["areas"][2]["extents"][0]
    path = restore.ota_image(device=RADAR, extent=extent)
    assert path == restore.CACHE / "stock-radar-8149" / "lk.img"
    assert path.read_bytes()[: len(LK)] == LK
    path.write_bytes(data=LK[:10])
    assert restore.ota_image(device=RADAR, extent=extent) == path
    assert path.read_bytes()[: len(LK)] == LK
    with pytest.raises(FatalError, match="is not the one the backup names"):
        restore.ota_image(device=RADAR, extent={**extent, "sha256": "0" * 64})


def test_reread_needs_the_backup_table_in_the_kernel(*, adb: FakeAdb) -> None:
    areas = [
        area(
            extents=[],
            first=48,
            held=LK + SYSTEM_TAIL,
            name="lk_a",
            node=f"{twrp.DISK}p3",
        ),
        area(extents=[], first=0, held=TABLE, name="gpt-primary", node=twrp.DISK),
    ]
    adb.answers["/proc/mounts"] = ["left:"]
    adb.answers["/proc/partitions"] = [f"179 3 1 mmcblk0p3\n{restore.READ_OK}"]
    with pytest.raises(FatalError, match="does not see the backup's partition table"):
        restore.reread(areas=areas)
    adb.answers["/proc/partitions"] = ["179 3 2 mmcblk0p3"]
    with pytest.raises(FatalError, match="no answer"):
        restore.reread(areas=areas)
    adb.answers["/proc/partitions"] = [f"179 3 2 mmcblk0p3\n{restore.READ_OK}"]
    restore.reread(areas=areas)
    assert adb.commands(holding="--rereadpt")


def test_restore_counts_the_ota_images_it_has_yet_to_extract(
    *, monkeypatch: pytest.MonkeyPatch, reached: list[dict], tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "backup"
    manifest = made(cache=restore.CACHE, folder=folder)
    areas = sum(each["size"] for each in manifest["areas"])
    monkeypatch.setattr(
        name="disk_usage",
        target=restore.shutil,
        value=lambda _: types.SimpleNamespace(free=areas),
    )
    with pytest.raises(FatalError, match="which has 0 MiB free"):
        restore.restore(directory=str(folder), force=True)
    assert not reached
    image = restore.CACHE / "stock-radar-8149" / "lk.img"
    image.parent.mkdir(parents=True)
    image.write_bytes(data=LK)

    def entered(**_: object) -> None:
        raise FatalError(message="entered TWRP")

    monkeypatch.setattr(name="twrp_entry", target=restore, value=entered)
    with pytest.raises(FatalError, match="entered TWRP"):
        restore.restore(directory=str(folder), force=True)


def test_restore_needs_room_to_rebuild_the_backup(
    *, monkeypatch: pytest.MonkeyPatch, reached: list[dict], tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "backup"
    made(cache=restore.CACHE, folder=folder)
    entered = []
    monkeypatch.setattr(
        name="twrp_entry",
        target=restore,
        value=lambda **options: entered.append(options),
    )
    monkeypatch.setattr(
        name="disk_usage",
        target=restore.shutil,
        value=lambda _: types.SimpleNamespace(free=0),
    )
    with pytest.raises(FatalError, match="which has 0 MiB free"):
        restore.restore(directory=str(folder), force=True)
    assert not entered
    assert not reached
    assert not (restore.CACHE / "restore-G0SERIAL").exists()


def test_restore_refuses_another_echo(
    *, monkeypatch: pytest.MonkeyPatch, reached: list[dict], tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "backup"
    made(cache=restore.CACHE, folder=folder)
    monkeypatch.setattr(name="known_device", target=restore, value=lambda: BISCUIT)
    with pytest.raises(FatalError, match="backup is of a radar"):
        restore.restore(directory=str(folder), force=True)
    monkeypatch.setattr(name="known_device", target=restore, value=lambda: RADAR)
    monkeypatch.setattr(name="identity", target=restore, value=lambda: ("G1", "beef"))
    with pytest.raises(FatalError, match="whose eMMC is not this one, G1"):
        restore.restore(directory=str(folder), force=True)
    assert not reached
    assert not (restore.CACHE / "restore-G0SERIAL").exists()


def test_restore_refuses_another_echo_before_twrp(
    *, monkeypatch: pytest.MonkeyPatch, reached: list[dict], tmp_path: pathlib.Path
) -> None:
    folder = tmp_path / "backup"
    made(cache=restore.CACHE, folder=folder)
    monkeypatch.setattr(name="attached_serial", target=restore, value=lambda: "G1")
    monkeypatch.setattr(
        name="twrp_entry",
        target=restore,
        value=lambda **_: pytest.fail("reached TWRP with another Echo attached"),
    )
    with pytest.raises(
        FatalError, match="backup is of the Echo G0SERIAL, and this is G1"
    ):
        restore.restore(directory=str(folder), force=True)
    assert not reached


@pytest.mark.parametrize(("device", "named"), [("donut", "donut"), ("radar", "radar")])
def test_restore_tells_the_entry_a_donut_backup_s_device(
    *,
    device: str,
    monkeypatch: pytest.MonkeyPatch,
    named: str,
    reached: list[dict],
    tmp_path: pathlib.Path,
) -> None:
    folder = tmp_path / "backup"
    manifest = made(cache=restore.CACHE, folder=folder)
    (folder / restore.MANIFEST).write_text(
        data=json.dumps({**manifest, "device": device})
    )
    monkeypatch.setattr(name="device", target=SESSION, value=None)

    def entered(**options: object) -> None:
        raise FatalError(
            message=f"entered TWRP as {getattr(options['named'], 'name', None)}"
        )

    monkeypatch.setattr(name="twrp_entry", target=restore, value=entered)
    with pytest.raises(FatalError, match=f"entered TWRP as {named}"):
        restore.restore(directory=str(folder), force=True)
    assert not reached


def test_restore_writes_every_area_with_the_tables_first_and_boot0_last(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    reached: list[dict],
    tmp_path: pathlib.Path,
) -> None:
    folder = tmp_path / "backup"
    made(cache=restore.CACHE, folder=folder)
    held = hashlib.md5(BOOT0, usedforsecurity=False).hexdigest()
    adb.answers["md5sum /dev/block/mmcblk0boot0"] = [marked("0" * 32), marked(held)]
    adb.answers["md5sum /tmp/boot0.img"] = [held]
    adb.answers["/proc/partitions"] = [f"179 3 2 mmcblk0p3\n{restore.READ_OK}"]
    contents = {}

    def recorded(**options: object) -> None:
        contents[options["label"]] = options["path"].read_bytes()
        reached.append(options)

    monkeypatch.setattr(name="write", target=restore, value=recorded)
    restore.restore(directory=str(folder), force=True)
    assert [(each["label"], each["sector"]) for each in reached] == [
        ("write gpt-backup", 67),
        ("write gpt-primary", 0),
        ("write lk_a", 48),
    ]
    assert reached[2]["number"] == 3
    assert contents["write lk_a"] == LK + SYSTEM_TAIL
    assert contents["write gpt-backup"] == TABLE[::-1]
    assert adb.commands(holding="--rereadpt")
    assert adb.commands(holding="mmcblk0boot0/force_ro")
    assert not SESSION.boot0_erased
    assert not (restore.CACHE / "restore-G0SERIAL").exists()


def test_written_stops_on_a_boot_area_that_does_not_verify(
    *, adb: FakeAdb, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "boot1.img"
    path.write_bytes(data=BOOT0)
    held = area(
        extents=[], first=None, held=BOOT0, name="boot1", node=f"{twrp.DISK}boot1"
    )
    adb.answers["md5sum /dev/block/mmcblk0boot1"] = [marked(held["md5"])]
    restore.written(area=held, path=path)
    assert not adb.commands(holding="force_ro")
    adb.answers["md5sum /dev/block/mmcblk0boot1"] = [marked("0" * 32)]
    adb.answers["/tmp/boot1.img"] = [(1, "no room")]
    with pytest.raises(FatalError, match="did not arrive intact after 3 tries"):
        restore.written(area=held, path=path)
    del adb.answers["/tmp/boot1.img"]
    adb.answers["md5sum /tmp/boot1.img"] = [held["md5"]]
    adb.answers["/tmp/boot1.img"] = [(0, "")]
    with pytest.raises(FatalError, match="boot1 did not verify"):
        restore.written(area=held, path=path)
    assert len(adb.commands(holding="mmcblk0boot1/force_ro")) == twrp.PUSH_TRIES


def test_written_stops_on_a_boot_area_that_never_answers(
    *, adb: FakeAdb, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "boot1.img"
    path.write_bytes(data=BOOT0)
    held = area(
        extents=[], first=None, held=BOOT0, name="boot1", node=f"{twrp.DISK}boot1"
    )
    adb.answers["md5sum /dev/block/mmcblk0boot1"] = [marked("0" * 32), "error: closed"]
    adb.answers["md5sum /tmp/boot1.img"] = [held["md5"]]
    with pytest.raises(FatalError, match="boot1 could not be read back after 3 tries"):
        restore.written(area=held, path=path)
    assert len(adb.commands(holding="mmcblk0boot1/force_ro")) == 1


def test_written_writes_a_boot_area_again_when_its_read_back_differs(
    *, adb: FakeAdb, tmp_path: pathlib.Path
) -> None:
    path = tmp_path / "boot1.img"
    path.write_bytes(data=BOOT0)
    held = area(
        extents=[], first=None, held=BOOT0, name="boot1", node=f"{twrp.DISK}boot1"
    )
    adb.answers["md5sum /dev/block/mmcblk0boot1"] = [
        marked("0" * 32),
        "adb.exe: device 'G090' not found",
        marked("1" * 32),
        marked(held["md5"]),
    ]
    adb.answers["md5sum /tmp/boot1.img"] = [held["md5"]]
    restore.written(area=held, path=path)
    assert len(adb.commands(holding="mmcblk0boot1/force_ro")) == 2
    assert len(adb.commands(holding="wait-for-recovery")) == 1
