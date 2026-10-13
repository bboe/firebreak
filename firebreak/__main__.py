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

from firebreak import __version__, updates
from firebreak.cache import move_old_caches
from firebreak.emos import child_emos
from firebreak.host import check_adb, check_user
from firebreak.identify import check_target
from firebreak.plugin import FireOs6
from firebreak.route import root
from firebreak.support import report, write_test
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
from firebreak.unlocks import (
    amonet_biscuit_v1_1_0,
    amonet_biscuit_v1_1_0_bboe,
    amonet_biscuit_v2_0_0,
)
from firebreak.unlocks.targets import TARGETS
from firebreak.write_test import EMMC_TARGET

AMONET_BISCUIT_V1_1_0 = amonet_biscuit_v1_1_0.AMONET_BISCUIT_V1_1_0.name
AMONET_BISCUIT_V1_1_0_BBOE = amonet_biscuit_v1_1_0_bboe.AMONET_BISCUIT_V1_1_0_BBOE.name
AMONET_BISCUIT_V2_0_0 = amonet_biscuit_v2_0_0.AMONET_BISCUIT_V2_0_0.name
TWRP_VERSION = amonet_biscuit_v1_1_0_bboe.TWRP_VERSION


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
    installs = TARGETS[AMONET_BISCUIT_V2_0_0].installs
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=f"""targets:
  {AMONET_BISCUIT_V1_1_0_BBOE}, the default
      rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP {TWRP_VERSION}.
  {AMONET_BISCUIT_V1_1_0}
      the same, with amonet v1.1.0's own TWRP 3.2.3.
  {AMONET_BISCUIT_V2_0_0}
      amonet v2.0.0's own procedure: Fire OS 6 {installs.build}
      with boot-root.zip's root adb.
  stock [BUILD]
      Amazon's Fire OS 6 BUILD, {updates.DEFAULT_BUILD} when left out, which
      erases the whole Dot.
Run again with another target to move the Dot to it.""",
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
        "--no-update-check",
        action="store_true",
        help="do not ask PyPI whether a newer firebreak exists",
    )
    parser.add_argument(
        "target",
        choices=tuple(TARGETS),
        default=AMONET_BISCUIT_V1_1_0_BBOE,
        help="the target, one of those listed below",
        metavar="TARGET",
        nargs="?",
    )
    parser.add_argument(
        "build",
        choices=sorted(updates.BUILDS),
        help="with stock, and only with stock: the build to install, one of "
        + ", ".join(sorted(updates.BUILDS))
        + f"; {updates.DEFAULT_BUILD} when left out",
        metavar="BUILD",
        nargs="?",
    )
    options = parser.parse_intermixed_args()
    target = TARGETS[options.target]
    stock = target.installs == FireOs6(build=None)
    if options.build is not None and not stock:
        parser.error(
            message="only stock takes a BUILD: " + ", ".join(sorted(updates.BUILDS))
        )
    ARGUMENTS.build = options.build or (updates.DEFAULT_BUILD if stock else "")
    ARGUMENTS.target = target
    ARGUMENTS.verbose = options.verbose
    for tool in ("adb", "fastboot"):
        if not shutil.which(cmd=tool):
            raise FatalError(
                message=tool + " not found: install Android platform-tools"
            )
    check_user()
    if not options.no_update_check:
        check_for_update()
    check_adb()
    move_old_caches()
    SESSION.short = options.short
    if options.report:
        report()
        return
    if options.write_test:
        write_test()
        return
    check_target(target=target)
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


if __name__ == "__main__":
    main()
