from __future__ import annotations

import functools
import types

import pytest

from firebreak import route, ui
from firebreak.devices import BISCUIT
from firebreak.unlocks import amonet_biscuit_v1_1_0, amonet_biscuit_v2_0_0
from firebreak.unlocks.targets import TARGETS
from firebreak.updates import BUILDS


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
            "getprop ro.build.version.name": "Fire OS 5.5.5.4",
        }
        self.started = 0
        self.states: list[route.State] = []
        self.stepped: list[dict[str, object]] = []
        self.tick = 1.0
        monkeypatch.setattr(
            name="run",
            target=route,
            value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
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
        monkeypatch.setattr(name="pyserial_wheel", target=route, value=lambda: None)
        monkeypatch.setattr(
            name="amonet_v2_0_0_payload", target=route, value=lambda: None
        )
        monkeypatch.setattr(
            name="stage_amonet_v1_1_0_recovery",
            target=route,
            value=lambda: self.fetched.append("v1.1.0 recovery"),
        )
        self.bootrom_answer = True

    def bootrom_step(self, **options: object) -> bool:
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
    found.target(name="amonet-biscuit-v1.1.0-bboe")
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
        value=TARGETS[BISCUIT]["amonet-biscuit-v1.1.0"],
    )
    route.prebuild()
    route.predownload()
    assert not route.PROGRESS.open


@pytest.mark.parametrize(
    ("build", "extra", "steps"),
    [("5.5.0.3", 2, route.STOCK_STEPS + 3), ("5.5.3.1", 0, route.STOCK_STEPS)],
)
def test_a_bootrom_build_restores_with_the_bootrom_s_downloads_and_steps(
    *, build: str, extra: int, monkeypatch: pytest.MonkeyPatch, steps: int
) -> None:
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value=build)
    stage = route.restore_stages()[route.State.AMONET_V2_0_0_TWRP]
    assert (
        stage.needs[1:]
        == ((amonet_biscuit_v2_0_0.SOURCE, route.pyserial_wheel)[:extra])
    )
    assert stage.steps == steps


def test_a_bootrom_step_that_finds_a_preloader_is_not_counted(
    *, monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.bootrom_answer = False
    route.SESSION.short = True
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.NONE, route.State.AMONET_V1_1_0_BBOE_BOOTED]
    route.root()
    assert len(run.stepped) == 1
    assert "v1.1.0 recovery" not in run.fetched


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
    route.prefetch(needs=[amonet_biscuit_v2_0_0.SOURCE, route.BOOT_ROOT])
    assert fetched == [route.BOOT_ROOT.name, amonet_biscuit_v2_0_0.SOURCE.name]


