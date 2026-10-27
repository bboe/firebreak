from __future__ import annotations

import functools
import types

import pytest

from firebreak import route, twrp, ui, unlock
from firebreak.devices import BISCUIT, TARGETS, biscuit
from firebreak.devices.biscuit import BUILDS


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
        monkeypatch.setattr(name="pyserial_wheel", target=route, value=lambda: None)
        monkeypatch.setattr(name="amonet_v2_payload", target=route, value=lambda: None)
        monkeypatch.setattr(
            name="stage_amonet_v1_1_0_recovery",
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
    [("5.5.0.3", 2, route.STOCK_STEPS + 2), ("5.5.3.1", 0, route.STOCK_STEPS)],
)
def test_a_bootrom_build_restores_with_the_bootrom_s_downloads_and_steps(
    *, build: str, extra: int, monkeypatch: pytest.MonkeyPatch, steps: int
) -> None:
    monkeypatch.setattr(name="build", target=route.ARGUMENTS, value=build)
    stage = route.restore_stages()[route.State.AMONET_V2_TWRP]
    assert stage.needs[1:] == ((biscuit.V2_0_1_SOURCE, route.pyserial_wheel)[:extra])
    assert stage.steps == steps


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
    assert {table[state].steps for state in route.TWRPS} == {route.STOCK_STEPS + 2}


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
    route.prefetch(needs=[biscuit.BBOE_RECOVERY, biscuit.V2_0_1_SOURCE])
    assert fetched == [
        biscuit.V2_0_1_SOURCE.name,
        biscuit.BBOE_RECOVERY.name,
    ]


def test_a_dot_at_its_goal_has_its_updater_hidden(
    *, capsys: pytest.CaptureFixture[str], run: Run
) -> None:
    run.states = [route.State.AMONET_V1_1_0_BBOE_BOOTED]
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
    run.states = [route.State.AMONET_V2_BOOTED]
    route.root()
    assert "rooted: Fire OS 6.5.7.4, with root adb" in said(capsys=capsys)


