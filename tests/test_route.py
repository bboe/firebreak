from __future__ import annotations

import dataclasses
import functools
import types

import pytest

from firebreak import identify, route, stock, twrp, unlock
from firebreak.devices import BISCUIT, DONUT, RADAR, TARGETS, biscuit, radar
from firebreak.devices.biscuit import BUILDS
from firebreak.plugin import Author, ClearBoot0Header


class RanOutError(Exception):
    pass


class Run:
    def __init__(self, *, monkeypatch: pytest.MonkeyPatch) -> None:
        self.clock = [0.0]
        self.fetched: list[str] = []
        self.monkeypatch = monkeypatch
        self.checked = 0
        self.prefetched: list[list[object]] = []
        self.said: dict[str, str] = {
            "getenforce": "Permissive",
            "getprop ro.adb.secure": "1",
            "getprop ro.build.version.name": "Fire OS 5.5.5.4",
        }
        self.started = 0
        self.states: list[route.State] = []
        self.stepped: list[dict[str, object]] = []
        self.totals: list[int] = []
        self.tick = 1.0
        for module in (route, twrp, unlock):
            monkeypatch.setattr(
                name="run",
                target=module,
                value=lambda **_: types.SimpleNamespace(
                    returncode=0, stdout="  -S SIZE[K|M|G]"
                ),
            )
        monkeypatch.setattr(name="in_fastboot", target=unlock, value=lambda: False)
        monkeypatch.setattr(
            name="getvar",
            target=unlock,
            value=lambda **o: {"product": "BISCUIT", "unlock_status": "true"}.get(
                o["name"], ""
            ),
        )
        monkeypatch.setattr(name="state", target=route, value=self.state)
        monkeypatch.setattr(name="sleep", target=route.time, value=lambda _: None)
        monkeypatch.setattr(name="monotonic", target=route.time, value=self.monotonic)
        monkeypatch.setattr(name="prefetch", target=route, value=self.prefetch)
        monkeypatch.setattr(name="check_target", target=route, value=self.check)
        monkeypatch.setattr(name="DOWNLOADS", target=route, value=[])
        monkeypatch.setattr(
            name="fetch",
            target=route,
            value=lambda **o: self.fetched.append(o["download"].name),
        )
        monkeypatch.setattr(name="cache_note", target=route, value=lambda: None)
        monkeypatch.setattr(name="hide_updater", target=route, value=lambda: None)
        monkeypatch.setattr(
            name="adb_shell", target=route, value=lambda **o: self.said[o["command"]]
        )
        monkeypatch.setattr(
            name="DOWNLOADER",
            target=route,
            value=types.SimpleNamespace(ident=None, start=self.start),
        )
        monkeypatch.setattr(name="bootrom_step", target=route, value=self.bootrom_step)
        monkeypatch.setattr(name="unpack", target=route, value=lambda **_: None)
        monkeypatch.setattr(name="amonet_payload", target=route, value=lambda: None)
        monkeypatch.setattr(
            name="stage_fireos5_recovery",
            target=route,
            value=lambda: self.fetched.append("v1.1.0 recovery"),
        )
        self.bootrom_answer = True

    def bootrom_step(self, **options: object) -> bool:
        self.totals.append(route.PROGRESS.steps)
        self.stepped.append(options)
        return self.bootrom_answer

    def check(self, **_: object) -> None:
        self.checked += 1

    def monotonic(self) -> float:
        self.clock[0] += self.tick
        return self.clock[0]

    def prefetch(self, *, needs: object) -> None:
        self.prefetched.append(list(needs))

    def start(self) -> None:
        self.started += 1

    def state(self) -> route.State:
        if not self.states:
            raise RanOutError
        return self.states.pop(0)

    def target(self, *, build: str = "", name: str) -> None:
        self.monkeypatch.setattr(
            name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
        )
        self.monkeypatch.setattr(name="build", target=route.ARGUMENTS, value=build)


@pytest.fixture
def run(*, monkeypatch: pytest.MonkeyPatch) -> Run:
    found = Run(monkeypatch=monkeypatch)
    found.target(name="fireos5")
    return found


def described(*, value: object) -> object:
    if isinstance(value, functools.partial):
        return value.func, {
            name: described(value=held) for name, held in value.keywords.items()
        }
    return value


def said(*, capsys: pytest.CaptureFixture[str]) -> str:
    return " ".join(capsys.readouterr().out.split())


def test_a_background_failure_is_left_for_the_run_to_meet(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_: object) -> None:
        raise route.FatalError(message="no download link")

    monkeypatch.setattr(name="system_image", target=route, value=fail)
    monkeypatch.setattr(name="prefetch", target=route, value=fail)
    monkeypatch.setattr(
        name="target",
        target=route.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos5"],
    )
    route.prebuild()
    route.predownload()
    assert not route.PROGRESS.open


@pytest.mark.parametrize(
    ("build", "extra", "steps"),
    [("5.5.0.3", 1, stock.STOCK_STEPS + 2), ("5.5.3.1", 0, stock.STOCK_STEPS)],
)
def test_a_bootrom_build_restores_with_the_bootrom_s_downloads_and_steps(
    *, build: str, extra: int, monkeypatch: pytest.MonkeyPatch, steps: int
) -> None:
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value=build)
    stage = route.restore_stages()[route.State.UNLOCKED_TWRP]
    assert stage.needs[1:] == (biscuit.V2_0_1_SOURCE,)[:extra]
    assert stage.steps == steps


def test_a_bootrom_no_run_here_erased_gets_no_warning(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.BOOTROM, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert "erased boot0" not in said(capsys=capsys)


@pytest.mark.parametrize("fastboot", [True, False])
def test_a_bootrom_restore_counts_the_same_whichever_way_it_ends(
    *, fastboot: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value="5.5.0.3")
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT]["stock"]
    )
    monkeypatch.setattr(name="fastboot", target=route.SESSION, value=fastboot)
    table = route.restore_stages()
    assert {table[state].steps for state in route.TWRPS} == {stock.STOCK_STEPS + 2}


