from __future__ import annotations

import base64
import contextlib
import gzip
import hashlib
import io
import itertools
import re
import shutil
import sqlite3
import subprocess
import zipfile
from typing import TYPE_CHECKING

import pytest
from conftest import ADB_KEY

from firebreak import fireos
from firebreak.devices import BISCUIT, DONUT, RADAR, TARGETS, biscuit
from firebreak.ui import FatalError

if TYPE_CHECKING:
    import pathlib

    from conftest import FakeAdb

BLOCK = 4096
EC_OID = bytes.fromhex("06072a8648ce3d0201")
MAGISK_FILES = {
    b"data/adb": (0o40700, b""),
    b"data/adb/magisk.db": (0o100600, b"database"),
    b"data/adb/magisk/magisk": (0o100755, b"binary"),
}
RSA_OID = bytes.fromhex("06092a864886f70d010101")


@pytest.fixture
def fireos5(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
    scripts: dict[str, str],
    tmp_path: pathlib.Path,
) -> list[dict[str, object]]:
    del scripts
    monkeypatch.setattr(
        name="target",
        target=fireos.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos5"],
    )
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: tmp_path)
    monkeypatch.setattr(
        name="system_image",
        target=fireos,
        value=lambda **_: ([tmp_path / "system.00.gz"], "f" * 32, 8),
    )
    monkeypatch.setattr(
        name="write_system", target=fireos, value=lambda **o: calls.append(o)
    )
    monkeypatch.setattr(name="boot_image", target=fireos, value=lambda **_: b"B" * 5000)
    monkeypatch.setattr(
        name="install_magisk", target=fireos, value=lambda **o: calls.append(o)
    )
    adb.answers["slot_suffix"] = ["_b"]
    adb.answers["bs=4096 count=2"] = [lambda: md5(data=pushed[-1][0].read_bytes())]
    return calls


@pytest.fixture
def fireos6(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
    tmp_path: pathlib.Path,
) -> list[str]:
    del pushed
    (tmp_path / "ota").write_bytes(data=b"ota")
    monkeypatch.setattr(
        name="target",
        target=fireos.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos6"],
    )
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=True)
    waited: list[str] = []
    monkeypatch.setattr(name="amonet_chain", target=fireos, value=lambda: None)
    monkeypatch.setattr(
        name="download", target=fireos.updates, value=lambda **_: tmp_path / "ota"
    )
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: tmp_path / "br")
    monkeypatch.setattr(
        name="partition_table", target=fireos, value=lambda: " 1 boot_a\n 2 userdata"
    )
    monkeypatch.setattr(
        name="wait_for_twrp", target=fireos, value=lambda: waited.append("twrp")
    )
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "b", "b", "a")
    ]
    adb.answers["boot-root.zip"] = ["Installing\nDone"]
    adb.answers["Installing zip file"] = [ended(rc=0)]
    adb.answers["neutering ota updates"] = ["1\nzip-ok"]
    adb.answers["updates-ok"] = [
        "fos6-a\noff-a\nlocked-a\nfos6-b\noff-b\nlocked-b\nupdates-ok"
    ]
    return waited


@pytest.fixture
def magisk(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        name="magisk_db", target=fireos, value=lambda **o: o["path"].write_bytes(b"db")
    )
    monkeypatch.setattr(
        name="magisk_files", target=fireos, value=lambda **_: MAGISK_FILES
    )


@pytest.fixture
def migration(
    *,
    adb: FakeAdb,
    fireos6: list[str],
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
    tmp_path: pathlib.Path,
) -> dict[str, list[object]]:
    bridge = tmp_path / "bridge.zip"
    with zipfile.ZipFile(file=bridge, mode="w") as archive:
        archive.writestr(data=b"K" * 5000, zinfo_or_arcname="boot.img")
    package = fireos.BUILDS[BISCUIT][fireos.MIGRATE_BUILD]
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    monkeypatch.setattr(
        name="fetch",
        target=fireos,
        value=lambda **o: bridge if o["download"] is package else tmp_path / "br",
    )
    calls: dict[str, list[object]] = {"confirm": [], "system": []}
    monkeypatch.setattr(
        name="confirm", target=fireos, value=lambda **o: calls["confirm"].append(o)
    )
    monkeypatch.setattr(
        name="system_image",
        target=fireos,
        value=lambda **o: (
            calls["system"].append(o["package"])
            or ([tmp_path / "system.00.gz"], "f" * 32, 8)
        ),
    )
    monkeypatch.setattr(
        name="write_system",
        target=fireos,
        value=lambda **o: calls["system"].append(o["system"]),
    )
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "a", "a", "b", "b", "a", "a")
    ]
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 5.5.5.4 (680767620)\nbuild-ok"
    ]
    adb.answers["queue-clear"] = [
        "queue-clear\nstaged\nMapMigrationSuccess=1\nWifiConfigSuccess=1\nstaged-ok"
    ]
    adb.answers["echo pending"] = ["mounted\npending\nmoving\nstaged-ok"]
    adb.answers["migrated-ok"] = [
        "boot=1 init=MIGRATION_PUFFIN_FINISH\nmap-ok\nmigrated-ok"
    ]
    adb.answers[fireos.VERIFIED_OK] = [f"true\n{fireos.VERIFIED_OK}"]
    adb.answers["bs=4096 count=2"] = [lambda: md5(data=pushed[-1][0].read_bytes())]
    moved = map_db(oid=RSA_OID, path=tmp_path / "moved.db")
    adb.answers[fireos.SIGNED_OK] = [
        f"{md5(data=moved.read_bytes())}  {fireos.MAP_DB}\n{fireos.SIGNED_OK}"
    ]
    adb.answers[f"> {fireos.MAP_DB}"] = [
        lambda: f"{md5(data=pushed[-1][0].read_bytes())}  {fireos.MAP_DB}"
    ]
    adb.answers["map.db"] = [lambda: copied(source=moved, target=adb.asked[-1][-1])]
    calls["waited"] = fireos6  # type: ignore[assignment]
    return calls


@pytest.fixture
def pushed(*, monkeypatch: pytest.MonkeyPatch) -> list[tuple[pathlib.Path, str]]:
    sent: list[tuple[pathlib.Path, str]] = []
    monkeypatch.setattr(
        name="push_checked",
        target=fireos,
        value=lambda **o: sent.append((o["local"], str(o["remote"]))),
    )
    return sent


