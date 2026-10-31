"""Change the firmware on an Echo Dot (2nd Generation) or an Echo (2nd
Generation) over USB: unlock it, or return it to stock. It finds where the Echo
is, from stock, part way through, or on another target, and keeps going until
the Echo is on the target: it waits while the Echo reboots, and while you take
a step it asks for. Stopped, it picks up where it left off on the next run. It
uses the one Echo on USB; set ANDROID_SERIAL when several are. It needs Python
3.9 or later, and adb and fastboot from Android platform-tools.
https://github.com/bboe/firebreak/blob/main/docs/unlocking.md says why each
step is there.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import pathlib
import shutil
import subprocess
import sys
import textwrap
from typing import TYPE_CHECKING

from firebreak import __version__
from firebreak.cache import make_cache
from firebreak.devices import (
    BUILDS,
    DEFAULT_BUILDS,
    DEFAULTS,
    DEPRECATED,
    FIREOS5_BUILDS,
    TARGETS,
    biscuit,
)
from firebreak.emos import child_emos
from firebreak.entry import (
    BOOTROM,
    FASTBOOT,
    SHORT,
    TWRP,
    bootrom_device,
    bootrom_entry,
    entries,
    fastboot_entry,
    short_entry,
    twrp_entry,
)
from firebreak.host import check_adb, check_python, check_root, check_user
from firebreak.identify import choices, choose_target
from firebreak.plugin import FireOs6
from firebreak.route import root
from firebreak.support import report, write_test
from firebreak.survey import survey_all
from firebreak.targets import FIREOS5, FIREOS6, REMOVED_IN, STOCK
from firebreak.ui import (
    ARGUMENTS,
    SESSION,
    ANSIColor,
    FatalError,
    Kind,
    paint,
    show,
    stop,
    upgrade,
    warn,
)
from firebreak.write_test import EMMC_TARGET

if TYPE_CHECKING:
    from collections.abc import Iterable

    from firebreak.plugin import Device

CREDITS = """firebreak automates work that other people did first.

xyz wrote amonet, a MediaTek bootrom exploit. firebreak's bootrom and payload
clients follow its protocol.
  https://github.com/xyzz/amonet
k4y0z made the first port of amonet to the Echo Dot (2nd Generation).
  https://github.com/chaosmaster
Rortiz2 continued that port, released it with TWRP, and keeps the XDA thread.
The bboe TWRP is a fork of their TWRP tree.
  https://github.com/R0rt1z2
  https://github.com/R0rt1z2/amonet/tree/mt8163-biscuit
  https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/
  https://github.com/R0rt1z2/twrp_device_amazon_echo-mt8163
AntiEngineer helped find the pins and bring up UART on a Dot.
topjohnwu wrote Magisk, which roots Fire OS 5.
  https://github.com/topjohnwu/Magisk
Andy Goetz described how to short the eMMC bus at the passives beside R60.
  https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/
mtkclient, by bkerler, agrees with two of firebreak's bootrom addresses.
  https://github.com/bkerler/mtkclient
ftvdb keeps the Fire OS builds that the tables link to.
  https://ftvdb.com/"""
DEVICES = {device.name: device for device in TARGETS}
FACTORY_RESETS = {
    name
    for targets in TARGETS.values()
    for name, target in targets.items()
    if isinstance(target.installs, FireOs6) and target.unlock
}
REPORT = "report"
SURVEY = "survey"
UNLOCK = "unlock"
WRITE_TEST = "write-test"


