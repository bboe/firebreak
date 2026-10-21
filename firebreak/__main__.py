"""Change the firmware on an Echo Dot (2nd Generation) over USB: root it, or
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
from firebreak.unlocks.targets import DEFAULTS, STOCK, TARGETS
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
WRITE_TEST = "write-test"


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
        device=DEVICES.get(options.device), name=options.command
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


def parsed() -> argparse.Namespace:
    builds = sorted(
        updates.BUILDS,
        key=lambda build: (
            build not in updates.FIREOS5_BUILDS,
            tuple(map(int, build.split("."))),
        ),
        reverse=True,
    )
    common_parent = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    common_parent.add_argument(
        "--verbose",
        action="store_true",
        help="print each adb and fastboot command, its exit status and the"
        " time, and each state the Dot reaches",
    )
    common_parent.add_argument(
        "--no-update-check",
        action="store_true",
        help="do not ask PyPI whether a newer firebreak exists",
    )
    fastboot_parent = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    fastboot_parent.add_argument(
        "--fastboot",
        action="store_true",
        help="leave the Dot in fastboot at the end instead of letting it start"
        " the firmware it now holds, so the next run needs no button held",
    )
    short_parent = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    short_parent.add_argument(
        "--short",
        action="store_true",
        help="for a Dot that shows no light and needs its test point shorted:"
        " wait for its bootrom, say when the short may come off, then go on",
    )
    device_parent = argparse.ArgumentParser(
        add_help=False, argument_default=argparse.SUPPRESS
    )
    device_parent.add_argument(
        "--device",
        choices=DEVICES,
        help="the device the target is for, which firebreak otherwise reads from"
        " the Echo: "
        + ", ".join(f"{device.name} for the {device.title}" for device in TARGETS),
    )
    about = {
        REPORT: "print what the Dot and this computer are, and the Dot's"
        " partition table, for a support request. It starts the Dot's recovery"
        " to read them and writes no partition.",
        WRITE_TEST: f"write a known pattern over the Dot's {EMMC_TARGET}"
        " partition and read it back, which tells a failing eMMC from a failing"
        " USB cable because nothing crosses USB. It leaves a fresh empty"
        " filesystem there, or says it could not.",
        SURVEY: "read each Amazon OTA zip for the tables in docs/devices.md. It"
        " needs no Dot.",
    }
    labels = {WRITE_TEST: " [--short]", SURVEY: " OTA [OTA ...]"}
    commands_help = [
        line
        for name, summary in about.items()
        for line in listed(label=name + labels.get(name, ""), summary=summary)
    ]
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""{target_help()}
Run again with another target to move the Dot to it.

commands, which are not targets:
"""
        + "\n".join(commands_help),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[common_parent, fastboot_parent, short_parent, device_parent],
        prog="firebreak",
    )
    parser.add_argument(
        "--credits",
        action="version",
        help="print who did the work firebreak builds on, and stop",
        version=CREDITS,
    )
    parser.add_argument(
        "--version", action="version", version=f"firebreak {__version__}"
    )
    commands = parser.add_subparsers(
        dest="command",
        help="the target, or a command, one of those listed below",
        metavar="TARGET|COMMAND",
    )
    summaries = {
        name: target.summary
        for targets in TARGETS.values()
        for name, target in targets.items()
    }
    for name, summary in sorted(summaries.items()):
        target = commands.add_parser(
            name,
            description=summary,
            parents=[common_parent, fastboot_parent, short_parent, device_parent],
        )
        if name == STOCK:
            target.add_argument(
                "build",
                choices=builds,
                default=updates.DEFAULT_BUILD,
                help="the build to install, one of "
                + ", ".join(builds)
                + f"; {updates.DEFAULT_BUILD} when left out",
                metavar="BUILD",
                nargs="?",
            )
    commands.add_parser(REPORT, description=about[REPORT], parents=[common_parent])
    commands.add_parser(
        WRITE_TEST, description=about[WRITE_TEST], parents=[common_parent, short_parent]
    )
    commands.add_parser(
        SURVEY, description=about[SURVEY], parents=[common_parent]
    ).add_argument("otas", help="an Amazon OTA zip", metavar="OTA", nargs="+")
    options = parser.parse_args()
    for option, default in (
        ("build", ""),
        ("device", None),
        ("fastboot", False),
        ("no_update_check", False),
        ("short", False),
        ("verbose", False),
    ):
        setattr(options, option, getattr(options, option, default))
    takes = {
        REPORT: set(),
        STOCK: {"device", "fastboot", "short"},
        SURVEY: set(),
        WRITE_TEST: {"short"},
    }.get(options.command, {"device", "short"})
    for option in sorted({"device", "fastboot", "short"} - takes):
        if getattr(options, option):
            parser.error(
                message=f"{options.command or 'the default target'} takes no --{option}"
            )
    if options.fastboot and options.build in updates.BOOTROM_BUILDS:
        parser.error(
            message=f"stock {options.build} ends in its bootrom over a serial"
            " port, which cannot leave the Dot in fastboot"
        )
    device = DEVICES.get(options.device)
    if (
        device
        and options.command in summaries
        and options.command not in TARGETS[device]
    ):
        parser.error(message=f"the {device.title} has no target {options.command}")
    return options


def target_help() -> str:
    lines = []
    for device, targets in TARGETS.items():
        lines.append(f"targets for the {device.title}:")
        default = DEFAULTS[device]
        for target in sorted(
            targets.values(), key=lambda target: (target.name != default, target.name)
        ):
            label = target.name + (" [BUILD]" if target.name == STOCK else "")
            if target.name == default:
                label += ", the default"
            lines.extend(listed(label=label, summary=target.summary))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