@pytest.mark.parametrize(
    ("name", "states", "done", "message"),
    [
        (
            "fireos6",
            [route.State.STOCK_BOOTED],
            [route.State.AMONET_V2_TWRP],
            "boot-root.zip did not take",
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
    twrp = route.State.AMONET_V2_TWRP
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
    route.ERASED.touch()
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    run.states = [route.State.NONE, route.State.AMONET_V1_1_0_BBOE_BOOTED]
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
    route.prefetch(needs=route.needed(start=route.State.AMONET_V2_TWRP, table=table))
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
        ("fireos6", "", "8146"),
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
        needs=route.needed(start=route.State.AMONET_V2_TWRP, table=route.stages())
    )
    assert got == [downloaded]


def test_a_reset_route_takes_five_steps(*, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(name="factory_reset", target=route.ARGUMENTS, value=True)
    monkeypatch.setattr(
        name="target",
        target=route.ARGUMENTS,
        value=TARGETS[BISCUIT]["fireos6"],
    )
    assert route.stages()[route.State.AMONET_V2_TWRP].steps == 5


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
            route.State.AMONET_V2_FASTBOOT,
            [
                biscuit.V1_1_0_SOURCE,
                route.pyserial_wheel,
                biscuit.V2_0_1_SOURCE,
                route.TWRP,
                BUILDS["5.5.5.4"],
                route.MAGISK,
                route.start_prebuild,
            ],
        ),
        ("fireos5", route.State.ROOTED, [route.TWRP]),
        ("fireos5", route.State.EMOS, [route.pyserial_wheel]),
        (
            "fireos6",
            route.State.AMONET_V1_1_0_TWRP,
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
    run.target(name="fireos6")
    route.ERASED.touch()
    monkeypatch.setattr(name="stages", target=route, value=route.stages)
    monkeypatch.setattr(
        name="stage_amonet_v2_recovery",
        target=route,
        value=lambda: run.fetched.append("v2.0.1 recovery"),
    )
    run.states = [route.State.NONE, route.State.AMONET_V2_BOOTED]
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
    argvalues=[(route.State.AMONET_V2_TWRP, True), (route.State.STOCK_BOOTED, False)],
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
        name="fastboot_driver_missing", target=route, value=lambda: False
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
    table = {
        route.State.STOCK_FASTBOOT: route.Stage(
            run=lambda: route.ERASED.touch() or True,
            steps=2,
            then=route.State.AMONET_V1_1_0_BBOE_TWRP,
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
            then=route.State.AMONET_V2_TWRP,
        ),
        route.State.AMONET_V2_TWRP: route.Stage(
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


def test_a_seen_state_clears_the_bootrom_hold(
    *, monkeypatch: pytest.MonkeyPatch
) -> None:
    route.HELD.touch()
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
    assert not route.HELD.exists()


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
        route.State.AMONET_V2_FASTBOOT,
        route.State.AMONET_V2_TWRP_V1_1_0_TABLE,
    ])

    def state() -> route.State:
        found = next(states, None)
        if found is None:
            raise KeyboardInterrupt
        return found

    table = {
        route.State.AMONET_V2_FASTBOOT: route.Stage(
            passes=frozenset({route.State.AMONET_V2_TWRP_V1_1_0_TABLE}),
            run=lambda: ran.append("first") or returned,
            steps=1,
            then=None,
        ),
        route.State.AMONET_V2_TWRP_V1_1_0_TABLE: route.Stage(
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
    run.states = [route.State.AMONET_V2_TWRP, route.State.NONE]
    route.root()
    out = said(capsys=capsys)
    assert "Stock 5.5.5.4 is written" in out
    assert "until the orange ring circles" in out


@pytest.mark.parametrize(
    ("states", "message"),
    [
        ([route.State.STOCK_BOOTED], "nothing to restore"),
        ([route.State.AMONET_V2_TWRP, route.State.STOCK_BOOTED], "runs stock 8146"),
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
            then=route.State.AMONET_V1_1_0_BBOE_TWRP,
        )
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.STOCK_FASTBOOT]
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
    run.states = [route.State.AMONET_V2_TWRP, route.State.STOCK_FASTBOOT]
    route.root()
    out = said(capsys=capsys)
    assert "waits in fastboot" in out
    assert "until the orange ring circles" not in out


def test_a_v2_0_0_dot_is_restarted_into_its_own_twrp(
    *, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, run: Run
) -> None:
    run.target(build="8146", name="stock")
    table = route.stages() | {
        route.State.AMONET_V2_BOOTED: route.Stage(run=lambda: None, steps=1, then=None)
    }
    monkeypatch.setattr(name="stages", target=route, value=lambda: table)
    run.states = [route.State.AMONET_V2_FASTBOOT, route.State.AMONET_V2_BOOTED]
    with pytest.raises(RanOutError):
        route.root()
    out = said(capsys=capsys)
    assert "is in amonet v2's fastboot. Starting its recovery." in out
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
    run.states = [route.State.AMONET_V2_FASTBOOT]
    with pytest.raises(RanOutError):
        route.root()
    assert "hold the + button while you plug it back in" in said(capsys=capsys)


def test_each_target_has_its_route_s_stages(*, monkeypatch: pytest.MonkeyPatch) -> None:
    state = route.State
    to_recovery = (route.reboot, {"label": "waiting for recovery"})
    to_twrp = (route.reboot, {"label": "waiting for TWRP to start"})
    shared = {
        state.AMONET_V1_1_0_FASTBOOT: (
            route.stage_amonet_v1_1_0_recovery,
            1,
            state.AMONET_V1_1_0_BBOE_TWRP,
            frozenset(),
        ),
        state.AMONET_V2_FASTBOOT: (
            route.stage_amonet_v2_recovery,
            1,
            state.AMONET_V2_TWRP,
            frozenset(),
        ),
        state.EMOS: (route.stage_emos, 1, None, frozenset()),
        state.NO_SYSTEM: (to_recovery, 1, None, frozenset()),
    } | dict.fromkeys(
        (state.STOCK_FASTBOOT, state.STOCK_FIREOS5_FASTBOOT),
        (route.stage_fastbrick, 2, state.AMONET_V2_TWRP, frozenset()),
    )
    reboots = {
        state.AMONET_V2_BOOTED: (
            to_twrp,
            1,
            state.AMONET_V2_TWRP,
            frozenset(),
        ),
        state.BOOTED: (to_recovery, 1, None, frozenset()),
        state.ROOTED: (to_recovery, 1, state.AMONET_V1_1_0_TWRP, frozenset()),
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
            "after": to_twrp,
            "guard": route.amonet_chain,
            "unlock": route.biscuit.UNLOCK_TO_FIREOS6,
            "zero": ("misc",),
        },
    )
    routes = {
        "fireos6": shared
        | {
            state.AMONET_V1_1_0_BBOE_TWRP: (
                install,
                4,
                state.AMONET_V2_TWRP,
                frozenset(),
            ),
            state.AMONET_V1_1_0_TWRP: (
                install,
                4,
                state.AMONET_V2_TWRP,
                frozenset(),
            ),
            state.AMONET_V2_TWRP: (
                route.stage_install_fireos6,
                None,
                state.AMONET_V2_BOOTED,
                frozenset(),
            ),
            state.AMONET_V2_TWRP_V1_1_0_TABLE: (
                install,
                4,
                state.AMONET_V2_TWRP,
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
    for name in ("fireos5", "fireos5"):
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
                state.AMONET_V2_BOOTED: reboots[state.AMONET_V2_BOOTED],
                state.AMONET_V2_FASTBOOT: (
                    route.stage_downgrade,
                    2,
                    state.AMONET_V1_1_0_BBOE_TWRP,
                    frozenset({
                        state.AMONET_V1_1_0_FASTBOOT,
                        state.AMONET_V2_FASTBOOT,
                        state.AMONET_V2_TWRP,
                        state.AMONET_V2_TWRP_V1_1_0_TABLE,
                    }),
                ),
                state.AMONET_V2_TWRP: (
                    chain,
                    2,
                    state.AMONET_V2_TWRP_V1_1_0_TABLE,
                    frozenset(),
                ),
                state.AMONET_V2_TWRP_V1_1_0_TABLE: (chain, 7, goal, frozenset()),
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
        ("fireos5", False, {"stock": 11, "twrp": 9, "v1.1.0": 7}),
        ("fireos6", False, {"stock": None, "twrp": None, "v1.1.0": None}),
        ("fireos6", True, {"stock": 7, "twrp": 5, "v1.1.0": 9}),
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
        state.AMONET_V2_TWRP: totals["twrp"],
        state.AMONET_V2_TWRP_V1_1_0_TABLE: totals["v1.1.0"],
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
    twrp = route.State.AMONET_V2_TWRP
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
        value=TARGETS[BISCUIT]["fireos5"],
    )
    with pytest.raises(KeyboardInterrupt):
        route.root()
    assert route.SESSION.boot0_marker == route.ERASED
    assert not route.ERASED.exists()