def build_parser() -> argparse.ArgumentParser:
    builds = ordered(builds={build for each in BUILDS.values() for build in each})
    about = {
        BOOTROM: "hold the Echo in its bootrom, where amonet's payload can reach"
        " the eMMC with no firmware running. It asks before it clears boot0,"
        " which is what leaves an Echo startable from its bootrom alone. An"
        " Echo that shows no light cannot be reached this way: `firebreak"
        " short` is for that one.",
        FASTBOOT: "start the Echo's fastboot, whichever bootloader it holds. It"
        " reboots an Echo that answers adb, and asks for the button gesture"
        " where it cannot. It writes nothing.",
        REPORT: "print what the Echo and this computer are, and the Echo's"
        " partition table, for a support request. It starts the Echo's recovery"
        " to read them and writes no partition.",
        SHORT: "hold the bootrom of an Echo that shows no light, by shorting its"
        " test point. It says where to short, waits for the bootrom, says when"
        " the short may come off, and leaves amonet's payload holding it. It"
        " writes nothing, and --device picks whose test point to describe.",
        SURVEY: "read each Amazon OTA zip for the tables in docs/devices.md. It"
        " needs no Echo.",
        TWRP: "start the Echo's TWRP. On an unlocked Echo it restarts into the"
        " recovery already there and writes nothing, and says what to do where"
        " that is not a TWRP. A locked Echo has to be unlocked first, which"
        " erases it, so that one is asked about.",
        UNLOCK: "unlock the Echo and root it, to TARGET or to the newest Fire OS"
        " firebreak supports when TARGET is left out.",
        WRITE_TEST: f"write a known pattern over the Echo's {EMMC_TARGET}"
        " partition and read it back, which tells a failing eMMC from a failing"
        " USB cable because nothing crosses USB. It leaves a fresh empty"
        " filesystem there, or says it could not.",
    }
    labels = {SURVEY: " OTA [OTA ...]", UNLOCK: " [TARGET]"}
    parents = option_parents()
    quiet = option_parents(hidden=True)
    navigating = ["--force", "--no-update-check", "--verbose"]
    restoring = [
        "--end-in-fireos",
        "--no-update-check",
        "--no-wait",
        "--no-way-back",
        "--verbose",
    ]
    rooting = ["--factory-reset", "--no-update-check", "--verbose"]
    every = sorted({"--credits", "--device", *navigating, *restoring, *rooting})
    uses = {
        BOOTROM: navigating,
        FASTBOOT: ["--no-update-check", "--verbose"],
        REPORT: ["--no-update-check", "--verbose"],
        SHORT: ["--device", "--no-update-check", "--verbose"],
        STOCK: restoring,
        SURVEY: ["--no-update-check", "--verbose"],
        TWRP: navigating,
        UNLOCK: rooting,
        WRITE_TEST: ["--no-update-check", "--verbose"],
        **dict.fromkeys(DEPRECATED, rooting),
    }
    described = dict(about)
    summaries: dict[str, dict[Device, str]] = {}
    for device, targets in TARGETS.items():
        for name, target in targets.items():
            summaries.setdefault(name, {})[device] = target.summary
    described.update({
        name: " ".join(
            f"For the {device.title}: {summary}"
            for device, summary in by_device.items()
        )
        if len(by_device) > 1
        else next(iter(by_device.values()))
        for name, by_device in summaries.items()
    })
    described.update({
        name: f"goes away in firebreak {REMOVED_IN}: use"
        f" `firebreak {UNLOCK} {was.name}` instead."
        + (" " + was.note if was.note else "")
        for name, was in DEPRECATED.items()
    })
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""{target_help()}

Run it again with another of these to move the Echo there.

commands that reach one entry point and stop there:
"""
        + "\n".join(
            line
            for name in entries()
            for line in listed(label=name + labels.get(name, ""), summary=about[name])
        )
        + """