@pytest.fixture
def scripts(*, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    ran: dict[str, str] = {}

    def adb_script(*, body: str, name: str, work: pathlib.Path) -> bool:
        del work
        ran[name] = body
        return name not in ran.get("fail", "")

    monkeypatch.setattr(name="adb_script", target=fireos, value=adb_script)
    return ran


def clock(*, monkeypatch: pytest.MonkeyPatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: sum(slept))
    monkeypatch.setattr(name="sleep", target=fireos.time, value=slept.append)
    return slept


def copied(*, source: pathlib.Path, target: str) -> str:
    shutil.copyfile(source, target)
    return ""


def ended(*, rc: int) -> str:
    return f"{fireos.BOOT_ROOT_INSTALL}\nI:Updater process ended with RC={rc}\nzip-ok"


def map_db(
    *, oid: bytes, path: pathlib.Path, signature: bytes | None = None
) -> pathlib.Path:
    key = base64.b64encode(b"\x30\x82\x04\xbd\x02\x01\x00\x30\x0d\x06" + oid + b"KEY")
    with contextlib.closing(sqlite3.connect(str(path))) as database, database:
        database.execute(
            "CREATE TABLE deviceData (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
        )
        rows = [("registration_state", b"REGISTERED"), (fireos.PRIVATE_KEY, key)]
        if signature is not None:
            rows.append((fireos.SIGNATURE, signature))
        database.executemany("INSERT INTO deviceData VALUES (?, ?)", rows)
    return path


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def package(*, data: bytes, path: pathlib.Path, transfer: str) -> pathlib.Path:
    with zipfile.ZipFile(file=path, mode="w") as archive:
        archive.writestr(data=transfer, zinfo_or_arcname="system.transfer.list")
        archive.writestr(data=data, zinfo_or_arcname="system.new.dat")
    return path


def signature(*, path: pathlib.Path) -> object:
    with contextlib.closing(sqlite3.connect(str(path))) as database:
        row = database.execute(
            "SELECT value FROM deviceData WHERE key = ?", (fireos.SIGNATURE,)
        ).fetchone()
    return row and row[0]


@pytest.mark.parametrize("waiting", ["migrated-ok", fireos.VERIFIED_OK])
def test_a_4315_that_restarts_into_twrp_stops_the_wait_at_once(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    monkeypatch: pytest.MonkeyPatch,
    waiting: str,
) -> None:
    del migration
    slept = clock(monkeypatch=monkeypatch)
    adb.answers[waiting] = [waiting]
    adb.answers["get-state"] = ["recovery", "device", "recovery"]
    with pytest.raises(FatalError, match="restarted into TWRP while"):
        fireos.stage_install_fireos6()
    assert sum(slept) < fireos.SETUP_WAIT
    assert adb.commands(holding="twrp install /sdcard/update.zip") == []


def test_a_4315_wait_passes_over_the_twrp_it_restarted_from(
    *, adb: FakeAdb, migration: dict[str, list[object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del migration
    clock(monkeypatch=monkeypatch)
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = ["mounted\nmoving\nstaged-ok"]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "a", "b", "b", "a", "a")
    ]
    adb.answers["get-state"] = [
        "recovery",
        "error: no devices/emulators found",
        subprocess.TimeoutExpired(cmd="adb", timeout=30),
        "recovery",
        "device",
    ]
    adb.answers[fireos.VERIFIED_OK] = [
        *[fireos.VERIFIED_OK] * 4,
        f"true\n{fireos.VERIFIED_OK}",
    ]
    fireos.stage_install_fireos6()
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2


def test_a_boot_image_that_does_not_verify_stops_fire_os_5(
    *, adb: FakeAdb, fireos5: list[dict[str, object]]
) -> None:
    adb.answers["bs=4096 count=2"] = [""]
    with pytest.raises(
        FatalError,
        match=r"did not verify on the Echo Dot \(2nd Generation\): read nothing",
    ):
        fireos.stage_install_fireos()
    assert len(fireos5) == 1


@pytest.mark.usefixtures("fireos6")
def test_a_boot_root_error_stops_the_run(*, adb: FakeAdb) -> None:
    adb.answers["boot-root.zip"] = ["Installing\n(!) Error: no space"]
    with pytest.raises(FatalError, match=r"boot-root\.zip failed: \(!\) Error"):
        fireos.stage_install_fireos6()


@pytest.mark.parametrize(
    ("said", "stops"),
    [
        ("boot=1 init=ROLLBACK\nmigrated-ok", "ended ROLLBACK."),
        (
            "boot=1 init=MIGRATION_PUFFIN_FINISH\nmigrated-ok",
            "ended MIGRATION_PUFFIN_FINISH with no registration",
        ),
    ],
)
def test_a_migration_that_fails_stops_before_the_upgrade(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    said: str,
    stops: str,
) -> None:
    del migration
    adb.answers["migrated-ok"] = [said]
    with pytest.raises(FatalError, match=re.escape(stops)) as stopped:
        fireos.stage_install_fireos6()
    assert "--factory-reset" in stopped.value.message
    assert adb.commands(holding="twrp install /sdcard/update.zip") == []


def test_a_migration_that_never_ends_stops_after_ten_minutes(
    *, adb: FakeAdb, migration: dict[str, list[object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del migration
    slept = clock(monkeypatch=monkeypatch)
    adb.answers["migrated-ok"] = [
        "boot= init=\nmigrated-ok",
        subprocess.TimeoutExpired(cmd="adb", timeout=30),
        "boot=1 init=MIGRATION_START\nmigrated-ok",
    ]
    with pytest.raises(FatalError, match="within 10 minutes"):
        fireos.stage_install_fireos6()
    assert sum(slept) > fireos.MIGRATE_WAIT


@pytest.mark.parametrize(
    ("content", "message"), [(None, "cannot be read"), (b"\n", "is empty")]
)
def test_a_missing_or_empty_adb_key_stops_before_any_write(
    *,
    adb: FakeAdb,
    content: bytes | None,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    folder = tmp_path / "other"
    folder.mkdir()
    monkeypatch.setattr(name="HOST_KEY", target=fireos, value=folder / "adbkey.pub")
    if content is not None:
        (folder / "adbkey.pub").write_bytes(content)
    with pytest.raises(FatalError, match=f"adbkey.pub {message}.*nothing was written"):
        fireos.adb_key()
    assert (["adb", "start-server"] in adb.asked) == (content is None)


def test_a_rooted_dot_swaps_its_twrp_for_the_target_s(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    bboe = tmp_path / "bboe.img"
    bboe.write_bytes(b"B" * 1024)
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: bboe)
    monkeypatch.setattr(
        name="read_recovery", target=fireos, value=lambda **_: bboe.read_bytes()
    )
    label = f"TWRP {biscuit.BBOE_TWRP_VERSION}"
    fireos.stage_swap_twrp()
    assert adb.asked[0][:3] == ["adb", "push", str(bboe)]
    assert label in fireos.PROGRESS.line
    monkeypatch.setattr(name="read_recovery", target=fireos, value=lambda **_: b"x")
    with pytest.raises(FatalError, match=f"{label} did not verify in recovery"):
        fireos.stage_swap_twrp()


def test_a_short_new_data_file_stops_the_build() -> None:
    with pytest.raises(FatalError, match=r"p's system\.new\.dat is short"):
        b"".join(
            fireos.system_chunks(
                name="p", new_data=io.BytesIO(b"a" * 100), ranges=[(0, 1)]
            )
        )


def test_a_staged_report_that_failed_asks_a_booted_dot_to_restart(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    adb.answers["queue-clear"] = [
        "queue-clear\nstaged\nMapMigrationSuccess=0\nstaged-ok"
    ]
    with pytest.raises(FatalError, match="Restart it") as stopped:
        fireos.check_staged(booted=True)
    assert "MapMigrationSuccess did not succeed" in stopped.value.message


def test_a_system_image_is_built_once_from_the_package(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    data = b"S" * 2 * BLOCK
    path = package(
        data=data,
        path=tmp_path / "fireos.bin",
        transfer="3\n4\n0\n0\nerase 2,0,4\nnew 2,0,2\n",
    )
    download = fireos.Download(name="fireos.bin", sha256="ab" * 32, url="")
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: path)
    slices, want, blocks = fireos.system_image(package=download)
    whole = b"".join(gzip.decompress(data=piece.read_bytes()) for piece in slices)
    assert whole == data + bytes(2 * BLOCK)
    assert want == md5(data=whole)
    assert blocks == 4
    assert slices[0].parent == fireos.CACHE / "system-abababababab"
    monkeypatch.setattr(
        name="build_system", target=fireos, value=lambda **_: pytest.fail("rebuilt")
    )
    assert fireos.system_image(package=download) == (slices, want, blocks)


@pytest.mark.parametrize(
    "transfer",
    [
        "4\n4\n0\n0\nerase 2,0,4\nmove 2,0,2\n",
        "3\n4\n0\n0\nerase 2,0,4\nnew 4,2,4,0,2\n",
        "3\n4\n0\n0\nerase 2,0,4\n",
    ],
)
def test_a_transfer_list_this_does_not_read_stops_the_build(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, transfer: str
) -> None:
    path = package(data=b"", path=tmp_path / "fireos.bin", transfer=transfer)
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: path)
    with pytest.raises(FatalError, match="has a transfer list this does not read"):
        fireos.build_system(
            package=fireos.Download(name="fireos.bin", sha256="0" * 64, url=""),
            target=tmp_path / "system",
        )
    assert not (tmp_path / "system").exists()


def test_a_version_4_list_with_zero_ranges_builds_the_system(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    data = b"S" * 2 * BLOCK
    path = package(
        data=data,
        path=tmp_path / "bridge.bin",
        transfer="4\n4\n0\n0\nnew 2,0,2\nzero 2,2,3\nerase 2,3,4\n",
    )
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: path)
    slices, want, blocks = fireos.system_image(
        package=fireos.Download(name="bridge.bin", sha256="cd" * 32, url="")
    )
    whole = b"".join(gzip.decompress(data=piece.read_bytes()) for piece in slices)
    assert whole == data + bytes(2 * BLOCK)
    assert (want, blocks) == (md5(data=whole), 4)


def test_an_updater_hidden_on_a_later_try_waits_twice_as_long_each_time(
    *,
    adb: FakeAdb,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    slept = clock(monkeypatch=monkeypatch)
    adb.answers["dumpsys package"] = [
        *["  User 0: hidden=false"] * 3,
        "  User 0: hidden=true",
    ]
    fireos.hide_updater()
    assert len(adb.commands(holding="pm hide " + fireos.UPDATER)) == 3
    assert slept == [1, 2]
    assert capsys.readouterr().out.count("not hidden yet") == 1


def test_an_updater_that_stays_visible_stops_the_run_after_a_minute(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept = clock(monkeypatch=monkeypatch)
    adb.answers["dumpsys package"] = ["  User 0: hidden=false"]
    with pytest.raises(FatalError, match="is not hidden"):
        fireos.hide_updater()
    assert slept == [1, 2, 4, 8, 16, 29]
    assert len(adb.commands(holding="pm hide " + fireos.UPDATER)) == 7


@pytest.mark.parametrize(("said", "warned"), [("erased-ok", 0), ("rm: busy", 1)])
@pytest.mark.parametrize("wiped", [True, False])
def test_erased_warns_when_the_delete_does_not_report_back(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    warned: int,
    wiped: bool,
) -> None:
    warnings: list[dict] = []
    monkeypatch.setattr(
        name="warn", target=fireos, value=lambda **said: warnings.append(said)
    )
    adb.answers["/sdcard/x.zip"] = [said]
    fireos.erased(path="/sdcard/x.zip", wiped=wiped)
    assert len(warnings) == warned
    assert ("if=/dev/zero" in adb.commands(holding="x.zip")[0]) == wiped


def test_fire_os_5_5_5_4_moves_its_setup_through_4315_then_installs_the_target(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    pushed: list[tuple[pathlib.Path, str]],
) -> None:
    fireos.stage_install_fireos6()
    assert len(migration["confirm"]) == 1
    assert migration["system"] == [
        fireos.BUILDS[BISCUIT][fireos.MIGRATE_BUILD],
        f"{fireos.BY_NAME}/system_a",
    ]
    assert [remote for _, remote in pushed] == [
        "/tmp/boot.img",
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
        "/tmp/map.db",
        "/sdcard/update.zip",
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
    ]
    assert f"of={fireos.BY_NAME}/boot_a" in adb.commands(holding="of=")[0]
    assert len(adb.commands(holding=f"> {fireos.MAP_DB}")) == 1
    assert adb.commands(holding="twrp wipe") == []
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2
    assert len(adb.commands(holding="twrp install /sdcard/boot-root.zip")) == 2
    assert ["adb", "reboot", "recovery"] in adb.asked
    assert migration["waited"] == ["twrp", "twrp"]
    assert fireos.PROGRESS.steps == fireos.PROGRESS.step
    assert adb.asked[-1] == ["adb", "reboot"]


def test_fire_os_5_before_the_preloader_takes_its_slot_and_does_not_reboot(
    *, adb: FakeAdb, fireos5: list[dict[str, object]]
) -> None:
    fireos.stage_install_fireos(reboot=False, slot="_a")
    assert fireos5[0]["system"] == f"{fireos.BY_NAME}/system_a"
    assert adb.commands(holding="slot_suffix") == []
    assert ["adb", "reboot"] not in adb.asked


def test_fire_os_5_goes_in_and_the_dot_reboots(
    *,
    adb: FakeAdb,
    fireos5: list[dict[str, object]],
    pushed: list[tuple[pathlib.Path, str]],
    scripts: dict[str, str],
) -> None:
    fireos.stage_install_fireos()
    system = f"{fireos.BY_NAME}/system_b"
    assert fireos5[0]["system"] == system
    assert fireos5[0]["blocks"] == 8
    assert scripts["data.sh"] == fireos.Shell.DATA.value
    assert f"mount -t ext4 {system}" in scripts["system.sh"]
    assert all(host in scripts["system.sh"] for host in fireos.UPDATE_HOSTS)
    assert pushed[0][1] == str(fireos.DOT_TEMPORARY_DIRECTORY / "boot.img")
    assert f"of={fireos.BY_NAME}/boot_b_x" in adb.commands(holding="dd if=")[0]
    assert "magisk" in fireos5[1]
    assert adb.asked[-1] == ["adb", "reboot"]


def test_fire_os_5_refuses_a_slot_it_does_not_know(
    *, adb: FakeAdb, fireos5: list[dict[str, object]]
) -> None:
    adb.answers["slot_suffix"] = [""]
    with pytest.raises(FatalError, match="TWRP reports the boot slot ''"):
        fireos.stage_install_fireos()
    assert fireos5 == []


@pytest.mark.parametrize(
    ("fail", "said"),
    [("data.sh", "userdata did not format"), ("system.sh", "patching /system failed")],
)
def test_fire_os_5_stops_where_a_script_fails(
    *, fail: str, fireos5: list[dict[str, object]], said: str, scripts: dict[str, str]
) -> None:
    del fireos5
    scripts["fail"] = fail
    with pytest.raises(FatalError, match=said):
        fireos.stage_install_fireos()


@pytest.mark.parametrize(
    ("key", "said", "stops"),
    [
        (
            "build-ok",
            "mount-ok\nro.build.version.name=Fire OS 5.5.4.9 (672720020)\nbuild-ok",
            "holds Fire OS 5.5.4.9. Only Fire OS 5.5.5.4",
        ),
        ("queue-clear", "adb: device offline", "did not say whether"),
        ("queue-clear", "staged\nMapMigrationSuccess=1\nstaged-ok", "queued"),
        (
            "queue-clear",
            (
                "queue-clear\nstaged\nMapMigrationSuccess=1\nWifiConfigSuccess=0\n"
                "staged-ok"
            ),
            "WifiConfigSuccess did not succeed",
        ),
        (
            "queue-clear",
            "queue-clear\nMapMigrationSuccess=1\nstaged-ok",
            "missing or incomplete",
        ),
        ("echo pending", "adb: device offline", "still has a setup to move"),
    ],
)
@pytest.mark.usefixtures("migration")
def test_fire_os_5_that_cannot_move_its_setup_stops_before_any_write(
    *,
    adb: FakeAdb,
    key: str,
    pushed: list[tuple[pathlib.Path, str]],
    said: str,
    stops: str,
) -> None:
    adb.answers[key] = [said]
    if key == "echo pending":
        adb.answers["build-ok"] = [
            "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
        ]
    with pytest.raises(FatalError, match=re.escape(stops)):
        fireos.stage_install_fireos6()
    assert pushed == []
    assert adb.commands(holding="of=") == []
    assert adb.commands(holding="twrp wipe") == []


def test_fire_os_6_4315_folds_a_moved_setup_s_wal_into_what_it_writes(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    pushed: list[tuple[pathlib.Path, str]],
    tmp_path: pathlib.Path,
) -> None:
    del migration
    source = tmp_path / "source"
    source.mkdir()
    database = sqlite3.connect(str(source / "map.db"))
    database.execute("PRAGMA journal_mode=WAL")
    database.execute("PRAGMA wal_autocheckpoint=0")
    database.execute(
        "CREATE TABLE deviceData (key TEXT PRIMARY KEY, value BLOB NOT NULL)"
    )
    database.commit()
    database.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    key = base64.b64encode(b"\x30\x82\x04\xbd\x02\x01\x00\x30\x0d\x06" + RSA_OID)
    database.execute("INSERT INTO deviceData VALUES (?, ?)", (fireos.PRIVATE_KEY, key))
    database.commit()
    snapshot = tmp_path / "snapshot"
    shutil.copytree(source, snapshot)
    database.close()
    files = {
        f"{fireos.MAP_DB}{suffix}": snapshot / f"map.db{suffix}"
        for suffix in ("", "-wal")
    }
    adb.answers[fireos.SIGNED_OK] = [
        "\n".join(
            f"{md5(data=file.read_bytes())}  {name}" for name, file in files.items()
        )
        + f"\n{fireos.SIGNED_OK}"
    ]
    adb.answers["map.db"] = [
        lambda: copied(source=files[adb.asked[-1][-2]], target=adb.asked[-1][-1])
    ]
    kept = tmp_path / "written.db"
    adb.answers[f"> {fireos.MAP_DB}"] = [
        lambda: (
            f"{copied(source=pushed[-1][0], target=str(kept))}"
            f"{md5(data=kept.read_bytes())}  {fireos.MAP_DB}"
        )
    ]
    fireos.sign_setup()
    assert signature(path=kept) == b"SHA256WithRSA:1.0"
    assert f"{fireos.MAP_DB}-wal" in adb.commands(holding=f"> {fireos.MAP_DB}")[0]


def test_fire_os_6_4315_leaves_a_setup_that_already_signs(
    *, tmp_path: pathlib.Path
) -> None:
    path = map_db(oid=RSA_OID, path=tmp_path / "map.db", signature=b"kept")
    before = path.read_bytes()
    assert not fireos.signature_added(path=path)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("device", "said"),
    [(BISCUIT, "mounted\nstaged-ok"), (RADAR, "mounted\nmoving\nstaged-ok")],
)
def test_fire_os_6_4315_never_moved_into_upgrades_as_any_older_build(
    *,
    adb: FakeAdb,
    device: object,
    migration: dict[str, list[object]],
    monkeypatch: pytest.MonkeyPatch,
    said: str,
) -> None:
    del migration
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[device]["fireos6"]
    )
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = [said]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "b", "b", "a")
    ]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="start otad") == []
    assert adb.commands(holding=fireos.SIGNED_OK) == []
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2


def test_fire_os_6_4315_reads_a_device_key_stored_as_pem() -> None:
    body = base64.b64encode(b"\x30\x82" + RSA_OID + b"KEY" * 40)
    pem = b"\n".join([
        b"-----BEGIN PRIVATE KEY-----",
        body[:64],
        body[64:],
        b"-----END PRIVATE KEY-----",
    ])
    assert fireos.key_type(value=pem) == "RSA"


@pytest.mark.parametrize(
    ("oid", "value"),
    [(RSA_OID, b"SHA256WithRSA:1.0"), (EC_OID, b"SHA256WithECDSA:1.0")],
)
def test_fire_os_6_4315_signs_its_moved_setup_with_its_key_s_algorithm(
    *, oid: bytes, tmp_path: pathlib.Path, value: bytes
) -> None:
    path = map_db(oid=oid, path=tmp_path / "map.db")
    assert fireos.signature_added(path=path)
    assert signature(path=path) == value


@pytest.mark.parametrize(
    ("said", "pulled"),
    [
        (fireos.SIGNED_OK, True),
        (f"{'0' * 32}  {fireos.MAP_DB}\n{fireos.SIGNED_OK}", True),
        (None, False),
    ],
)
def test_fire_os_6_4315_stops_on_a_moved_setup_it_cannot_read(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    pulled: bool,
    said: str | None,
) -> None:
    del migration
    adb.answers["echo pending"] = ["staged-ok"]
    if said is not None:
        adb.answers[fireos.SIGNED_OK] = [said]
    if not pulled:
        adb.answers["map.db"] = [(1, "adb: error: remote object does not exist")]
    with pytest.raises(FatalError, match="could not be read in TWRP"):
        fireos.sign_setup()
    assert adb.commands(holding=f"> {fireos.MAP_DB}") == []


def test_fire_os_6_4315_stops_on_a_moved_setup_that_does_not_verify(
    *, adb: FakeAdb, migration: dict[str, list[object]]
) -> None:
    del migration
    adb.answers[f"> {fireos.MAP_DB}"] = [f"{'0' * 32}  {fireos.MAP_DB}"]
    with pytest.raises(FatalError, match="did not verify"):
        fireos.sign_setup()


@pytest.mark.parametrize("oid", [b"", None])
def test_fire_os_6_4315_stops_on_a_moved_setup_with_no_usable_key(
    *,
    adb: FakeAdb,
    migration: dict[str, list[object]],
    oid: bytes | None,
    tmp_path: pathlib.Path,
) -> None:
    del migration
    moved = tmp_path / "other.db"
    if oid is None:
        moved.write_bytes(b"not a database" * 100)
    else:
        map_db(oid=oid, path=moved)
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = ["mounted\nmoving\nverified\nstaged-ok"]
    adb.answers[fireos.SIGNED_OK] = [
        f"{md5(data=moved.read_bytes())}  {fireos.MAP_DB}\n{fireos.SIGNED_OK}"
    ]
    adb.answers["map.db"] = [lambda: copied(source=moved, target=adb.asked[-1][-1])]
    with pytest.raises(FatalError, match="no device key") as stopped:
        fireos.stage_install_fireos6()
    assert "--factory-reset" in stopped.value.message
    assert adb.commands(holding="twrp install /sdcard/update.zip") == []


def test_fire_os_6_4315_stops_when_twrp_does_not_mount_data(
    *, adb: FakeAdb, migration: dict[str, list[object]]
) -> None:
    del migration
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = ["staged-ok"]
    with pytest.raises(FatalError, match="could not mount") as stopped:
        fireos.stage_install_fireos6()
    assert "--factory-reset" in stopped.value.message
    assert adb.commands(holding="start otad") == []


def test_fire_os_6_4315_that_never_finishes_its_setup_stops_after_five_minutes(
    *, adb: FakeAdb, migration: dict[str, list[object]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del migration
    slept = clock(monkeypatch=monkeypatch)
    adb.answers[fireos.VERIFIED_OK] = [
        fireos.VERIFIED_OK,
        subprocess.TimeoutExpired(cmd="adb", timeout=30),
        f"false\n{fireos.VERIFIED_OK}",
    ]
    with pytest.raises(FatalError, match="within 5 minutes") as stopped:
        fireos.stage_install_fireos6()
    assert "Wi-Fi" in stopped.value.message
    assert sum(slept) > fireos.SETUP_WAIT
    assert adb.commands(holding="stop otad") != []
    assert adb.commands(holding="twrp install /sdcard/update.zip") == []


def test_fire_os_6_4315_with_a_moved_setup_still_to_finish_finishes_it_first(
    *, adb: FakeAdb, migration: dict[str, list[object]]
) -> None:
    del migration
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = ["mounted\nmoving\nstaged-ok"]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "a", "b", "b", "a", "a")
    ]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="migrated-ok") == []
    assert len(adb.commands(holding="start otad")) == 1
    assert len(adb.commands(holding="stop otad")) == 1
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2


def test_fire_os_6_4315_with_a_setup_still_to_move_starts_before_the_upgrade(
    *, adb: FakeAdb, migration: dict[str, list[object]]
) -> None:
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "a", "b", "b", "a", "a")
    ]
    fireos.stage_install_fireos6()
    assert migration["confirm"] == []
    assert migration["system"] == []
    assert len(adb.commands(holding="migrated-ok")) == 1
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2


