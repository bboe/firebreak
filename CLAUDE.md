# CLAUDE.md

`dot_firmware.py` changes the firmware on an Echo Dot (2nd Generation) (model RS03QR, codename biscuit) over USB. README.md has the targets and how to run it. `docs/rooting.md` says why each step is there; read the section for a step **before** you touch it. Most of it was measured on hardware rather than reasoned out.

## Commands

```sh
/usr/bin/python3 tests/python_floor.py   # macOS only: the script against Apple's 3.9.6
/usr/bin/python3 dot_firmware.py --help
pre-commit run --all-files    # CodeSorter and ruff, as CI runs them
```

## Rules

- Python 3.9 or later, standard library only. Users run one downloaded file.
- The floor is Apple's `/usr/bin/python3`, 3.9.6, not the newest 3.9. Later 3.9 releases added APIs it lacks. `tests/python_floor.py` fails on any import, or any attribute reached through a module's name, that 3.9.6 lacks, and on `filter=` to the extract calls. It cannot see methods on objects or other keyword arguments. It runs on macOS, so a Windows-only name fails it even behind a platform check. CI runs it on a macOS runner.
- The code carries no explanatory comments. The why goes in `docs/rooting.md`, on the section that covers the step. `# ruff: ignore[...]` lines stay.
- Nothing here proves a change but a run on a Dot. Each target has a different starting state, and a bug in one route does not show on another.
- Trust `adb shell`'s exit status only in v2.0.0's TWRP and TWRP 3.7.0_9-bboe2; elsewhere it can exit 0 whatever happened. It merges the device's stderr into stdout, and can cut the tail of the output. A read that decides something ends with a marker of its own, at the **end**, and the check requires it. An md5 needs none: a cut digest is shorter than 32 characters.
- The by-name nodes for the bootloader partitions can be RAM decoys in TWRP. Write and read back through `/dev/block/mmcblk0pN`.
- An image written with `dd` leaves the partition's old bytes past its end. Compare a partition against an image only over the image's exact length.