other commands:
"""
        + "\n".join(
            line
            for name in sorted(about)
            if name not in {UNLOCK, *entries()}
            for line in listed(label=name + labels.get(name, ""), summary=about[name])
        )
        + "\n\nRun `firebreak COMMAND --help` for what that command takes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[
            (
                quiet
                if name
                in {
                    "--device",
                    "--end-in-fireos",
                    "--factory-reset",
                    "--force",
                    "--no-wait",
                    "--no-way-back",
                }
                else parents
            )[name]
            for name in every
        ],
        prog="firebreak",
    )
    parser.add_argument(
        "--version", action="version", version=f"firebreak {__version__}"
    )
    commands = parser.add_subparsers(
        dest="command",
        help="the command to run, one of those listed below",
        metavar="COMMAND",
    )
    for name in sorted(uses):
        made = commands.add_parser(
            name,
            description="\n".join(textwrap.wrap(described[name], width=74))
            if name == STOCK
            else described[name],
            epilog=stock_builds_help() if name == STOCK else None,
            formatter_class=argparse.RawDescriptionHelpFormatter
            if name == STOCK
            else argparse.HelpFormatter,
            parents=[
                (parents if each in uses[name] else quiet)[each]
                for each in sorted({*uses[name], "--device"})
            ],
        )
        if name == STOCK:
            made.add_argument(
                "build",
                choices=builds,
                default=None,
                help="the build to install, from the list below",
                metavar="BUILD",
                nargs="?",
            )
        elif name == SURVEY:
            made.add_argument(
                "otas", help="an Amazon OTA zip", metavar="OTA", nargs="+"
            )
        elif name == UNLOCK:
            made.add_argument(
                "target",
                choices=unlock_targets(),
                help="the target to unlock to, one of "
                + ", ".join(unlock_targets())
                + "; the newest Fire OS when left out",
                metavar="TARGET",
                nargs="?",
            )
    return parser


def check_for_update() -> None:
    with contextlib.suppress(Exception):
        import update_checker  # ruff: ignore[import-outside-top-level]

        result = update_checker.UpdateChecker().check(
            package_name="firebreak", package_version=__version__
        )
        if result:
            how, line = upgrade()
            warn(text=f"{result} To use it, {how}:")
            show(kind=Kind.WARN, text=paint(code=ANSIColor.YELLOW, text=f"  {line}"))


def child_main(*, arguments: list[str], name: str) -> int:
    if sys.path[0] == str(pathlib.Path.cwd()):
        del sys.path[0]
    return {"emos": child_emos}[name](action=arguments[0], want=arguments[1])


def chosen_device(*, name: str | None) -> Device | None:
    if len(choices(device=None, name=name)) <= 1:
        return None
    return bootrom_device()


def cli() -> None:
    options = parsed()
    if options.command == SURVEY:
        check_root()
        make_cache()
        survey_all(paths=[pathlib.Path(path) for path in options.otas])
        return
    ARGUMENTS.build = options.build
    ARGUMENTS.verbose = options.verbose
    check_python()
    for tool in ("adb", "fastboot"):
        if not shutil.which(cmd=tool):
            raise FatalError(
                message=tool + " not found: install Android platform-tools"
            )
    check_user()
    if not options.no_update_check:
        check_for_update()
    check_adb()
    make_cache()
    SESSION.fastboot = not options.end_in_fireos
    SESSION.no_wait = options.no_wait
    SESSION.short = options.command == SHORT
    SESSION.device = DEVICES.get(options.device)
    command = {
        BOOTROM: functools.partial(bootrom_entry, force=options.force),
        FASTBOOT: fastboot_entry,
        REPORT: report,
        SHORT: short_entry,
        TWRP: functools.partial(twrp_entry, force=options.force),
        WRITE_TEST: write_test,
    }.get(options.command)
    if command:
        command()
        return
    name = options.target if options.command == UNLOCK else options.command
    ARGUMENTS.target = choose_target(
        device=chosen_device(name=name), name=name, reader=bootrom_device
    )
    ARGUMENTS.factory_reset = options.factory_reset
    if ARGUMENTS.factory_reset and ARGUMENTS.target.name not in FACTORY_RESETS:
        raise FatalError(
            message=f"{ARGUMENTS.target.name} takes no --factory-reset: only"
            f" {', '.join(sorted(FACTORY_RESETS))} install a Fire OS 6 build to"
            " erase to."
        )
    device = ARGUMENTS.target.device
    if ARGUMENTS.target.name == STOCK:
        stock_build(allowed=options.no_way_back, device=device, wanted=options.build)
    root()


def listed(*, label: str, summary: str) -> list[str]:
    return [
        f"  {label}",
        *textwrap.wrap(
            break_on_hyphens=False,
            initial_indent=" " * 6,
            subsequent_indent=" " * 6,
            text=summary,
            width=74,
        ),
    ]


def main() -> None:
    if sys.argv[1:2] == ["_child"]:
        sys.exit(child_main(arguments=sys.argv[3:], name=sys.argv[2]))
    try:
        cli()
    except FatalError as error:
        stop(error=error)
    except KeyboardInterrupt:
        stop(error=FatalError(message="stopped", prefix=""))
    except subprocess.TimeoutExpired as error:
        stop(
            error=FatalError(
                message=f"{' '.join(map(str, error.cmd))} did not finish in"
                f" {error.timeout:.0f} seconds"
            )
        )


def option_parents(*, hidden: bool = False) -> dict[str, argparse.ArgumentParser]:
    made: dict[str, argparse.ArgumentParser] = {}
    for name, summary in (
        (
            "--end-in-fireos",
            (
                "let the Echo start the firmware it now holds at the end, where"
                " the run otherwise leaves it in fastboot, which the next run"
                " reaches with no button held"
            ),
        ),
        (
            "--factory-reset",
            (
                "erase userdata and install the target's Fire OS 6 build in both"
                " slots, where the target otherwise roots the Fire OS 6 already"
                " installed and keeps the Echo's Wi-Fi and Alexa setup"
            ),
        ),
        ("--no-update-check", "do not ask PyPI whether a newer firebreak exists"),
        (
            "--no-wait",
            ("start the writes at once, without the 10 seconds that Ctrl-C cancels in"),
        ),
        (
            "--no-way-back",
            (
                "install a stock build whose bootloader no payload here unlocks,"
                " which leaves an Echo that firebreak cannot unlock again"
            ),
        ),
        (
            "--force",
            (
                "do not ask before a write that a command needs to reach the"
                " state it is named for"
            ),
        ),
        (
            "--verbose",
            (
                "print each adb and fastboot command, its exit status and the"
                " time, and each state the Echo reaches"
            ),
        ),
    ):
        made[name] = argparse.ArgumentParser(
            add_help=False, argument_default=argparse.SUPPRESS
        )
        made[name].add_argument(
            name,
            action="store_true",
            help=argparse.SUPPRESS if hidden else summary,
        )
    made["--credits"] = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    made["--credits"].add_argument(
        "--credits",
        action="version",
        help="print who did the work firebreak builds on, and stop",
        version=CREDITS,
    )
    made["--device"] = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    made["--device"].add_argument(
        "--device",
        choices=DEVICES,
        help=argparse.SUPPRESS
        if hidden
        else "whose test point to describe, which an Echo that shows no light"
        " cannot say itself. Every other command reads the device from the"
        " Echo. One of: "
        + ", ".join(f"{device.name} for the {device.title}" for device in TARGETS),
    )
    return made


def ordered(*, builds: Iterable[str]) -> list[str]:
    fireos5 = frozenset().union(*FIREOS5_BUILDS.values())
    return sorted(
        builds,
        key=lambda build: (
            build not in fireos5,
            tuple(map(int, build.split("."))),
        ),
        reverse=True,
    )


def parsed() -> argparse.Namespace:
    parser = build_parser()
    options = parser.parse_args()
    for option, default in (
        ("build", ""),
        ("device", None),
        ("end_in_fireos", False),
        ("factory_reset", False),
        ("force", False),
        ("no_update_check", False),
        ("no_wait", False),
        ("no_way_back", False),
        ("target", None),
        ("verbose", False),
    ):
        setattr(options, option, getattr(options, option, None) or default)
    if options.command is None:
        notice = (
            "The command line arguments have changed. What used to be the"
            f" default is now `firebreak {UNLOCK} {FIREOS5}`, and the new"
            f" default is `firebreak {UNLOCK} {FIREOS6}`. This warning goes"
            f" away in firebreak {REMOVED_IN}."
        )
        warn(text=notice)
        print()
        parser.print_help()
        print()
        warn(text=notice)
        sys.exit(1)
    takes = {
        BOOTROM: {"force"},
        FASTBOOT: set(),
        REPORT: set(),
        SHORT: {"device"},
        STOCK: {"end_in_fireos", "no_wait", "no_way_back"},
        SURVEY: set(),
        TWRP: {"force"},
        WRITE_TEST: set(),
    }.get(options.command, {"factory_reset"})
    for option in sorted(
        {
            "device",
            "end_in_fireos",
            "factory_reset",
            "force",
            "no_wait",
            "no_way_back",
        }
        - takes
    ):
        if getattr(options, option):
            dashed = option.replace("_", "-")
            parser.error(message=f"{options.command} takes no --{dashed}")
    return options


def stock_build(*, allowed: bool, device: Device, wanted: str) -> None:
    ARGUMENTS.build = wanted or DEFAULT_BUILDS[device]
    if ARGUMENTS.build not in BUILDS[device]:
        raise FatalError(
            message=f"the {device.title} has no stock build {ARGUMENTS.build}:"
            f" use one of {', '.join(ordered(builds=BUILDS[device]))}"
        )
    if BUILDS[device][ARGUMENTS.build].no_way_back and not allowed:
        raise FatalError(
            message=f"stock {ARGUMENTS.build} ships a bootloader no payload here"
            f" unlocks, so a restore to it leaves an {device.title} that firebreak"
            " cannot unlock again: its bootrom would still take the chain, but"
            " nothing here gets a locked one there. Pass --no-way-back to install"
            " it anyway."
        )
    if ARGUMENTS.build in biscuit.BOOTROM_BUILDS and SESSION.fastboot:
        warn(
            text=f"Stock {ARGUMENTS.build} ends in its bootrom over a serial port,"
            f" which cannot leave the {device.title} in fastboot. firebreak holds"
            " it in its bootrom instead, where the next run picks it up with no"
            " button held."
        )


def stock_builds_help() -> str:
    lines = ["the builds BUILD takes:"]
    for device, each in BUILDS.items():
        free = {name for name, ota in each.items() if not ota.no_way_back}
        gated = {name for name, ota in each.items() if ota.no_way_back}
        lines.append("")
        lines.extend(
            listed(
                label=f"{device.title}, {DEFAULT_BUILDS[device]} when left out:",
                summary=", ".join(ordered(builds=free)),
            )
        )
        if gated:
            lines.extend(
                "  " + line
                for line in listed(
                    label="and, only with --no-way-back, which cannot be undone:",
                    summary=", ".join(ordered(builds=gated)),
                )
            )
    return "\n".join(lines)


def target_help() -> str:
    lines = []
    for device, targets in TARGETS.items():
        if lines:
            lines.append("")
        lines.append(f"commands for the {device.title}:")
        default = DEFAULTS.get(device)
        lines.extend(listed(label=STOCK + " [BUILD]", summary=targets[STOCK].summary))
        unlocks = sorted(
            (target for target in targets.values() if target.unlock),
            key=lambda target: (target.name != default, target.name),
        )
        if not unlocks:
            continue
        lines.append(f"  {UNLOCK} [TARGET], where TARGET is one of:")
        for target in unlocks:
            label = target.name + (", the default" if target.name == default else "")
            lines.extend(
                "  " + line for line in listed(label=label, summary=target.summary)
            )
    return "\n".join(lines)


def unlock_targets() -> list[str]:
    return sorted({
        name
        for targets in TARGETS.values()
        for name, target in targets.items()
        if target.unlock
    })


if __name__ == "__main__":
    main()