def test_fire_os_6_4315_with_no_setup_to_move_upgrades_at_once(
    *, adb: FakeAdb, migration: dict[str, list[object]]
) -> None:
    del migration
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.5.5 (NS6555/4315)\nbuild-ok"
    ]
    adb.answers["echo pending"] = ["mounted\nmoving\nverified\nstaged-ok"]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "b", "b", "a")
    ]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="migrated-ok") == []
    assert adb.commands(holding="start otad") == []
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_counts_the_install_by_the_name_ps_prints(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    fireos.stage_install_fireos6()
    assert "ps -A | grep -c update_engine;" in adb.commands(holding="get_active")[0]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_disables_otad_and_blocks_the_update_hosts(*, adb: FakeAdb) -> None:
    fireos.stage_install_fireos6()
    [command] = adb.commands(holding="updates-ok")
    assert "/system_$s $m" in command
    assert "&\\n    disabled|" in command
    assert "|| { echo fos6-$s; continue; }" in command
    assert "if [ -f $p ] && [ -f $h ]; then" in command
    assert "$m/*.rc $m/system/etc/init/*.rc" in command
    assert "sed -i 's|^service update_engine .*|&\\n    disabled|' $u" in command
    assert (
        "[ -n \"$u\" ] && ! sed -n '/^service update_engine /,/^[^ ]/p' $u" in command
    )
    assert "[ -n \"$r\" ] && ! grep -h -A 1 '^service otad ' $r" in command
    assert all(host in command for host in fireos.UPDATE_HOSTS)
    assert adb.asked[-1] == ["adb", "reboot"]


def test_fire_os_6_goes_into_both_slots_then_boot_root(
    *, adb: FakeAdb, fireos6: list[str], pushed: list[tuple[pathlib.Path, str]]
) -> None:
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed] == [
        "/sdcard/update.zip",
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
    ]
    erased = adb.commands(holding="if=/dev/zero")
    assert [command.split("1<>")[1].split()[0] for command in erased] == [
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
    ]
    assert (
        adb.commands(holding="twrp install /sdcard/update.zip")
        == ["twrp install /sdcard/update.zip"] * 2
    )
    assert adb.commands(holding="twrp wipe") == ["twrp wipe cache", "twrp wipe data"]
    said = [words[-1] for words in adb.asked]
    for zipped, ended in (
        ("update.zip", "get_active"),
        ("boot-root.zip", "Updater process ended"),
    ):
        erase = max(
            at for at, each in enumerate(said) if f"1<>/sdcard/{zipped}" in each
        )
        install = max(
            at
            for at, each in enumerate(said)
            if each == f"twrp install /sdcard/{zipped}"
        )
        assert any(ended in each for each in said[install:erase])
    assert fireos6 == ["twrp"]
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_installs_the_default_over_an_older_build_and_keeps_data(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
) -> None:
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "b", "b", "a")
    ]
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6574.1 (NS65741/8146)\nbuild-ok"
    ]
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed][0::2] == [
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
    ]
    assert adb.commands(holding="twrp wipe") == []
    assert len(adb.commands(holding="twrp install /sdcard/update.zip")) == 2
    assert fireos.PROGRESS.steps == fireos.PROGRESS.step
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_installs_where_no_fire_os_6_is_installed(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
) -> None:
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    monkeypatch.setattr(name="steps", target=fireos.PROGRESS, value=3)
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "a", "b", "b", "a")
    ]
    adb.answers["build-ok"] = ["mount-ok\nbuild-ok"]
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed] == [
        "/sdcard/update.zip",
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
    ]
    assert fireos.PROGRESS.steps == 6


