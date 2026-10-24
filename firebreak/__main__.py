"""Change the firmware on an Echo Dot (2nd Generation) over USB: unlock it, or
return it to stock. It finds where the Dot is, from stock, part way through, or
on another target, and keeps going until the Dot is on the target: it waits
while the Dot reboots, and while you take a step it asks for. Stopped, it picks
up where it left off on the next run. It uses the one Dot on USB; set
ANDROID_SERIAL when several are. It needs Python 3.9 or later, and adb and
fastboot from Android platform-tools.
https://github.com/bboe/firebreak/blob/main/docs/rooting.md says why each
step is there.
"""

from __future__ import annotations

import argparse
import contextlib
import pathlib
import shutil
import subprocess
import sys
import textwrap

from firebreak import __version__, updates
from firebreak.cache import make_cache
from firebreak.emos import child_emos
from firebreak.host import check_adb, check_python, check_root, check_user
from firebreak.identify import choose_target
from firebreak.route import root
from firebreak.support import report, write_test
from firebreak.survey import survey_all
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
from firebreak.unlocks.targets import (
    DEFAULTS,
    DEPRECATED,
    FIREOS5,
    FIREOS6,
    REMOVED_IN,
    STOCK,
    TARGETS,
)
from firebreak.write_test import EMMC_TARGET

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
REPORT = "report"
SURVEY = "survey"
UNLOCK = "unlock"
WRITE_TEST = "write-test"


def build_parser() -> argparse.ArgumentParser:
    builds = sorted(
        updates.BUILDS,
        key=lambda build: (
            build not in updates.FIREOS5_BUILDS,
            tuple(map(int, build.split("."))),
        ),
        reverse=True,
    )
    about = {
        REPORT: "print what the Dot and this computer are, and the Dot's"
        " partition table, for a support request. It starts the Dot's recovery"
        " to read them and writes no partition.",
        SURVEY: "read each Amazon OTA zip for the tables in docs/devices.md. It"
        " needs no Dot.",
        UNLOCK: "unlock the Dot and root it, to TARGET or to the newest Fire OS"
        " firebreak supports when TARGET is left out.",
        WRITE_TEST: f"write a known pattern over the Dot's {EMMC_TARGET}"
        " partition and read it back, which tells a failing eMMC from a failing"
        " USB cable because nothing crosses USB. It leaves a fresh empty"
        " filesystem there, or says it could not.",
    }
    labels = {SURVEY: " OTA [OTA ...]", UNLOCK: " [TARGET]"}
    parents = option_parents()
    quiet = option_parents(hidden=True)
    every = ["--device", "--fastboot", "--no-update-check", "--short", "--verbose"]
    rooting = ["--device", "--no-update-check", "--short", "--verbose"]
    uses = {
        REPORT: ["--no-update-check", "--verbose"],
        STOCK: every,
        SURVEY: ["--no-update-check", "--verbose"],
        UNLOCK: rooting,
        WRITE_TEST: ["--no-update-check", "--short", "--verbose"],
        **dict.fromkeys(DEPRECATED, rooting),
    }
    described = dict(about)
    described.update({
        name: target.summary
        for targets in TARGETS.values()
        for name, target in targets.items()
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

Run it again with another of these to move the Dot there.

other commands:
"""
        + "\n".join(
            line
            for name in sorted(about)
            if name != UNLOCK
            for line in listed(label=name + labels.get(name, ""), summary=about[name])
        )
        + "\n\nRun `firebreak COMMAND --help` for what that command takes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[
            (quiet if name in {"--device", "--fastboot", "--short"} else parents)[name]
            for name in sorted(["--credits", *every])
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
            description=described[name],
            parents=[parents[each] for each in sorted(uses[name])],
        )
        if name == STOCK:
            made.add_argument(
                "build",
                choices=builds,
                default=updates.DEFAULT_BUILD,
                help="the build to install, one of "
                + ", ".join(builds)
                + f"; {updates.DEFAULT_BUILD} when left out",
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


def canonical(*, name: str | None) -> str | None:
    was = DEPRECATED.get(name or "")
    return was.name if was else name


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
    SESSION.fastboot = options.fastboot
    SESSION.short = options.short
    command = {REPORT: report, WRITE_TEST: write_test}.get(options.command)
    if command:
        command()
        return
    ARGUMENTS.target = choose_target(
        device=DEVICES.get(options.device),
        name=options.target if options.command == UNLOCK else options.command,
    )
    root()


def listed(*, label: str, summary: str) -> list[str]:
    return [
        f"  {label}",
        *textwrap.wrap(
            initial_indent=" " * 6, subsequent_indent=" " * 6, text=summary, width=74
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
            "--fastboot",
            (
                "leave the Dot in fastboot at the end instead of letting it"
                " start the firmware it now holds, so the next run needs no"
                " button held"
            ),
        ),
        ("--no-update-check", "do not ask PyPI whether a newer firebreak exists"),
        (
            "--short",
            (
                "for a Dot that shows no light and needs its test point"
                " shorted: wait for its bootrom, say when the short may come"
                " off, then go on"
            ),
        ),
        (
            "--verbose",
            (
                "print each adb and fastboot command, its exit status and the"
                " time, and each state the Dot reaches"
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
        else "the device the command is for, which firebreak otherwise reads"
        " from the Echo: "
        + ", ".join(f"{device.name} for the {device.title}" for device in TARGETS),
    )
    return made


def parsed() -> argparse.Namespace:
    parser = build_parser()
    options = parser.parse_args()
    for option, default in (
        ("build", ""),
        ("device", None),
        ("fastboot", False),
        ("no_update_check", False),
        ("short", False),
        ("target", None),
        ("verbose", False),
    ):
        setattr(options, option, getattr(options, option, default))
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
        REPORT: set(),
        STOCK: {"device", "fastboot", "short"},
        SURVEY: set(),
        WRITE_TEST: {"short"},
    }.get(options.command, {"device", "short"})
    for option in sorted({"device", "fastboot", "short"} - takes):
        if getattr(options, option):
            parser.error(message=f"{options.command} takes no --{option}")
    if options.fastboot and options.build in updates.BOOTROM_BUILDS:
        parser.error(
            message=f"stock {options.build} ends in its bootrom over a serial"
            " port, which cannot leave the Dot in fastboot"
        )
    device = DEVICES.get(options.device)
    wanted = options.target if options.command == UNLOCK else options.command
    if (
        device
        and wanted in target_names()
        and canonical(name=wanted) not in TARGETS[device]
    ):
        parser.error(message=f"the {device.title} has no target {wanted}")
    return options


def target_help() -> str:
    lines = []
    for device, targets in TARGETS.items():
        lines.append(f"commands for the {device.title}:")
        default = DEFAULTS[device]
        lines.extend(listed(label=STOCK + " [BUILD]", summary=targets[STOCK].summary))
        lines.append(f"  {UNLOCK} [TARGET], where TARGET is one of:")
        for target in sorted(
            (target for target in targets.values() if target.unlock),
            key=lambda target: (target.name != default, target.name),
        ):
            label = target.name + (", the default" if target.name == default else "")
            lines.extend(
                "  " + line for line in listed(label=label, summary=target.summary)
            )
    return "\n".join(lines)


def target_names() -> set[str]:
    return {name for targets in TARGETS.values() for name in targets} | set(DEPRECATED)


def unlock_targets() -> list[str]:
    return sorted({
        name
        for targets in TARGETS.values()
        for name, target in targets.items()
        if target.unlock
    })


if __name__ == "__main__":
    main()
