from __future__ import annotations

import gzip
import hashlib
import io
import itertools
import zipfile
from typing import TYPE_CHECKING

import pytest

from firebreak import fireos
from firebreak.devices import BISCUIT, State
from firebreak.ui import FatalError
from firebreak.unlocks.targets import TARGETS

if TYPE_CHECKING:
    import pathlib

    from conftest import FakeAdb

BLOCK = 4096
MAGISK_FILES = {
    b"data/adb": (0o40700, b""),
    b"data/adb/magisk.db": (0o100600, b"database"),
    b"data/adb/magisk/magisk": (0o100755, b"binary"),
}


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
        value=TARGETS[BISCUIT]["amonet-biscuit-v1.1.0-bboe"],
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
    monkeypatch.setattr(
        name="target",
        target=fireos.ARGUMENTS,
        value=TARGETS[BISCUIT]["amonet-biscuit-v2.0.0"],
    )
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


def ended(*, rc: int) -> str:
    return f"{fireos.BOOT_ROOT_INSTALL}\nI:Updater process ended with RC={rc}\nzip-ok"


def md5(*, data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def package(*, data: bytes, path: pathlib.Path, transfer: str) -> pathlib.Path:
    with zipfile.ZipFile(file=path, mode="w") as archive:
        archive.writestr(data=transfer, zinfo_or_arcname="system.transfer.list")
        archive.writestr(data=data, zinfo_or_arcname="system.new.dat")
    return path


def test_a_boot_image_that_does_not_verify_stops_fire_os_5(
    *, adb: FakeAdb, fireos5: list[dict[str, object]]
) -> None:
    adb.answers["bs=4096 count=2"] = [""]
    with pytest.raises(FatalError, match="did not verify on the Dot: read nothing"):
        fireos.stage_install_fireos()
    assert len(fireos5) == 1


@pytest.mark.usefixtures("fireos6")
def test_a_boot_root_error_stops_the_run(*, adb: FakeAdb) -> None:
    adb.answers["boot-root.zip"] = ["Installing\n(!) Error: no space"]
    with pytest.raises(FatalError, match=r"boot-root\.zip failed: \(!\) Error"):
        fireos.stage_install_fireos6()


@pytest.mark.parametrize(
    ("goal", "label"),
    [
        (State.AMONET_V1_1_0_BBOE_BOOTED, "TWRP 3.7.0_9-bboe2"),
        (State.AMONET_V1_1_0_BOOTED, "TWRP 3.2.3"),
    ],
)
def test_a_rooted_dot_swaps_its_twrp_for_the_target_s(
    *,
    adb: FakeAdb,
    goal: State,
    label: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    bboe = tmp_path / "bboe.img"
    bboe.write_bytes(b"B" * 1024)
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "twrp.img").write_bytes(b"3" * 1024)
    monkeypatch.setattr(
        name="target",
        target=fireos.ARGUMENTS,
        value=next(
            target for target in TARGETS[BISCUIT].values() if target.goal == goal
        ),
    )
    monkeypatch.setattr(name="fetch", target=fireos, value=lambda **_: bboe)
    monkeypatch.setattr(name="unpack", target=fireos, value=lambda **_: tmp_path)
    held = (
        bboe
        if goal == State.AMONET_V1_1_0_BBOE_BOOTED
        else tmp_path / "bin" / "twrp.img"
    )
    monkeypatch.setattr(
        name="read_recovery", target=fireos, value=lambda **_: held.read_bytes()
    )
    fireos.stage_swap_twrp()
    assert adb.asked[0][:3] == ["adb", "push", str(held)]
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
    "transfer", ["4\n4\n0\n0\nerase 2,0,4\nnew 2,0,2\n", "3\n4\n0\n0\nnew 2,0,2\n"]
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
    assert "softwareupdates.amazon.com" in scripts["system.sh"]
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


def test_fire_os_6_goes_into_both_slots_then_boot_root(
    *, adb: FakeAdb, fireos6: list[str], pushed: list[tuple[pathlib.Path, str]]
) -> None:
    fireos.stage_install_fireos6()
    assert [remote for _, remote in pushed] == [
        "/sdcard/update.zip",
        "/sdcard/update.zip",
        "/sdcard/boot-root.zip",
    ]
    assert adb.commands(holding="twrp wipe") == ["twrp wipe cache", "twrp wipe data"]
    assert fireos6 == ["twrp"]
    assert adb.asked[-1] == ["adb", "reboot"]


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_refuses_amonet_v1_1_0_s_table(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="partition_table", target=fireos, value=lambda: " 1 boot_a_x\n"
    )
    with pytest.raises(FatalError, match=r"runs on amonet v1\.1\.0's partition table"):
        fireos.stage_install_fireos6()
    assert adb.commands(holding="twrp wipe") == []


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_says_to_power_cycle_when_the_reboot_never_goes(
    *, adb: FakeAdb
) -> None:
    adb.answers["reboot"] = [(1, "no devices")]
    with pytest.raises(FatalError, match=r"boot-root\.zip is installed"):
        fireos.stage_install_fireos6()
    assert len(adb.commands(holding="reboot")) == fireos.PUSH_TRIES


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_boot_root_ends_badly(*, adb: FakeAdb) -> None:
    adb.answers["Installing zip file"] = [ended(rc=1)]
    with pytest.raises(FatalError, match=r"boot-root\.zip failed: I:Updater .* RC=1"):
        fireos.stage_install_fireos6()
    assert ["adb", "reboot"] not in adb.asked


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


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_stops_when_the_slot_never_reads(
    *, adb: FakeAdb, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = itertools.count(step=400)
    monkeypatch.setattr(name="monotonic", target=fireos.time, value=lambda: next(clock))
    adb.answers["bcbtool get_active"] = ["1\na\nslot-ok"]
    with pytest.raises(FatalError, match="did not report its active slot"):
        fireos.stage_install_fireos6()


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_that_leaves_the_slot_alone_stops_the_run(*, adb: FakeAdb) -> None:
    adb.answers["bcbtool get_active"] = ["0\na\nslot-ok"]
    with pytest.raises(FatalError, match="left the active slot 'a', where it was 'a'"):
        fireos.stage_install_fireos6()


@pytest.mark.usefixtures("fireos6")
def test_fire_os_6_tries_the_reboot_again(*, adb: FakeAdb) -> None:
    adb.answers["reboot"] = [(1, "no devices"), (0, "")]
    fireos.stage_install_fireos6()
    assert adb.commands(holding="wait-for-recovery") == ["wait-for-recovery"]
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
def test_fire_os_6_waits_out_a_drop_and_a_running_install(*, adb: FakeAdb) -> None:
    adb.answers["bcbtool get_active"] = [
        "0\na\nslot-ok",
        "adb: device 'G090' not found",
        "1\na\nslot-ok",
        "0\nb\nslot-ok",
        "0\nb\nslot-ok",
        "0\na\nslot-ok",
    ]
    fireos.stage_install_fireos6()
    assert len(adb.commands(holding="bcbtool get_active")) == 6


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
