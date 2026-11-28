# CLAUDE.md

firebreak changes the firmware on three Echoes over USB: the Echo Dot (2nd
Generation) (model RS03QR, codename biscuit), the Echo (2nd Generation)
(radar) and the Echo Dot (3rd Generation) (donut). README.md has how to
install and run it. `docs/unlocking.md` says why each step is there; read the
section for a step **before** you touch it. Most of it was measured on
hardware rather than reasoned out. Its sections are the general process, and
its `Each device` section holds what one device alone does.
`docs/measurements.md` holds the whole-run readings that belong to no one step:
the ring, the timings, and what an Echo's bootrom does. `docs/plugins.md`
covers the plugin API: devices, unlocks and their plans.
`docs/troubleshooting.md` holds the user-facing fixes the README left out.

## Commands

```sh
uvx --with tox-uv tox            # lint, build, then test, as CI runs them
uvx --with tox-uv tox -e lint    # pre-commit-hooks, CodeSorter, markdownlint, ruff, toml-sort
uvx --with tox-uv tox -e build   # dist/: wheel and sdist
uvx --with tox-uv tox -e build,test    # pytest and coverage on Python 3.12, or on $TEST_PYTHON
```

## Rules

- Python 3.12 or later, which uvx downloads where none is installed. There
  are three dependencies, each pinned exactly: pyserial, which the emOS probe
  and the bootrom step open a port with, pyusb, which a donut's bootrom is
  driven over because a serial port cannot reach it, and update_checker,
  which tells a run that PyPI has a newer firebreak. One extra, `brotli`, is
  pinned the same way and installs only on request: it reads the brotli
  `system` and `vendor` data athena's and theia's OTAs ship, which no route
  needs. Everything else is the standard library. Users run it
  with `uvx firebreak@latest` from PyPI, or
  `uvx 'firebreak[brotli]@latest'` to survey those two.
- A release is a `v` tag matching `__version__` in `firebreak/__init__.py`,
  which hatchling also reads for the package. `release.yml` publishes the
  wheel to PyPI by trusted publishing and attaches the sdist and wheel to a
  GitHub release. Each release adds its dated section to `CHANGELOG.md` first.
- Every module but `__main__.py` keeps 90% line coverage, each on its own.
  `test` fails a module below that. CI puts the report in the job summary
  and the HTML in a `coverage` artifact. The tests build their own payloads, boot
  images and tables, and fake adb, pyserial and amonet; none needs a Dot or a
  download.
- The code carries no explanatory comments. The why goes in `docs/unlocking.md`,
  on the section that covers the step. `# ruff: ignore[...]` lines stay.
- Nothing here proves a change but a run on a Dot. Each target has a different
  starting state, and a bug in one route does not show on another.
- Trust `adb shell`'s exit status only in v2.0.0's TWRP and TWRP 3.7.0_9-bboe2;
  elsewhere it can exit 0 whatever happened. It merges the device's stderr into
  stdout, and can cut the tail of the output. A read that decides something ends
  with a marker of its own, at the **end**, and the check requires it. A cut
  md5 is shorter than 32 characters, but the md5 of a read that returned
  nothing is whole, so a hash of `dd`'s output also needs `dd`'s record count.
- The by-name nodes for the bootloader partitions can be RAM decoys in TWRP.
  Write and read back through `/dev/block/mmcblk0pN`.
- An image written with `dd` leaves the partition's old bytes past its end.
  Compare a partition against an image only over the image's exact length.