def test_a_dot_at_its_goal_has_its_updater_hidden(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.states = [route.State.AMONET_V1_1_0_BBOE_BOOTED]
    route.root()
    assert "The Dot is rooted: Fire OS 5.5.5.4, SELinux Permissive" in said(
        capsys=capsys
    )
    assert run.started == 0


def test_a_dot_at_v2_0_0_s_goal_says_it_has_root_adb(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.target(name="amonet-biscuit-v2.0.0")
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    run.states = [route.State.AMONET_V2_0_0_BOOTED]
    route.root()
    assert "rooted: Fire OS 6.5.7.4, with root adb" in said(capsys=capsys)


@pytest.mark.parametrize(
    ("name", "states", "done", "message"),
    [
        (
            "amonet-biscuit-v2.0.0",
            [route.State.STOCK_BOOTED],
            [route.State.AMONET_V2_0_0_TWRP],
            "boot-root.zip did not take",
        ),
        ("amonet-biscuit-v1.1.0-bboe", [route.State.BOOTED], [], "has not finished"),
        (
            "amonet-biscuit-v1.1.0-bboe",
            [route.State.STARTING],
            [],
            "the Dot has been starting for 10 minutes",
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
    twrp = route.State.AMONET_V2_0_0_TWRP
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


@pytest.mark.parametrize(
    ("name", "twrp"),
    [("amonet-biscuit-v1.1.0", []), ("amonet-biscuit-v1.1.0-bboe", [route.TWRP.name])],
)
def test_a_fire_os_5_route_fetches_what_it_needs_and_builds_the_system(
    *, monkeypatch: pytest.MonkeyPatch, name: str, twrp: list[str]
) -> None:
    fetched: list[str] = []
    built: list[object] = []
    shown: list[str] = []
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
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
    route.prefetch(
        needs=route.needed(start=route.State.AMONET_V2_0_0_TWRP, table=table)
    )
    prebuilder.join(timeout=5)
    assert (
        fetched
        == [
            amonet_biscuit_v2_0_0.SOURCE.name,
            amonet_biscuit_v1_1_0.SOURCE.name,
            *twrp,
            BUILDS[BISCUIT]["5.5.5.4"].name,
            "Magisk-v17.3.zip",
        ]
        * 2
    )
    assert built == [BUILDS[BISCUIT]["5.5.5.4"]]
    assert shown == ["Finishing the downloads."] * 2


@pytest.mark.parametrize(
    ("name", "build", "downloaded"),
    [
        ("amonet-biscuit-v2.0.0", "", "8146"),
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
        needs=route.needed(start=route.State.AMONET_V2_0_0_TWRP, table=route.stages())
    )
    assert got == [downloaded]


@pytest.mark.parametrize(
    ("name", "start", "needs"),
    [
        (
            "amonet-biscuit-v1.1.0-bboe",
            route.State.AMONET_V2_0_0_FASTBOOT,
            [
                amonet_biscuit_v1_1_0.SOURCE,
                route.pyserial_wheel,
                amonet_biscuit_v2_0_0.SOURCE,
                route.TWRP,
                BUILDS[BISCUIT]["5.5.5.4"],
                route.MAGISK,
                route.start_prebuild,
            ],
        ),
        (
            "amonet-biscuit-v1.1.0",
            route.State.AMONET_V1_1_0_BOOTED,
            [],
        ),
        (
            "amonet-biscuit-v1.1.0",
            route.State.ROOTED,
            [amonet_biscuit_v1_1_0.SOURCE],
        ),
        (
            "amonet-biscuit-v1.1.0-bboe",
            route.State.ROOTED,
            [amonet_biscuit_v1_1_0.SOURCE, route.TWRP],
        ),
        ("amonet-biscuit-v1.1.0", route.State.EMOS, [route.pyserial_wheel]),
        (
            "amonet-biscuit-v2.0.0",
            route.State.AMONET_V1_1_0_TWRP,
            [
                amonet_biscuit_v2_0_0.SOURCE,
                amonet_biscuit_v1_1_0.SOURCE,
                route.ota_build,
                route.BOOT_ROOT,
            ],
        ),
        (
            "amonet-biscuit-v2.0.0",
            route.State.STOCK_FASTBOOT,
            [amonet_biscuit_v2_0_0.SOURCE, route.ota_build, route.BOOT_ROOT],
        ),
        (
            "amonet-biscuit-v2.0.0",
            route.State.STOCK_FIREOS5_FASTBOOT,
            [amonet_biscuit_v2_0_0.SOURCE, route.ota_build, route.BOOT_ROOT],
        ),
        ("stock", route.State.AMONET_V1_1_0_TWRP, [route.ota_build]),
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
    run.target(name="amonet-biscuit-v2.0.0")
    route.ERASED.touch()
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.NONE, route.State.AMONET_V2_0_0_BOOTED]
    run.said["getprop ro.build.version.name"] = "Fire OS 6.5.7.4"
    route.root()
    assert run.fetched == ["v1.1.0 recovery"]
    assert {
        amonet_biscuit_v1_1_0.SOURCE,
        amonet_biscuit_v2_0_0.SOURCE,
        route.BOOT_ROOT,
    } <= set(run.prefetched[0])
    assert run.stepped[0]["erase"] is None
    assert "stopped after it erased boot0" in said(capsys=capsys)


def test_a_run_fetches_its_route_s_downloads_before_the_first_stage(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    ran: list[str] = []
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            needs=(amonet_biscuit_v2_0_0.SOURCE,),
            run=lambda: ran.append("fastbrick"),
            steps=2,
            then=route.State.AMONET_V1_1_0_BBOE_BOOTED,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    route.ARGUMENTS.verbose = True
    run.states = [route.State.STOCK_FASTBOOT, route.State.AMONET_V1_1_0_BBOE_BOOTED]
    route.root()
    out = said(capsys=capsys)
    assert ran == ["fastbrick"]
    assert run.checked == 1
    assert run.started == 0
    assert run.prefetched == [[amonet_biscuit_v2_0_0.SOURCE]]
    assert "Keep the Dot plugged in" in out
    assert "state: stock-fastboot" in out


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
    monkeypatch.setattr(name="fastboot_driver_missing", target=route, value=check)
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
            needs=(amonet_biscuit_v2_0_0.SOURCE,), run=lambda: None, steps=2, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="check_target", target=route, value=refuse)
    run.states = [route.State.STOCK_FASTBOOT]
    with pytest.raises(route.FatalError, match="Echo"):
        route.root()
    assert run.prefetched == []


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ([route.State.BOOTED], "The Dot is starting Fire OS"),
        ([route.State.STOCK_BOOTED], "appears to be unmodified"),
        ([route.State.EMOS], "runs EchoMuse's emOS"),
        ([route.State.NO_SYSTEM], "/system is damaged"),
        ([route.State.NONE], "Waiting for a Dot on USB"),
        (
            [route.State.STOCK_BOOTED, route.State.NONE],
            "Waiting for the Dot in fastboot mode, with a green ring.",
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
    table = {
        route.State.STOCK_NO_FASTBRICK_FASTBOOT: route.Stage(
            run=lambda: route.ERASED.touch() or True,
            steps=2,
            then=route.State.AMONET_V1_1_0_BBOE_TWRP,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    monkeypatch.setattr(name="bootrom_step", target=route, value=lambda **_: False)
    run.states = [route.State.STOCK_NO_FASTBRICK_FASTBOOT, route.State.NONE]
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
            needs=(amonet_biscuit_v2_0_0.SOURCE,),
            run=lambda: None,
            steps=2,
            then=route.State.AMONET_V2_0_0_TWRP,
        ),
        route.State.AMONET_V2_0_0_TWRP: route.Stage(
            needs=(amonet_biscuit_v2_0_0.SOURCE, BUILDS[BISCUIT]["5.5.5.4"]),
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
    assert [amonet_biscuit_v2_0_0.SOURCE, BUILDS[BISCUIT]["5.5.5.4"]] == route.DOWNLOADS
    assert run.prefetched == []


@pytest.mark.parametrize(
    ("returned", "expected"),
    [(False, ["first", "second"]), (None, ["first"])],
)
def test_a_stage_counts_its_passes_unless_it_returns_false(
    *, expected: list[str], monkeypatch: pytest.MonkeyPatch, returned: bool | None
) -> None:
    ran: list[str] = []
    states = iter([
        route.State.AMONET_V2_0_0_FASTBOOT,
        route.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
    ])

    def state() -> route.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    table = {
        route.State.AMONET_V2_0_0_FASTBOOT: route.Stage(
            passes=frozenset({route.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE}),
            run=lambda: ran.append("first") or returned,
            steps=1,
            then=None,
        ),
        route.State.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: route.Stage(
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
        value=TARGETS[BISCUIT]["amonet-biscuit-v1.1.0-bboe"],
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert ran == expected


def test_a_stale_marker_says_nothing_before_the_dot_is_seen(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.ERASED.touch()
    monkeypatch.setattr(
        name="run", target=route, value=lambda **_: types.SimpleNamespace(stdout="")
    )
    with pytest.raises(route.FatalError, match="no -S option") as stopped:
        route.root()
    assert "boot0 may hold no preloader" not in " ".join(
        ui.explained(error=stopped.value).split()
    )
    assert route.SESSION.boot0_marker is None


def test_a_stock_fire_os_5_run_ends_after_the_restore(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="5.5.5.4", name="stock")
    monkeypatch.setattr(name="stages", target=route, value=dict)
    run.states = [route.State.AMONET_V2_0_0_TWRP, route.State.NONE]
    route.root()
    out = said(capsys=capsys)
    assert "Stock 5.5.5.4 is written" in out
    assert "until the orange ring circles" in out


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ([route.State.STOCK_BOOTED], "nothing to restore"),
        ([route.State.AMONET_V2_0_0_TWRP, route.State.STOCK_BOOTED], "runs stock 8146"),
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
        route.State.STOCK_NO_FASTBRICK_FASTBOOT: route.Stage(
            run=lambda: ran.append("unlock"),
            steps=2,
            then=route.State.AMONET_V1_1_0_BBOE_TWRP,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.STOCK_NO_FASTBRICK_FASTBOOT]
    route.root()
    assert ran == []
    assert "nothing to restore" in said(capsys=capsys)


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
    run.states = [route.State.AMONET_V2_0_0_TWRP, route.State.STOCK_FASTBOOT]
    route.root()
    out = said(capsys=capsys)
    assert "waits in fastboot" in out
    assert "until the orange ring circles" not in out


def test_a_v2_0_0_dot_is_told_to_use_its_gesture_and_to_reboot(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    table = {
        route.State.AMONET_V2_0_0_BOOTED: route.Stage(
            run=lambda: None, steps=1, then=None
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.AMONET_V2_0_0_FASTBOOT, route.State.AMONET_V2_0_0_BOOTED]
    with pytest.raises(RanOutError):
        route.root()
    out = said(capsys=capsys)
    assert "hold the + button while you plug it back in" in out
    assert "Rebooting it into recovery." in out


def test_each_target_has_its_route_s_stages(*, monkeypatch: pytest.MonkeyPatch) -> None:
    state = route.State
    to_twrp = (route.reboot, {"label": "waiting for recovery"})
    to_v2_0_0_twrp = (route.reboot, {"label": "waiting for v2.0.0 recovery to start"})
    shared = {
        state.AMONET_V1_1_0_FASTBOOT: (
            route.stage_amonet_v1_1_0_recovery,
            1,
            state.AMONET_V1_1_0_BBOE_TWRP,
            frozenset(),
        ),
        state.EMOS: (route.stage_emos, 1, None, frozenset()),
        state.NO_SYSTEM: (to_twrp, 1, None, frozenset()),
        state.STOCK_NO_FASTBRICK_FASTBOOT: (
            route.stage_unlock,
            2,
            state.AMONET_V1_1_0_BBOE_TWRP,
            frozenset(),
        ),
    } | dict.fromkeys(
        (state.STOCK_FASTBOOT, state.STOCK_FIREOS5_FASTBOOT),
        (route.stage_fastbrick, 2, state.AMONET_V2_0_0_TWRP, frozenset()),
    )
    reboots = {
        state.AMONET_V2_0_0_BOOTED: (
            to_v2_0_0_twrp,
            1,
            state.AMONET_V2_0_0_TWRP,
            frozenset(),
        ),
        state.BOOTED: (to_twrp, 1, None, frozenset()),
        state.ROOTED: (to_twrp, 1, state.AMONET_V1_1_0_TWRP, frozenset()),
        state.AMONET_V1_1_0_BOOTED: (
            to_twrp,
            1,
            state.AMONET_V1_1_0_TWRP,
            frozenset(),
        ),
        state.AMONET_V1_1_0_BBOE_BOOTED: (
            to_twrp,
            1,
            state.AMONET_V1_1_0_BBOE_TWRP,
            frozenset(),
        ),
    }
    install = (
        route.recovery.carry_out,
        {
            "after": to_v2_0_0_twrp,
            "guard": route.amonet_chain,
            "unlock": route.amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0,
            "zero": ("misc",),
        },
    )
    routes = {
        "amonet-biscuit-v2.0.0": shared
        | {
            state.AMONET_V1_1_0_BBOE_TWRP: (
                install,
                4,
                state.AMONET_V2_0_0_TWRP,
                frozenset(),
            ),
            state.AMONET_V1_1_0_TWRP: (
                install,
                4,
                state.AMONET_V2_0_0_TWRP,
                frozenset(),
            ),
            state.AMONET_V2_0_0_TWRP: (
                route.stage_install_fireos6,
                5,
                state.AMONET_V2_0_0_BOOTED,
                frozenset(),
            ),
            state.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: (
                install,
                4,
                state.AMONET_V2_0_0_TWRP,
                frozenset(),
            ),
        }
        | {rooted: reboots[rooted] for rooted in route.FIREOS5_ROOTED},
        "stock": shared
        | dict.fromkeys(
            route.TWRPS, (route.stage_restore, 16, state.STOCK_BOOTED, route.TWRPS)
        )
        | reboots,
    }
    for name in ("amonet-biscuit-v1.1.0", "amonet-biscuit-v1.1.0-bboe"):
        goal = TARGETS[BISCUIT][name].goal
        chain = (
            route.recovery.carry_out,
            {
                "after": (
                    route.reboot,
                    {
                        "estimate": "345 s",
                        "into": "",
                        "label": "waiting for rooted Fire OS 5 to boot",
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
                state.AMONET_V1_1_0_BBOE_TWRP: (
                    route.stage_install_fireos,
                    4,
                    state.AMONET_V1_1_0_BBOE_BOOTED,
                    frozenset(),
                ),
                state.AMONET_V1_1_0_TWRP: (
                    route.stage_replace_twrp,
                    1,
                    state.AMONET_V1_1_0_BBOE_TWRP,
                    frozenset(),
                ),
                state.AMONET_V2_0_0_BOOTED: reboots[state.AMONET_V2_0_0_BOOTED],
                state.AMONET_V2_0_0_FASTBOOT: (
                    route.stage_downgrade,
                    2,
                    state.AMONET_V1_1_0_BBOE_TWRP,
                    frozenset({
                        state.AMONET_V1_1_0_FASTBOOT,
                        state.AMONET_V2_0_0_FASTBOOT,
                        state.AMONET_V2_0_0_TWRP,
                        state.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
                    }),
                ),
                state.AMONET_V2_0_0_TWRP: (
                    chain,
                    2,
                    state.AMONET_V2_0_0_TWRP_V1_1_0_TABLE,
                    frozenset(),
                ),
                state.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: (chain, 7, goal, frozenset()),
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
    ("name", "totals"),
    [
        ("amonet-biscuit-v1.1.0-bboe", {"stock": 11, "twrp": 9, "v1.1.0": 7}),
        ("amonet-biscuit-v2.0.0", {"stock": 7, "twrp": 5, "v1.1.0": 9}),
    ],
)
def test_fastboot_counts_the_steps_the_route_takes(
    *, monkeypatch: pytest.MonkeyPatch, name: str, totals: dict[str, int]
) -> None:
    state = route.State
    monkeypatch.setattr(
        name="target", target=route.ARGUMENTS, value=TARGETS[BISCUIT][name]
    )
    table = route.stages()
    starts = {
        state.AMONET_V2_0_0_TWRP: totals["twrp"],
        state.AMONET_V2_0_0_TWRP_V1_1_0_TABLE: totals["v1.1.0"],
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
    twrp = route.State.AMONET_V2_0_0_TWRP
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
    run.target(name="amonet-biscuit-v2.0.0")
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.AMONET_V2_0_0_FASTBOOT]
    with pytest.raises(RanOutError):
        route.root()
    assert run.started == 1
    assert list(route.DOWNLOADS) == [amonet_biscuit_v2_0_0.SOURCE, route.ota_build]


def test_the_session_has_no_marker_while_the_first_probe_runs(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.ERASED.touch()

    def state() -> route.State:
        raise KeyboardInterrupt

    monkeypatch.setattr(
        name="run",
        target=route,
        value=lambda **_: types.SimpleNamespace(stdout="  -S SIZE[K|M|G]"),
    )
    monkeypatch.setattr(name="state", target=route, value=state)
    monkeypatch.setattr(name="stages", target=route, value=dict)
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert route.SESSION.boot0_marker is None


def test_the_session_takes_the_marker_after_the_first_probe(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.ERASED.touch()
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
        value=TARGETS[BISCUIT]["amonet-biscuit-v1.1.0-bboe"],
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert route.SESSION.boot0_marker == route.ERASED
    assert not route.ERASED.exists()