@pytest.mark.parametrize(
    ("said", "stops"),
    [
        (
            "mount-ok\nro.build.version.name=Fire OS 6599.1 (NS6599/8999)\nbuild-ok",
            (
                r"\(NS6599/8999\), a Fire OS 6 build firebreak does not know.*"
                " --factory-reset"
            ),
        ),
        ("adb: device 'G090' not found", "did not say which Fire OS slot a holds"),
        ("mount: Invalid argument\nbuild-ok", "did not mount slot a's system"),
    ],
)
@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_leaves_a_slot_it_cannot_patch_alone(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
    said: str,
    stops: str,
) -> None:
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    adb.answers["build-ok"] = [said]
    with pytest.raises(FatalError, match=stops) as stopped:
        fireos.stage_install_fireos6()
    assert "its Fire OS and data are as they were" in stopped.value.message
    assert "not modified" not in stopped.value.message
    assert pushed == []
    assert adb.commands(holding="twrp wipe") == []


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_leaves_a_system_that_already_started_alone(*, adb: FakeAdb) -> None:
    adb.answers["reboot"] = [(1, "no devices")]
    adb.answers["get-state"] = ["device"]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="reboot") == ["reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_locks_adb_to_this_computer_s_key(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    keys: list[bytes] = []
    monkeypatch.setattr(
        name="push_checked",
        target=fireos,
        value=lambda **o: (
            keys.append(o["local"].read_bytes())
            if o["remote"] == fireos.ADB_KEY
            else None
        ),
    )
    fireos.stage_install_fireos6()
    [command] = adb.commands(holding="updates-ok")
    assert "sed -i 's|^ro.adb.secure=.*|ro.adb.secure=1|' $p" in command
    assert "cat /tmp/adbkey.pub > $m/adb_keys" in command
    assert "cmp -s /tmp/adbkey.pub $m/adb_keys && echo locked-$s" in command
    assert "rm -f /tmp/adbkey.pub" in command
    assert keys == [ADB_KEY]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_patches_the_installed_build_unless_reset(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    pushed: list[tuple[pathlib.Path, str]],
) -> None:
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    adb.answers["bcbtool get_active"] = ["0\nb\nslot-ok"]
    adb.answers["build-ok"] = [
        "mount-ok\nro.build.version.name=Fire OS 6.5.7.5 (NS6575/8349)\nbuild-ok"
    ]
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed] == [
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
    ]
    assert adb.commands(holding="twrp wipe") == []
    assert adb.commands(holding="/dev/zero") == []
    assert adb.commands(holding="rm -f /sdcard") == [
        fireos.Shell.DELETED.value.format(
            ok=fireos.ERASED_OK, path="/sdcard/boot-root.zip"
        )
    ]
    assert "system_b" in adb.commands(holding="build-ok")[0]
    assert "slot _b:" in adb.commands(holding="neutering")[0]
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_pushes_the_ota_once_when_it_is_still_there(
    *, adb: FakeAdb, pushed: list[tuple[pathlib.Path, str]]
) -> None:
    adb.answers["md5sum /sdcard/update.zip"] = [
        hashlib.md5(b"ota", usedforsecurity=False).hexdigest() + "  /sdcard/update.zip"
    ]
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed] == [
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
        "/tmp/adbkey.pub",
    ]
    assert len(adb.commands(holding="1<>/sdcard/update.zip")) == 1


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_reads_the_slot_past_output_adb_merged_in(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["bcbtool get_active"] = [
        f"ps: unknown option\n0\n{slot}\nslot-ok" for slot in ("a", "b", "b", "a")
    ]
    fireos.stage_install_fireos6()
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_reboots_again_when_adb_stays_silent(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["reboot"] = [(1, "no devices"), (0, "")]
    adb.answers["get-state"] = [
        subprocess.TimeoutExpired(cmd="adb", timeout=30),
        "error: no devices/emulators found",
    ]
    fireos.stage_install_fireos6()
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_refuses_the_boot_moved_table(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="partition_table", target=fireos, value=lambda: " 1 boot_a_x\n"
    )
    with pytest.raises(FatalError, match=r"runs on a boot moved partition table"):
        fireos.stage_install_fireos6()
    assert adb.commands(holding="twrp wipe") == []


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_restarts_a_donut_into_twrp_through_fastboot(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[DONUT]["fireos6"]
    )
    asked: list[bytes] = []
    monkeypatch.setattr(
        name="ask_fastboot",
        target=fireos,
        value=lambda **options: asked.append(options["command"]),
    )
    answers = iter((False, True))
    monkeypatch.setattr(name="in_fastboot", target=fireos, value=lambda: next(answers))
    fireos.install_fireos6(wipe=True)
    assert asked == [TARGETS[DONUT]["fireos6"].device.fastboot_command]
    assert ["adb", "reboot", "recovery"] not in adb.asked
    restart = adb.asked.index(["adb", "reboot"])
    assert adb.asked[restart + 1][-2:] == ["oem", "reboot-recovery"]
    monkeypatch.setattr(
        name="restart_refusals",
        target=fireos,
        value=lambda: [("fastboot reboot-recovery", "FAILED")],
    )
    answers = iter((True,))
    with pytest.raises(FatalError, match="took neither command"):
        fireos.twrp_by_fastboot(command=b"x")
    assert fireos.install_steps() == fireos.INSTALL_STEPS + 1


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_says_to_power_cycle_when_the_reboot_never_goes(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["reboot"] = [(1, "no devices")]
    adb.answers["get-state"] = ["recovery"]
    with pytest.raises(FatalError, match=r"boot-root\.zip is installed"):
        fireos.stage_install_fireos6()
    assert len(adb.commands(holding="reboot")) == fireos.PUSH_TRIES


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_a_donut_never_reaches_fastboot(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[DONUT]["fireos6"]
    )
    monkeypatch.setattr(name="ask_fastboot", target=fireos, value=lambda **_: None)
    monkeypatch.setattr(name="in_fastboot", target=fireos, value=lambda: False)
    monkeypatch.setattr(name="FASTBOOT_WAIT", target=fireos, value=-1)
    with pytest.raises(FatalError, match="did not reach fastboot"):
        fireos.install_fireos6(wipe=True)


@pytest.mark.parametrize(
    ("said", "slots"),
    [
        ("fos6-a\noff-a\nfos6-b\noff-b\nlocked-b\nupdates-ok", "slot a"),
        ("fos6-a\noff-a\nfos6-b\noff-b\nupdates-ok", "slot a and b"),
    ],
)
@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_adb_stays_open_in_a_slot(
    *, adb: FakeAdb, said: str, slots: str
) -> None:
    adb.answers["updates-ok"] = [said]
    with pytest.raises(
        FatalError, match=f"not locked to this computer's key in Fire OS 6's {slots}\\."
    ):
        fireos.stage_install_fireos6()
    assert ["adb", "reboot"] not in adb.asked


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_boot_root_ends_badly(*, adb: FakeAdb) -> None:
    adb.answers["Installing zip file"] = [ended(rc=1)]
    with pytest.raises(FatalError, match=r"boot-root\.zip failed: I:Updater .* RC=1"):
        fireos.stage_install_fireos6()
    assert ["adb", "reboot"] not in adb.asked


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_boot_root_is_killed(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["Installing zip file"] = [
        f"{fireos.BOOT_ROOT_INSTALL}\nI:Updater process ended with signal: 9\nzip-ok"
    ]
    with pytest.raises(FatalError, match=r"boot-root\.zip failed: .*signal: 9"):
        fireos.stage_install_fireos6()


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_boot_root_never_ends(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    adb.answers["Installing zip file"] = [f"{fireos.BOOT_ROOT_INSTALL}\nzip-ok"]
    adb.answers["bcbtool get_active"] = [
        f"0\n{slot}\nslot-ok" for slot in ("a", "b", "b", "a")
    ]
    clock = itertools.count(step=100)
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: next(clock))
    with pytest.raises(FatalError, match="did not finish installing boot-root"):
        fireos.stage_install_fireos6()


@pytest.mark.parametrize("said", ["0\nzip-ok", "adb: device 'G090' not found"])
@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_boot_root_patched_no_slot(
    *, adb: FakeAdb, said: str
) -> None:
    adb.answers["neutering ota updates"] = [said]
    with pytest.raises(FatalError, match="ended without patching slot a"):
        fireos.stage_install_fireos6()
    assert ["adb", "reboot"] not in adb.asked


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_the_slot_never_reads(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = itertools.count(step=400)
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: next(clock))
    adb.answers["bcbtool get_active"] = ["1\na\nslot-ok"]
    with pytest.raises(FatalError, match="did not report its active slot"):
        fireos.stage_install_fireos6()


@pytest.mark.parametrize(
    ("said", "slots"),
    [
        ("fos6-b\noff-b\nupdates-ok", "slot a"),
        ("fos6-a\noff-a\nfos6-b\nupdates-ok", "slot b"),
        ("fos6-b\nupdates-ok", "slot a and b"),
        ("off-a\noff-b", "slot a"),
        ("adb: device 'G090' not found", "slot a"),
    ],
)
@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_the_updates_stay_on_in_a_slot(
    *, adb: FakeAdb, said: str, slots: str
) -> None:
    adb.answers["updates-ok"] = [said]
    with pytest.raises(FatalError, match=f"not blocked in Fire OS 6's {slots}\\."):
        fireos.stage_install_fireos6()
    assert ["adb", "reboot"] not in adb.asked


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_that_leaves_the_slot_alone_stops_the_run(*, adb: FakeAdb) -> None:
    adb.answers["bcbtool get_active"] = ["0\na\nslot-ok"]
    with pytest.raises(FatalError, match="left the active slot 'a', where it was 'a'"):
        fireos.stage_install_fireos6()


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_tries_the_reboot_again(*, adb: FakeAdb) -> None:
    adb.answers["reboot"] = [(1, "no devices"), (0, "")]
    adb.answers["get-state"] = ["recovery"]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="get-state") == ["get-state"]
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_waits_for_boot_root_to_end(*, adb: FakeAdb) -> None:
    adb.answers["Installing zip file"] = [
        "adb: device 'G090' not found",
        f"I:Updater process ended with RC=0\n{fireos.BOOT_ROOT_INSTALL}\nzip-ok",
        ended(rc=0),
    ]
    fireos.stage_install_fireos6()
    assert len(adb.commands(holding="Installing zip file")) == 3
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_waits_out_a_drop_and_a_running_install(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["bcbtool get_active"] = [
        "0\na\nslot-ok",
        "adb: device 'G090' not found",
        "1\na\nslot-ok",
        "0\nb\nslot-ok",
        "0\nb\nslot-ok",
        "0\na\nslot-ok",
    ]
    fireos.stage_install_fireos6()
    assert len(adb.commands(holding="bcbtool get_active")) == 7


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_waits_out_an_adb_shell_that_hangs(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock(monkeypatch=monkeypatch)
    adb.answers["bcbtool get_active"] = [
        subprocess.TimeoutExpired(cmd="adb", timeout=30),
        *(f"0\n{slot}\nslot-ok" for slot in ("a", "b", "b", "a")),
    ]
    fireos.stage_install_fireos6()
    assert adb.asked[-1] == ["adb", "reboot"]


def test_leaving_an_older_fire_os_5_stops_before_the_reboot(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    adb.answers["ro.build.version.name"] = ["Fire OS 5.5.0.3 (564196920)"]
    with pytest.raises(FatalError, match=re.escape("holds Fire OS 5.5.0.3")):
        fireos.leave_fireos5(reboot=lambda: pytest.fail("rebooted"))


@pytest.mark.parametrize("reset", [False, True])
def test_leaving_fire_os_5_confirms_before_it_hides_or_clears_unless_reset(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch, reset: bool
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=reset)
    done: list[str] = []
    monkeypatch.setattr(
        name="hide_updater", target=fireos, value=lambda: done.append("hide")
    )
    monkeypatch.setattr(
        name="confirm", target=fireos, value=lambda **_: done.append("confirm")
    )
    adb.answers["ro.build.version.name"] = ["Fire OS 5.5.5.4 (680767620)"]
    adb.answers["queue-clear"] = [
        "queue-clear\nstaged\nMapMigrationSuccess=1\nstaged-ok"
    ]
    adb.answers[fireos.STAGING_OK] = [
        f"init=MIGRATION_CSM_FINISH service=stopped\n{fireos.STAGING_OK}"
    ]
    fireos.leave_fireos5(reboot=lambda: done.append("reboot"))
    assert done == (["reboot"] if reset else ["confirm", "hide", "reboot"])
    staged = adb.commands(holding="queue-clear")
    assert staged == ([] if reset else [staged[0]])
    assert all(command.startswith("su -c '") for command in staged)


def test_leaving_fire_os_5_on_a_radar_stops_before_the_reboot(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=False)
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[RADAR]["fireos6"]
    )
    adb.answers["ro.build.version.name"] = ["Fire OS 5.5.5.4 (680767620)"]
    with pytest.raises(FatalError, match="only on the Echo Dot") as stopped:
        fireos.leave_fireos5(reboot=lambda: pytest.fail("rebooted"))
    assert "--factory-reset" in stopped.value.message


@pytest.mark.usefixtures("magisk")
def test_magisk_goes_in_as_a_cpio_and_is_read_back(
    *,
    adb: FakeAdb,
    pushed: list[tuple[pathlib.Path, str]],
    scripts: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    files = b"database" + b"binary"
    adb.answers["md5sum"] = [md5(data=files) + "  -"]
    fireos.install_magisk(magisk=tmp_path / "magisk.zip", work=tmp_path)
    assert pushed[0][1].endswith("magisk.cpio")
    assert scripts["magisk.sh"] == fireos.Shell.MAGISK.value
    assert adb.commands(holding="md5sum") == [
        "cd /; cat data/adb/magisk.db data/adb/magisk/magisk | md5sum"
    ]


@pytest.mark.parametrize(("fail", "said"), [("magisk.sh", "did not install"), ("", "")])
@pytest.mark.usefixtures("magisk", "pushed")
def test_magisk_that_does_not_land_stops_the_run(
    *,
    adb: FakeAdb,
    fail: str,
    said: str,
    scripts: dict[str, str],
    tmp_path: pathlib.Path,
) -> None:
    scripts["fail"] = fail
    adb.answers["md5sum"] = ["0" * 32 + "  -"]
    with pytest.raises(FatalError, match=said or "files did not verify"):
        fireos.install_magisk(magisk=tmp_path / "magisk.zip", work=tmp_path)


def test_staging_that_never_ends_stops_before_the_reboot(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    slept: list[float] = []
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: sum(slept))
    monkeypatch.setattr(name="sleep", target=fireos.time, value=slept.append)
    adb.answers[fireos.STAGING_OK] = [
        f"init=MIGRATION_START service=running\n{fireos.STAGING_OK}"
    ]
    with pytest.raises(FatalError, match="did not finish copying"):
        fireos.wait_staged()


def test_staging_waits_for_this_boot_s_copy_to_end(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    slept: list[float] = []
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: sum(slept))
    monkeypatch.setattr(name="sleep", target=fireos.time, value=slept.append)
    adb.answers[fireos.STAGING_OK] = [
        f"init= service=\n{fireos.STAGING_OK}",
        f"init=MIGRATION_CSM_FINISH service=running\n{fireos.STAGING_OK}",
        "init=MIGRATION_CSM_FINISH service=stopped",
        f"init=MIGRATION_CSM_FINISH service=stopped\n{fireos.STAGING_OK}",
    ]
    fireos.wait_staged()
    assert slept == [5, 5, 5]


def test_the_adb_key_is_the_one_in_the_home_folder() -> None:
    assert fireos.adb_key() == ADB_KEY


@pytest.mark.parametrize("verified", [True, False])
@pytest.mark.usefixtures("pushed")
def test_the_bboe_twrp_replaces_v1_1_0_s(
    *,
    adb: FakeAdb,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    verified: bool,
) -> None:
    image = tmp_path / "twrp.img"
    image.write_bytes(b"T" * 1024)
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: image)
    adb.answers["count=2 2>/dev/null | md5sum"] = [
        md5(data=image.read_bytes()) if verified else "0" * 32
    ]
    if verified:
        fireos.stage_replace_twrp()
        assert adb.asked[-1][1:] == ["reboot", "recovery"]
        return
    with pytest.raises(FatalError, match="did not verify in recovery"):
        fireos.stage_replace_twrp()
    assert ["adb", "reboot", "recovery"] not in adb.asked


@pytest.mark.parametrize(
    ("reset", "confirmed", "installs"),
    [(False, False, False), (False, True, True), (True, False, True)],
)
def test_the_fire_os_5_twrp_installs_only_after_the_booted_check_or_a_reset(
    *, confirmed: bool, installs: bool, monkeypatch: pytest.MonkeyPatch, reset: bool
) -> None:
    monkeypatch.setattr(
        name="target", target=fireos.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    monkeypatch.setattr(name="factory_reset", target=fireos.ARGUMENTS, value=reset)
    fireos.SESSION.migration_confirmed = confirmed
    ran: list[str] = []
    if installs:
        fireos.from_fireos5_twrp(install=lambda: ran.append("install"))
        assert ran == ["install"]
        return
    with pytest.raises(FatalError, match="reboot") as stopped:
        fireos.from_fireos5_twrp(install=lambda: ran.append("install"))
    assert "nothing was written" in stopped.value.message
    assert ran == []


def test_the_migration_is_confirmed_once_per_run(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[dict[str, object]] = []
    monkeypatch.setattr(
        name="confirm", target=fireos, value=lambda **o: asked.append(o)
    )
    fireos.SESSION.no_wait = True
    fireos.confirm_migration()
    fireos.confirm_migration()
    assert len(asked) == 1
    assert asked[0]["force"] is True
    assert "Fire OS 6 4315" in str(asked[0]["what"])


def test_the_system_image_fills_the_gaps_between_ranges_with_zeros() -> None:
    data = io.BytesIO(b"a" * BLOCK + b"b" * 2 * BLOCK)
    chunks = b"".join(
        fireos.system_chunks(name="p", new_data=data, ranges=[(1, 2), (3, 5), (6, 6)])
    )
    assert chunks == (
        bytes(BLOCK) + b"a" * BLOCK + bytes(BLOCK) + b"b" * 2 * BLOCK + bytes(BLOCK)
    )


@pytest.mark.parametrize(
    ("answers", "hides"),
    [
        (["  User 0: installed=true hidden=true"], 0),
        (["  User 0: installed=true hidden=false", "  User 0: hidden=true"], 1),
    ],
)
def test_the_updater_is_hidden_once(
    *, adb: FakeAdb, answers: list[str], hides: int
) -> None:
    adb.answers["dumpsys package"] = answers
    fireos.hide_updater()
    assert len(adb.commands(holding="pm hide " + fireos.UPDATER)) == hides