def test_a_bootrom_step_that_finds_a_preloader_is_not_counted(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.bootrom_answer = False
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.NONE, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert len(run.stepped) == 1
    assert "v1.1.0 recovery" not in run.fetched


def test_a_bootrom_that_answers_is_resumed_with_no_marker(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.BOOTROM, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert run.stepped[0]["unlock"] is biscuit.UNLOCK_FROM_BOOTROM
    assert route.SESSION.boot0_erased is False


def test_a_bootrom_that_answers_keeps_the_markers_a_run_left(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="held", target=route.SESSION, value=True)
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.BOOTROM]
    with pytest.raises(RanOutError):
        route.root()
    assert route.SESSION.boot0_erased is True


def test_a_bootrom_this_run_erased_boot0_for_says_what_a_stall_needs(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.BOOTROM, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert (
        "This run erased boot0, so the Echo Dot (2nd Generation) cannot start"
        " until amonet-biscuit-v1.1.0 is written through its bootrom."
    ) in said(capsys=capsys)


def test_a_browser_download_comes_first(*, monkeypatch: pytest.MonkeyPatch) -> None:
    fetched: list[str] = []
    monkeypatch.setattr(
        name="unpack",
        target=route,
        value=lambda **o: fetched.append(o["download"].name),
    )
    monkeypatch.setattr(
        name="fetch", target=route, value=lambda **o: fetched.append(o["download"].name)
    )
    route.prefetch(needs=[biscuit.BBOE_RECOVERY, biscuit.V2_0_1_SOURCE])
    assert fetched == [
        biscuit.V2_0_1_SOURCE.name,
        biscuit.BBOE_RECOVERY.name,
    ]


def test_a_donut_in_stock_fastboot_is_asked_for_its_bootrom_again(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
) -> None:
    asked: list[int] = []
    monkeypatch.setattr(name="ELEVATES", target=route, value=True)
    monkeypatch.setattr(
        name="authorized", target=route, value=lambda **_: asked.append(1)
    )
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[DONUT]["fireos6"]
    )
    run.tick = route.WAIT
    run.states = [
        route.State.STOCK_FASTBOOT,
        route.State.STOCK_FASTBOOT,
        route.State.STOCK_FASTBOOT,
        route.State.NONE,
        route.State.STOCK_FASTBOOT,
    ]
    with pytest.raises(RanOutError):
        route.root()
    out = said(capsys=capsys)
    assert out.count("is in its stock fastboot") == 2
    assert out.count(" ".join(DONUT.short_gesture.split())) == 2
    assert asked == [1]
    assert run.checked == 2


def test_a_donut_is_asked_for_its_bootrom_and_for_the_password_first(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[int] = []
    monkeypatch.setattr(name="ELEVATES", target=route, value=True)
    monkeypatch.setattr(
        name="authorized", target=route, value=lambda **_: asked.append(1)
    )
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[DONUT]["fireos6"]
    )
    for text in (
        route.unlock_ask(device=DONUT),
        route.usb_ask(device=DONUT),
    ):
        assert "bootrom" in text
        assert "fastboot mode" not in text
        assert DONUT.short_gesture in text
    assert asked == []
    route.password_first(device=DONUT)
    route.password_first(device=BISCUIT)
    assert asked == [1]
    assert route.waiting_line(device=DONUT) == ""
    assert "green ring" in route.waiting_line(device=BISCUIT)


def test_a_dot_at_its_goal_has_its_updater_hidden(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.states = [route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert (
        "The Echo Dot (2nd Generation) is rooted: Fire OS 5.5.5.4, SELinux Permissive"
        in said(capsys=capsys)
    )
    assert run.started == 0


def test_a_dot_at_v2_0_0_s_goal_says_it_has_root_adb(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.target(name="fireos6")
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    run.states = [route.State.UNLOCKED_BOOTED]
    route.root()
    assert (
        "rooted: Fire OS 6.5.7.4, with root adb, locked to this computer's adb key"
        in said(capsys=capsys)
    )


def test_a_dot_rooted_before_the_lock_says_only_that_it_has_root_adb(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.target(name="fireos6")
    run.said["getprop ro.adb.secure"] = "0"
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    run.states = [route.State.UNLOCKED_BOOTED]
    route.root()
    out = said(capsys=capsys)
    assert "rooted: Fire OS 6.5.7.4, with root adb." in out
    assert "locked" not in out
    assert BISCUIT.thread not in out


def test_a_dot_that_reaches_fire_os_5_names_its_unlock_s_thread(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    twrp = route.State.AMONET_FIREOS5_BBOE_TWRP
    table = {
        twrp: route.Stage(
            run=lambda: None, steps=1, then=route.State.AMONET_FIREOS5_BBOE_BOOTED
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [twrp, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert BISCUIT.thread in said(capsys=capsys)


def test_a_dot_that_stays_dark_after_boot_root_asks_for_a_power_cycle(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(name="fireos6")
    table = {
        route.State.UNLOCKED_TWRP: route.Stage(
            run=lambda: None, steps=1, then=route.State.UNLOCKED_BOOTED
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.UNLOCKED_TWRP, *[route.State.NONE] * 6]
    run.tick = route.POWER_CYCLE
    with pytest.raises(RanOutError):
        route.root()
    assert "Unplug its power cable, then plug it back in" in said(capsys=capsys)


@pytest.mark.parametrize(
    ("name", "states", "done", "message"),
    [
        (
            "fireos6",
            [route.State.STOCK_BOOTED],
            [route.State.UNLOCKED_TWRP],
            "boot-root.zip did not take",
        ),
        (
            "fireos5",
            [route.State.STOCK_BOOTED],
            [route.State.AMONET_FIREOS5_BBOE_TWRP],
            "Fire OS 5 started, and its adb refuses this computer",
        ),
        (
            "fireos5",
            [route.State.STOCK_BOOTED],
            [route.State.AMONET_TWRP_BOOT_MOVED],
            "Fire OS 5 started, and its adb refuses this computer",
        ),
        ("fireos5", [route.State.BOOTED], [], "has not finished"),
        (
            "fireos5",
            [route.State.STARTING],
            [],
            r"the Echo Dot \(2nd Generation\) has been starting for 10 minutes",
        ),
    ],
)
def test_a_dot_that_waits_too_long_stops_the_run(  # ruff: ignore[too-many-arguments]
    *,
    done: list[route.State],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    run: Run,
    states: list[route.State],
) -> None:
    run.target(name=name)
    table = {
        before: route.Stage(run=lambda: None, steps=1, then=None) for before in done
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [*done, *states * 5]
    run.tick = route.WAIT / 2
    with pytest.raises(route.FatalError, match=message):
        route.root()


def test_a_fire_os_5_restore_left_in_twrp_is_not_reported_as_written(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="5.5.5.4", name="stock")
    twrp = route.State.UNLOCKED_TWRP
    table = {
        twrp: route.Stage(
            passes=frozenset({twrp}), run=lambda: None, steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [twrp] * 6
    run.tick = route.WAIT / 2
    with pytest.raises(
        route.FatalError, match=r"stock 5\.5\.5\.4 has not started 10 minutes"
    ):
        route.root()


def test_a_fire_os_5_resume_writes_v1_1_0_through_the_bootrom(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.NONE, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    assert run.fetched == ["v1.1.0 recovery"]
    assert biscuit.V1_1_0_SOURCE in run.prefetched[0]
    assert run.stepped[0]["unlock"] is biscuit.UNLOCK_FROM_BOOTROM
    assert run.stepped[0]["little_kernel"] == biscuit.AMONET_V1_1_0_LK
    assert run.stepped[0]["tail"] == 4
    assert run.totals == [0]


def test_a_fire_os_5_route_fetches_what_it_needs_and_builds_the_system(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    fetched: list[str] = []
    built: list[object] = []
    shown: list[str] = []
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT]["fireos5"]
    )
    monkeypatch.setattr(
        name="unpack",
        target=route,
        value=lambda **o: fetched.append(o["download"].name),
    )
    monkeypatch.setattr(
        name="fetch", target=route, value=lambda **o: fetched.append(o["download"].name)
    )
    monkeypatch.setattr(
        name="system_image", target=route, value=lambda **o: built.append(o["package"])
    )
    monkeypatch.setattr(
        name="DOWNLOADER",
        target=route,
        value=types.SimpleNamespace(is_alive=lambda: True),
    )
    prebuilder = route.threading.Thread(daemon=True, target=route.prebuild)
    monkeypatch.setattr(name="PREBUILDER", target=route, value=prebuilder)
    monkeypatch.setattr(
        name="show", target=route, value=lambda **o: shown.append(o["text"])
    )
    table = route.stages()
    route.prefetch(needs=route.needed(start=route.State.STOCK_FASTBOOT, table=table))
    route.prefetch(needs=route.needed(start=route.State.UNLOCKED_TWRP, table=table))
    prebuilder.join(timeout=5)
    assert (
        fetched
        == [
            biscuit.V2_0_1_SOURCE.name,
            biscuit.V1_1_0_SOURCE.name,
            route.TWRP.name,
            BUILDS["5.5.5.4"].name,
            "Magisk-v17.3.zip",
        ]
        * 2
    )
    assert built == [BUILDS["5.5.5.4"]]
    assert shown == ["Finishing the downloads."] * 2


@pytest.mark.parametrize(
    ("name", "build", "downloaded"),
    [
        ("fireos6", "", "8349"),
        ("stock", "4315", "4315"),
    ],
)
def test_a_fire_os_6_prefetch_downloads_its_build(
    *, build: str, downloaded: str, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    got: list[str] = []
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
    )
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value=build)
    monkeypatch.setattr(name="unpack", target=route, value=lambda **_: None)
    monkeypatch.setattr(name="fetch", target=route, value=lambda **_: None)
    monkeypatch.setattr(
        name="download", target=route.updates, value=lambda **o: got.append(o["build"])
    )
    route.prefetch(
        needs=route.needed(start=route.State.UNLOCKED_TWRP, table=route.stages())
    )
    assert got == [downloaded]


@pytest.mark.parametrize(
    ("name", "run"),
    [("stock", "stage_restore"), ("fireos6", "stage_install_kamakiri")],
)
def test_a_kamakiri_route_runs_the_stage_its_target_asks_for_from_twrp(
    *, monkeypatch: pytest.MonkeyPatch, name: str, run: str
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[DONUT][name]
    )
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value="8349")
    table = route.stages()
    assert table[route.State.UNLOCKED_TWRP].run.__name__ == run
    assert table[route.State.BOOTROM].run.__name__ == "stage_kamakiri"


def test_a_preloader_is_waited_through_and_keeps_the_markers(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="held", target=route.SESSION, value=True)
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.PRELOADER]
    with pytest.raises(RanOutError):
        route.root()
    assert route.SESSION.boot0_erased is True


def test_a_preloader_that_never_chains_names_the_test_point(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.tick = route.WAIT
    run.states = [route.State.PRELOADER, route.State.PRELOADER]
    with pytest.raises(route.FatalError, match="test point is the only way in"):
        route.root()


def test_a_radar_takes_amonet_radars_chain_not_biscuits(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    route.SESSION.short = True
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[RADAR]["fireos6"]
    )
    unlocking = route.bootrom_chain().unlock
    assert unlocking is radar.CONFIG.bootrom_unlock
    assert unlocking.device.product == "RADAR"
    assert unlocking.plan[0] == ClearBoot0Header()
    assert unlocking.plan[1:] == radar.AMONET_V1_0_1.plan
    assert "radar-kaeru" in str(unlocking.plan)
    assert run.stepped == []


def test_a_reset_route_takes_five_steps(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="factory_reset", target=route.ARGUMENTS, value=True)
    monkeypatch.setattr(
        name="target",
        target=route.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos6"],
    )
    assert route.stages()[route.State.UNLOCKED_TWRP].steps == 5


def test_a_restore_left_for_fastboot_that_never_arrives_still_fails(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8149", name="stock")
    twrp = route.State.UNLOCKED_TWRP
    table = {
        twrp: route.Stage(
            passes=frozenset({twrp}), run=lambda: None, steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="ends_in_fastboot", target=route, value=lambda: True)
    run.states = [twrp, *[route.State.NONE] * 5]
    run.tick = route.WAIT / 2
    with pytest.raises(route.FatalError, match="stock 8149 has not started 10 minutes"):
        route.root()


def test_a_restore_whose_echo_stays_off_usb_ends_once_it_is_written(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8344", name="stock")
    twrp = route.State.UNLOCKED_TWRP
    table = {
        twrp: route.Stage(
            passes=frozenset({twrp}), run=lambda: None, steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [twrp, *[route.State.NONE] * 5]
    run.tick = route.STOCK_QUIET / 2
    route.root()
    said = " ".join(capsys.readouterr().out.split())
    assert "Stock 8344 is written and verified" in said
    assert "shown nothing on USB for 5 minutes" in said


def test_a_rooted_donut_counts_its_bootloader_request_as_a_step(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[DONUT]["fireos6"]
    )
    assert route.stages()[route.State.UNLOCKED_BOOTED].steps == 2


def test_a_rooted_dot_given_factory_reset_reinstalls_from_twrp(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(name="fireos6")
    monkeypatch.setattr(name="factory_reset", target=route.ARGUMENTS, value=True)
    ran: list[str] = []
    table = {
        route.State.UNLOCKED_BOOTED: route.Stage(
            run=lambda: ran.append("reboot"),
            steps=1,
            then=route.State.UNLOCKED_TWRP,
        ),
        route.State.UNLOCKED_TWRP: route.Stage(
            run=lambda: ran.append("install"),
            steps=5,
            then=route.State.UNLOCKED_BOOTED,
        ),
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    run.states = [
        route.State.UNLOCKED_BOOTED,
        route.State.UNLOCKED_TWRP,
        route.State.UNLOCKED_BOOTED,
    ]
    route.root()
    out = said(capsys=capsys)
    assert ran == ["reboot", "install"]
    assert "runs rooted Fire OS 6 on an unlocked bootloader. Rebooting it" in out
    assert "rooted: Fire OS 6.5.7.4, with root adb" in out
    assert (
        "amonet, the unlock this run used, is the work of Roger Ortiz (Rortiz2):"
        " https://github.com/R0rt1z2 If this tool helped bring new life to an old"
        " device, consider supporting Roger's continued unlocking work:"
        " - https://www.paypal.com/paypalme/R0rt1z2/ - https://ko-fi.com/r0rt1z2"
        " - https://github.com/sponsors/R0rt1z2 Unlock thread for the Echo Dot (2nd"
        " Generation):"
        f" {BISCUIT.thread}"
    ) in out


def test_a_rooted_dot_on_an_older_build_installs_the_default_from_twrp(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(name="fireos6")
    ran: list[str] = []
    table = {
        route.State.UNLOCKED_BOOTED: route.Stage(
            run=lambda: ran.append("reboot"),
            steps=1,
            then=route.State.UNLOCKED_TWRP,
        ),
        route.State.UNLOCKED_TWRP: route.Stage(
            needs=(route.BOOT_ROOT,),
            run=lambda: ran.append("install"),
            steps=None,
            then=route.State.UNLOCKED_BOOTED,
        ),
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.said["getprop ro.build.version.name"] = "Fire OS 6574.1 (NS65741/8149)"
    run.states = [
        route.State.UNLOCKED_BOOTED,
        route.State.UNLOCKED_BOOTED,
        route.State.UNLOCKED_TWRP,
        route.State.UNLOCKED_BOOTED,
    ]
    route.root()
    out = said(capsys=capsys)
    assert ran == ["reboot", "install"]
    assert run.prefetched[0] == [route.BOOT_ROOT]
    assert (
        "runs rooted Fire OS 6 8149. Rebooting it into TWRP to install 8349 over it"
        in out
    )
    assert "on an unlocked bootloader" not in out
    assert "rooted: Fire OS 6574.1 (NS65741/8149), with root adb" in out


@pytest.mark.parametrize(
    "version", ["Fire OS 6.5.7.5 (NS6575/8349)", "Fire OS 6.5.7.4"]
)
def test_a_rooted_dot_on_the_default_or_an_unknown_build_stays(
    *, capsys: pytest.CaptureFixture[str], run: Run, version: str
) -> None:
    run.target(name="fireos6")
    run.said["getprop ro.build.version.name"] = version
    run.states = [route.State.UNLOCKED_BOOTED]
    route.root()
    out = said(capsys=capsys)
    assert f"rooted: {version}, with root adb" in out
    assert "install 8349 over it" not in out


def test_a_route_leaves_a_payload_archive_out_of_its_downloads(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT]["fireos6"]
    )
    needs = route.needed(start=route.State.STOCK_FASTBOOT, table=route.stages())
    assert biscuit.V2_0_1_SOURCE in needs
    assert biscuit.V2_0_0_SOURCE not in needs


@pytest.mark.parametrize(
    ("name", "start", "needs"),
    [
        (
            "fireos5",
            route.State.UNLOCKED_FASTBOOT,
            [
                biscuit.V1_1_0_SOURCE,
                biscuit.V2_0_1_SOURCE,
                route.TWRP,
                BUILDS["5.5.5.4"],
                route.MAGISK,
                route.start_prebuild,
            ],
        ),
        ("fireos5", route.State.ROOTED, [route.TWRP]),
        ("fireos5", route.State.EMOS, []),
        (
            "fireos6",
            route.State.AMONET_FIREOS5_TWRP,
            [
                biscuit.V2_0_1_SOURCE,
                biscuit.V1_1_0_SOURCE,
                route.ota_build,
                route.BOOT_ROOT,
            ],
        ),
        (
            "fireos6",
            route.State.STOCK_FASTBOOT,
            [biscuit.V2_0_1_SOURCE, route.ota_build, route.BOOT_ROOT],
        ),
        (
            "fireos6",
            route.State.STOCK_FIREOS5_FASTBOOT,
            [biscuit.V2_0_1_SOURCE, route.ota_build, route.BOOT_ROOT],
        ),
        ("stock", route.State.AMONET_FIREOS5_TWRP, [route.ota_build]),
    ],
)
def test_a_route_needs_only_its_own_stages_downloads(
    *,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    needs: list[object],
    start: route.State,
) -> None:
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
    )
    assert route.needed(start=start, table=route.stages()) == needs


def test_a_run_after_boot0_was_erased_goes_through_the_bootrom(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(name="fireos6")
    route.SESSION.boot0_erased = True
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    monkeypatch.setattr(
        name="stage_amonet_recovery",
        target=route,
        value=lambda **_: run.fetched.append("v2.0.1 recovery"),
    )
    run.states = [route.State.NONE, route.State.UNLOCKED_BOOTED]
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    route.root()
    assert run.fetched == ["v2.0.1 recovery"]
    assert {biscuit.V2_0_1_SOURCE, route.BOOT_ROOT} <= set(run.prefetched[0])
    assert biscuit.V1_1_0_SOURCE not in run.prefetched[0]
    assert run.stepped[0]["erase"] is None
    assert run.stepped[0]["unlock"] is biscuit.UNLOCK_V2_FROM_BOOTROM
    assert run.stepped[0]["tail"] is None
    assert run.totals == [0]
    assert "amonet-biscuit-v2.0.1 is written" in said(capsys=capsys)


def test_a_run_fetches_its_route_s_downloads_before_the_first_stage(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    ran: list[str] = []
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            needs=(biscuit.V2_0_1_SOURCE,),
            run=lambda: ran.append("fastbrick"),
            steps=2,
            then=route.State.AMONET_FIREOS5_BBOE_BOOTED,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    route.ARGUMENTS.verbose = True
    run.states = [route.State.STOCK_FASTBOOT, route.State.AMONET_FIREOS5_BBOE_BOOTED]
    route.root()
    out = said(capsys=capsys)
    assert ran == ["fastbrick"]
    assert run.checked == 1
    assert run.started == 0
    assert run.prefetched == [[biscuit.V2_0_1_SOURCE]]
    assert "Keep the Echo Dot (2nd Generation) plugged in" in out
    assert "state: stock-fastboot" in out


def test_a_run_leaves_one_blank_line_before_the_fastboot_wait(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.STOCK_BOOTED, route.State.NONE]
    with pytest.raises(RanOutError):
        route.root()
    out = capsys.readouterr().out
    before, waiting = out.split(sep="Waiting for the Echo Dot (2nd Generation) in")
    assert waiting
    assert before.endswith("which starts its TWRP.\n\n")


@pytest.mark.parametrize(
    ("missing", "warned"),
    [([True], 1), ([True, False], 0), ([False], 0)],
)
def test_a_run_names_a_fastboot_driver_that_stays_missing(
    *,
    capsys: pytest.CaptureFixture[str],
    missing: list[bool],
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
    warned: int,
) -> None:
    asked: list[bool] = []

    def check() -> bool:
        asked.append(missing[len(asked) % len(missing)])
        return asked[-1]

    monkeypatch.setattr(name="stages", target=route, value=dict)
    monkeypatch.setattr(name="fastboot_driver_missing", target=identify, value=check)
    run.states = [route.State.NONE] * 30
    with pytest.raises(RanOutError):
        route.root()
    assert said(capsys=capsys).count("so its driver is missing") == warned
    assert 1 < len(asked) < 10


def test_a_run_refuses_another_device_before_it_downloads(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    def refuse(**_: object) -> None:
        raise route.FatalError(message="this is an Echo (2nd Generation)")

    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            needs=(biscuit.V2_0_1_SOURCE,), run=lambda: None, steps=2, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="check_target", target=route, value=refuse)
    run.states = [route.State.STOCK_FASTBOOT]
    with pytest.raises(route.FatalError, match="Echo"):
        route.root()
    assert run.prefetched == []


@pytest.mark.parametrize(
    argnames=("then", "said_so"),
    argvalues=[(route.State.UNLOCKED_TWRP, True), (route.State.STOCK_BOOTED, False)],
    ids=["twrp", "stock"],
)
def test_a_run_says_a_port_cannot_power_twrp_only_while_twrp_is_what_is_next(
    *,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
    said_so: bool,
    then: route.State,
) -> None:
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(run=lambda: None, steps=1, then=then)
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(
        name="fastboot_driver_missing", target=identify, value=lambda: False
    )
    run.states = [
        route.State.STOCK_FASTBOOT,
        *[route.State.NONE, route.State.STARTING] * 10,
    ]
    with pytest.raises(RanOutError):
        route.root()
    out = " ".join(said(capsys=capsys).split())
    assert out.count("cannot power TWRP") == (1 if said_so else 0)
    assert ("hold the + button while it powers up" in out) is said_so
    assert ("A USB 3 port on the computer itself" in out) is said_so


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ([route.State.BOOTED], "The Echo Dot (2nd Generation) is starting Fire OS"),
        ([route.State.STOCK_BOOTED], "appears to be unmodified"),
        ([route.State.EMOS], "runs EchoMuse's emOS"),
        ([route.State.NO_SYSTEM], "/system is damaged"),
        ([route.State.NONE], "Waiting for the Echo Dot (2nd Generation) on USB"),
        (
            [route.State.STOCK_BOOTED, route.State.NONE],
            (
                "Waiting for the Echo Dot (2nd Generation) in fastboot mode: a"
                " green ring on a stock Echo, every color turning on amonet's."
            ),
        ),
    ],
)
def test_a_run_says_what_the_dot_needs(
    *,
    capsys: pytest.CaptureFixture[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
    states: list[route.State],
) -> None:
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = states
    with pytest.raises(RanOutError):
        route.root()
    assert message in said(capsys=capsys)


def test_a_run_that_erased_boot0_itself_does_not_blame_the_last_run(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    def erases() -> bool:
        route.SESSION.boot0_erased = True
        return True

    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            run=erases,
            steps=2,
            then=route.State.AMONET_FIREOS5_BBOE_TWRP,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="bootrom_step", target=route, value=lambda **_: False)
    run.states = [route.State.STOCK_FASTBOOT, route.State.NONE]
    with pytest.raises(RanOutError):
        route.root()
    out = said(capsys=capsys)
    assert "This run erased boot0" in out
    assert "The last run stopped" not in out


def test_a_run_waiting_for_the_gesture_downloads_the_fastboot_route(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            needs=(biscuit.V2_0_1_SOURCE,),
            run=lambda: None,
            steps=2,
            then=route.State.UNLOCKED_TWRP,
        ),
        route.State.UNLOCKED_TWRP: route.Stage(
            needs=(biscuit.V2_0_1_SOURCE, BUILDS["5.5.5.4"]),
            run=lambda: None,
            steps=2,
            then=None,
        ),
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.NONE, route.State.STOCK_BOOTED, route.State.NONE]
    with pytest.raises(RanOutError):
        route.root()
    assert run.checked == 1
    assert run.started == 1
    assert [BUILDS["5.5.5.4"]] == route.DOWNLOADS
    assert run.prefetched == []


def test_a_seen_state_clears_the_erased_marker(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.SESSION.boot0_erased = True
    states = iter([route.State.BOOTED])

    def state() -> route.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    monkeypatch.setattr(
        name="run",
        target=route,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=route, value=state)
    monkeypatch.setattr(name="stages", target=route, value=dict)
    monkeypatch.setattr(name="sleep", target=route.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT]["fireos5"]
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert route.SESSION.boot0_erased is False


def test_a_short_run_takes_the_chain_its_target_wants(*, run: Run) -> None:
    route.SESSION.short = True
    assert route.bootrom_chain().unlock is biscuit.UNLOCK_FROM_BOOTROM
    run.target(name="fireos6")
    assert route.bootrom_chain().unlock is biscuit.UNLOCK_V2_FROM_BOOTROM
    run.target(build="8149", name="stock")
    assert route.bootrom_chain().unlock is biscuit.UNLOCK_V2_FROM_BOOTROM


@pytest.mark.parametrize(
    ("returned", "expected"),
    [(False, ["first", "second"]), (None, ["first"])],
)
def test_a_stage_counts_its_passes_unless_it_returns_false(
    *, expected: list[str], monkeypatch: pytest.MonkeyPatch, returned: bool | None
) -> None:
    ran: list[str] = []
    states = iter([
        route.State.UNLOCKED_FASTBOOT,
        route.State.AMONET_TWRP_BOOT_MOVED,
    ])

    def state() -> route.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    table = {
        route.State.UNLOCKED_FASTBOOT: route.Stage(
            passes=frozenset({route.State.AMONET_TWRP_BOOT_MOVED}),
            run=lambda: ran.append("first") or returned,
            steps=1,
            then=None,
        ),
        route.State.AMONET_TWRP_BOOT_MOVED: route.Stage(
            run=lambda: ran.append("second"), steps=1, then=None
        ),
    }
    monkeypatch.setattr(
        name="run",
        target=route,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=route, value=state)
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="prefetch", target=route, value=lambda **_: None)
    monkeypatch.setattr(name="check_target", target=route, value=lambda **_: None)
    monkeypatch.setattr(
        name="DOWNLOADER", target=route, value=types.SimpleNamespace(ident=1)
    )
    monkeypatch.setattr(name="sleep", target=route.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target",
        target=route.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos5"],
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert ran == expected


def test_a_stock_donut_with_nothing_to_restore_is_told_to_unlock_it() -> None:
    said = " ".join(route.nothing_to_restore(device=DONUT).split())
    assert "nothing to restore" in said
    assert f"run {route.invocation(options=['unlock'])}." in said
    assert "amonet" not in said
    assert "+ button" not in said
    assert "amonet v2" in route.nothing_to_restore(device=BISCUIT)


def test_a_stock_fire_os_5_run_ends_after_the_restore(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="5.5.5.4", name="stock")
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.UNLOCKED_TWRP, route.State.NONE]
    route.root()
    out = said(capsys=capsys)
    assert "Stock 5.5.5.4 is written" in out
    assert "until the orange ring circles" in out


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ([route.State.STOCK_BOOTED], "nothing to restore"),
        ([route.State.UNLOCKED_TWRP, route.State.STOCK_BOOTED], "runs stock 8146"),
    ],
)
def test_a_stock_run_ends_on_stock(
    *,
    capsys: pytest.CaptureFixture[str],
    message: str,
    monkeypatch: pytest.MonkeyPatch,
    run: Run,
    states: list[route.State],
) -> None:
    run.target(build="8146", name="stock")
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = states
    route.root()
    assert message in said(capsys=capsys)


def test_a_stock_run_leaves_a_locked_bootloader_alone(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8338", name="stock")
    ran: list[str] = []
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            run=lambda: ran.append("unlock"),
            steps=2,
            then=route.State.AMONET_FIREOS5_BBOE_TWRP,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.STOCK_FASTBOOT]
    route.root()
    assert ran == []
    assert "nothing to restore" in said(capsys=capsys)


def test_a_stock_run_of_a_build_with_adb_off_ends_after_the_restore(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    monkeypatch.setitem(route.ADB_OFF_BUILDS, BISCUIT, frozenset({"8146"}))
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.UNLOCKED_TWRP, route.State.NONE]
    route.root()
    out = said(capsys=capsys)
    assert "Stock 8146 is written" in out
    assert "starts with adb off" in out


def test_a_stock_run_reboots_fire_os_5_it_has_not_restored(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="5.5.5.4", name="stock")
    ran: list[str] = []
    table = {
        route.State.BOOTED: route.Stage(
            run=lambda: ran.append("reboot"), steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.BOOTED]
    with pytest.raises(RanOutError):
        route.root()
    assert ran == ["reboot"]
    assert "runs stock" not in said(capsys=capsys)


def test_a_stock_run_that_parks_in_fastboot_says_so(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="5.5.5.4", name="stock")
    monkeypatch.setattr(name="stages", target=route, value=dict)
    monkeypatch.setattr(name="fastboot", target=route.SESSION, value=True)
    run.states = [route.State.UNLOCKED_TWRP, route.State.STOCK_FASTBOOT]
    route.root()
    out = said(capsys=capsys)
    assert "waits in fastboot" in out
    assert "until the orange ring circles" not in out


def test_a_v2_0_0_dot_is_restarted_into_its_own_twrp(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    table = route.stages() | {
        route.State.UNLOCKED_BOOTED: route.Stage(run=lambda: None, steps=1, then=None)
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.UNLOCKED_FASTBOOT, route.State.UNLOCKED_BOOTED]
    with pytest.raises(RanOutError):
        route.root()
    out = said(capsys=capsys)
    assert "is in its unlocked fastboot. Starting its recovery." in out
    assert "Rebooting it into TWRP." in out
    assert "hold the + button" not in out


def test_a_v2_0_0_dot_that_refuses_the_restart_is_told_about_its_button(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    monkeypatch.setattr(
        name="run",
        target=unlock,
        value=lambda **_: types.SimpleNamespace(returncode=1, stdout=""),
    )
    monkeypatch.setattr(name="in_fastboot", target=unlock, value=lambda: True)
    run.states = [route.State.UNLOCKED_FASTBOOT]
    with pytest.raises(RanOutError):
        route.root()
    assert "hold the + button while you plug it back in" in said(capsys=capsys)


def test_an_unlock_credit_wraps_its_prose_and_ends_with_a_blank_line(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    route.credit_note(target=TARGETS[BISCUIT]["fireos6"])
    out = capsys.readouterr().out
    assert out.endswith(f"\n{BISCUIT.thread}\n\n")
    lines = out.splitlines()
    assert "  - https://www.paypal.com/paypalme/R0rt1z2/" in lines
    assert all(
        len(line) <= 79 or line.lstrip(" -").startswith("https://") for line in lines
    )


@pytest.mark.parametrize(
    ("author", "thread", "expected"),
    [
        (None, "", ""),
        (
            None,
            "https://xda",
            "Unlock thread for the Echo Dot (2nd Generation):\nhttps://xda\n\n",
        ),
        (
            Author(home="https://home", name="A", short_name="A"),
            "",
            "amonet, the unlock this run used, is the work of A: https://home\n\n",
        ),
    ],
)
def test_an_unlock_credits_only_what_it_has(
    *,
    author: Author | None,
    capsys: pytest.CaptureFixture[str],
    expected: str,
    thread: str,
) -> None:
    target = TARGETS[BISCUIT]["fireos6"]
    assert target.unlock is not None
    route.credit_note(
        target=dataclasses.replace(
            target,
            device=dataclasses.replace(BISCUIT, thread=thread),
            unlock=dataclasses.replace(target.unlock, author=author),
        )
    )
    route.credit_note(target=dataclasses.replace(target, unlock=None))
    assert capsys.readouterr().out == expected


def test_each_target_has_its_route_s_stages(*, monkeypatch: pytest.MonkeyPatch) -> None:
    state = route.State
    to_recovery = (route.reboot, {"label": "restarting into recovery"})
    to_twrp = (route.reboot, {"label": "restarting into TWRP"})
    shared = {
        state.AMONET_FIREOS5_FASTBOOT: (
            route.stage_fireos5_recovery,
            1,
            state.AMONET_FIREOS5_BBOE_TWRP,
            frozenset(),
        ),
        state.UNLOCKED_FASTBOOT: (
            route.stage_amonet_recovery,
            1,
            state.UNLOCKED_TWRP,
            frozenset(),
        ),
        state.EMOS: (route.stage_emos, 1, None, frozenset()),
        state.NO_SYSTEM: (to_recovery, 1, None, frozenset()),
    } | dict.fromkeys(
        (state.STOCK_FASTBOOT, state.STOCK_FIREOS5_FASTBOOT),
        (route.stage_fastbrick, 2, state.UNLOCKED_TWRP, frozenset()),
    )
    reboots = {
        state.UNLOCKED_BOOTED: (
            (route.restart_into_twrp, {"device": BISCUIT}),
            1,
            state.UNLOCKED_TWRP,
            frozenset(),
        ),
        state.BOOTED: (to_recovery, 1, None, frozenset()),
        state.ROOTED: (to_recovery, 1, state.AMONET_FIREOS5_TWRP, frozenset()),
        state.AMONET_FIREOS5_BBOE_BOOTED: (
            to_twrp,
            1,
            state.AMONET_FIREOS5_BBOE_TWRP,
            frozenset(),
        ),
    }
    install = (
        route.recovery.carry_out,
        {
            "after": to_twrp,
            "guard": route.amonet_chain,
            "unlock": route.biscuit.UNLOCK_TO_FIREOS6,
            "zero": ("misc",),
        },
    )
    routes = {
        "fireos6": shared
        | {
            state.AMONET_FIREOS5_BBOE_TWRP: (
                (route.from_fireos5_twrp, {"install": install}),
                4,
                state.UNLOCKED_TWRP,
                frozenset(),
            ),
            state.AMONET_FIREOS5_TWRP: (
                (route.from_fireos5_twrp, {"install": install}),
                4,
                state.UNLOCKED_TWRP,
                frozenset(),
            ),
            state.UNLOCKED_TWRP: (
                route.stage_install_fireos6,
                None,
                state.UNLOCKED_BOOTED,
                frozenset(),
            ),
            state.AMONET_TWRP_BOOT_MOVED: (
                install,
                4,
                state.UNLOCKED_TWRP,
                frozenset(),
            ),
        }
        | {
            rooted: (
                (route.leave_fireos5, {"reboot": reboots[rooted][0]}),
                *reboots[rooted][1:],
            )
            for rooted in route.FIREOS5_ROOTED
        }
        | {state.UNLOCKED_BOOTED: reboots[state.UNLOCKED_BOOTED]},
        "stock": shared
        | dict.fromkeys(
            route.TWRPS, (route.stage_restore, 16, state.STOCK_BOOTED, route.TWRPS)
        )
        | reboots,
    }
    for name in ("fireos5", "fireos5"):
        goal = TARGETS[BISCUIT][name].goal
        chain = (
            route.recovery.carry_out,
            {
                "after": (
                    route.reboot,
                    {
                        "estimate": 345,
                        "into": "",
                        "label": "waiting for rooted Fire OS 5",
                    },
                ),
                "before_preloader": (
                    route.stage_install_fireos,
                    {"reboot": False, "slot": "_a"},
                ),
                "guard": route.amonet_chain,
                "unlock": TARGETS[BISCUIT][name].unlock,
            },
        )
        routes[name] = (
            shared
            | {
                state.AMONET_FIREOS5_BBOE_TWRP: (
                    route.stage_install_fireos,
                    4,
                    state.AMONET_FIREOS5_BBOE_BOOTED,
                    frozenset(),
                ),
                state.AMONET_FIREOS5_TWRP: (
                    route.stage_replace_twrp,
                    1,
                    state.AMONET_FIREOS5_BBOE_TWRP,
                    frozenset(),
                ),
                state.UNLOCKED_BOOTED: reboots[state.UNLOCKED_BOOTED],
                state.UNLOCKED_FASTBOOT: (
                    route.stage_downgrade,
                    2,
                    state.AMONET_FIREOS5_BBOE_TWRP,
                    frozenset({
                        state.AMONET_FIREOS5_FASTBOOT,
                        state.UNLOCKED_FASTBOOT,
                        state.UNLOCKED_TWRP,
                        state.AMONET_TWRP_BOOT_MOVED,
                    }),
                ),
                state.UNLOCKED_TWRP: (
                    chain,
                    2,
                    state.AMONET_TWRP_BOOT_MOVED,
                    frozenset(),
                ),
                state.AMONET_TWRP_BOOT_MOVED: (chain, 7, goal, frozenset()),
            }
            | {
                rooted: (route.stage_swap_twrp, 1, goal, frozenset())
                for rooted in route.FIREOS5_ROOTED - {goal}
            }
        )
    assert set(routes) == set(TARGETS[BISCUIT])
    for name, table in routes.items():
        monkeypatch.setattr(
            name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
        )
        assert {
            current: (
                described(value=stage.run),
                stage.steps,
                stage.then,
                stage.passes,
            )
            for current, stage in route.stages().items()
        } == table, name


@pytest.mark.parametrize(
    ("name", "factory_reset", "totals"),
    [
        ("fireos5", False, {"rooted": 10, "stock": 11, "twrp": 9, "v1.1.0": 7}),
        (
            "fireos6",
            False,
            {"rooted": 0, "stock": None, "twrp": None, "v1.1.0": None},
        ),
        ("fireos6", True, {"rooted": 6, "stock": 7, "twrp": 5, "v1.1.0": 9}),
    ],
)
def test_fastboot_counts_the_steps_the_route_takes(
    *,
    factory_reset: bool,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    totals: dict[str, int | None],
) -> None:
    state = route.State
    monkeypatch.setattr(
        name="factory_reset", target=route.ARGUMENTS, value=factory_reset
    )
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
    )
    table = route.stages()
    starts = {
        state.UNLOCKED_BOOTED: totals["rooted"],
        state.UNLOCKED_TWRP: totals["twrp"],
        state.AMONET_TWRP_BOOT_MOVED: totals["v1.1.0"],
        state.STOCK_FASTBOOT: totals["stock"],
        state.STOCK_FIREOS5_FASTBOOT: totals["stock"],
    }
    assert {
        start: route.remaining(start=start, table=table) for start in starts
    } == starts


def test_stock_that_does_not_start_after_the_restore_stops_the_run(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    twrp = route.State.UNLOCKED_TWRP
    table = {
        twrp: route.Stage(
            passes=frozenset({twrp}), run=lambda: None, steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [twrp, *[route.State.STARTING] * 5]
    run.tick = route.WAIT / 2
    with pytest.raises(route.FatalError, match="stock 8146 has not started 10 minutes"):
        route.root()


def test_the_background_downloads_leave_the_browser_to_the_run(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(name="fireos6")
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.STOCK_BOOTED]
    with pytest.raises(RanOutError):
        route.root()
    assert run.started == 1
    assert list(route.DOWNLOADS) == [route.ota_build]


def test_the_session_takes_the_marker_after_the_first_probe(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.SESSION.boot0_erased = True
    states = iter([route.State.BOOTED])

    def state() -> route.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    monkeypatch.setattr(
        name="run",
        target=route,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=route, value=state)
    monkeypatch.setattr(name="stages", target=route, value=dict)
    monkeypatch.setattr(name="sleep", target=route.time, value=lambda _: None)
    monkeypatch.setattr(
        name="target",
        target=route.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos5"],
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert route.SESSION.boot0_erased is False
