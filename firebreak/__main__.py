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
SURVEY = "survey"


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
    builds = ", ".join(
        sorted(
            updates.BUILDS,
            key=lambda build: (
                build not in updates.FIREOS5_BUILDS,
                tuple(map(int, build.split("."))),
            ),
            reverse=True,
        )
    )
    devices = {device.name: device for device in TARGETS}
    names = sorted({name for targets in TARGETS.values() for name in targets})
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""{target_help()}
Run again with another target to move the Dot to it.

  survey OTA [OTA ...]
      not a target: read each Amazon OTA zip for the tables in
      docs/devices.md. It needs no Dot.""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog="firebreak",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print each adb and fastboot command, its exit status and the"
        " time, and each state the Dot reaches",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print what the Dot and this computer are, and the Dot's partition"
        " table, for a support request; it starts the Dot's recovery to read them"
        " and writes no partition",
    )
    parser.add_argument(
        "--write-test",
        action="store_true",
        help=f"write a known pattern over the Dot's {EMMC_TARGET} partition and"
        " read it back, which tells a failing eMMC from a failing USB cable"
        " because nothing crosses USB; it leaves a fresh empty filesystem there,"
        " or says it could not",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="for a Dot that shows no light and needs its test point shorted:"
        " wait for its bootrom, say when the short may come off, then go on",
    )
    parser.add_argument(
        "--device",
        choices=devices,
        help="the device the target is for, which firebreak otherwise reads from"
        " the Echo: "
        + ", ".join(f"{device.name} for the {device.title}" for device in TARGETS),
    )
    parser.add_argument(
        "--credits",
        action="version",
        help="print who did the work firebreak builds on, and stop",
        version=CREDITS,
    )
    parser.add_argument(
        "--no-update-check",
        action="store_true",
        help="do not ask PyPI whether a newer firebreak exists",
    )
    parser.add_argument(
        "--version", action="version", version=f"firebreak {__version__}"
    )
    parser.add_argument(
        "target",
        choices=(*names, SURVEY),
        help=f"the target, one of those listed below, or {SURVEY}",
        metavar="TARGET",
        nargs="?",
    )
    parser.add_argument(
        "rest",
        help="with stock, and only with stock: the BUILD to install, one of "
        + builds
        + f"; {updates.DEFAULT_BUILD} when left out. With {SURVEY}: each OTA"
        " zip to read",
        metavar="BUILD|OTA",
        nargs="*",
    )
    options = parser.parse_intermixed_args()
    if options.target == SURVEY:
        survey_from(options=options, parser=parser)
        return
    device = devices.get(options.device)
    if device and options.target and options.target not in TARGETS[device]:
        parser.error(message=f"the {device.title} has no target {options.target}")
    stock = options.target == STOCK
    if options.rest and not stock:
        parser.error(message="only stock takes a BUILD: " + builds)
    if len(options.rest) > 1 or not set(options.rest) <= set(updates.BUILDS):
        parser.error(message="stock takes one BUILD: " + builds)
    ARGUMENTS.build = (options.rest or [updates.DEFAULT_BUILD if stock else ""])[0]
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
    SESSION.short = options.short
    if options.report:
        report()
        return
    if options.write_test:
        write_test()
        return
    ARGUMENTS.target = choose_target(device=device, name=options.target)
    root()


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


def survey_from(
    *, options: argparse.Namespace, parser: argparse.ArgumentParser
) -> None:
    if not options.rest:
        parser.error(message=f"{SURVEY} needs at least one OTA")
    if options.report or options.write_test or options.short or options.device:
        parser.error(
            message=f"{SURVEY} takes none of --report, --write-test, --short and"
            " --device"
        )
    check_root()
    make_cache()
    survey_all(paths=[pathlib.Path(path) for path in options.rest])


def target_help() -> str:
    lines = []
    for device, targets in TARGETS.items():
        lines.append(f"targets for the {device.title}:")
        default = DEFAULTS[device]
        for target in sorted(
            targets.values(), key=lambda target: (target.name != default, target.name)
        ):
            name = target.name + (" [BUILD]" if target.name == STOCK else "")
            lines.append(
                f"  {name}, the default" if target.name == default else f"  {name}"
            )
            lines.extend(
                textwrap.wrap(
                    initial_indent=" " * 6,
                    subsequent_indent=" " * 6,
                    text=target.summary,
                    width=74,
                )
            )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
