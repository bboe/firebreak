# CLAUDE.md

firebreak changes the firmware on an Echo Dot (2nd Generation) (model RS03QR,
codename biscuit) over USB. README.md has the targets and how to run it.
`docs/rooting.md` says why each step is there; read the section for a step
**before** you touch it. Most of it was measured on hardware rather than
reasoned out.

## Commands

```sh
uvx --with tox-uv tox            # lint, build, then floor, as CI runs them
uvx --with tox-uv tox -e lint    # pre-commit-hooks, CodeSorter, markdownlint, ruff, toml-sort
uvx --with tox-uv tox -e build   # dist/: wheel and sdist; build/firebreak.pyz
uvx --with tox-uv tox -e build,floor   # macOS only: pytest and coverage on Apple's 3.9.6
```

## Rules

- Python 3.9 or later. pyserial is the one dependency, pinned to the version a
  pyz run downloads; everything else is the standard library. Users run it with
  `uvx` from this repository until the first release, which adds `firebreak.pyz`
  and the PyPI wheel.
- A release is a `v` tag matching `version` in `pyproject.toml`. `release.yml`
  publishes the wheel to PyPI by trusted publishing and attaches the pyz to a
  GitHub release.
- The floor is Apple's `/usr/bin/python3`, 3.9.6, not the newest 3.9. Later 3.9
  releases added APIs it lacks. `tests/test_python_floor.py` fails on any
  import, or any attribute reached through a module's name, that 3.9.6 lacks,
  and on `filter=` to the extract calls. It cannot see methods on objects or
  other keyword arguments. It runs on macOS, so a Windows-only name fails it
  even behind a platform check. CI runs it on a macOS runner.
- Every module but `__main__.py` keeps 90% line coverage, each on its own.
  `floor` fails a module below that. CI puts the report in the job summary
  and the HTML in a `coverage` artifact. The tests build their own payloads, boot
  images and tables, and fake adb, pyserial and amonet; none needs a Dot or a
  download.
- The code carries no explanatory comments. The why goes in `docs/rooting.md`,
  on the section that covers the step. `# ruff: ignore[...]` lines stay.
- Nothing here proves a change but a run on a Dot. Each target has a different
  starting state, and a bug in one route does not show on another.
- Trust `adb shell`'s exit status only in v2.0.0's TWRP and TWRP 3.7.0_9-bboe2;
  elsewhere it can exit 0 whatever happened. It merges the device's stderr into
  stdout, and can cut the tail of the output. A read that decides something ends
  with a marker of its own, at the **end**, and the check requires it. An md5
  needs none: a cut digest is shorter than 32 characters.
- The by-name nodes for the bootloader partitions can be RAM decoys in TWRP.
  Write and read back through `/dev/block/mmcblk0pN`.
- An image written with `dd` leaves the partition's old bytes past its end.
  Compare a partition against an image only over the image's exact length.
