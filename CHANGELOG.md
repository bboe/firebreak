# Changelog

This project adheres to [Semantic Versioning](https://semver.org).

## Unreleased

### Added

- `firebreak survey OTA` prints what docs/devices.md lists for an Amazon OTA
  zip: its build descriptions, anti-rollback versions, TEE hashes and
  partition hashes. It needs no Dot.
- `stock` returns a Dot to stock Fire OS 5.5.3.1, 5.5.4.6, 5.5.4.9, 5.5.5.0 or
  5.5.5.4.

## 0.4.0 - 2026-10-13

### Added

- `--credits` prints who did the work firebreak builds on, as the README's
  new Credits section does.
- `--version` prints firebreak's version.

### Changed

- A run downloads only what the route from the Dot's state to the target
  needs, and nothing before it sees the Dot. A Dot that waits for the
  fastboot gesture still downloads during it. A device plugged in after the
  run started is refused before the route's downloads.

## 0.3.0 - 2026-10-13

### Added

- A run names the device before it starts, and refuses a target made for
  another device before it downloads anything. In fastboot it asks the
  device's product; elsewhere it reads the USB product string, which needs no
  adb authorization.
- `--report` names the device and lists its USB devices, with the first 4
  characters of each serial number. In fastboot it also prints the
  anti-rollback versions.
- `--report` gives the eMMC chip's manufacture date and the sizes of its two
  boot areas, which differ between the chips Dots ship with.

### Fixed

- `--short` and a resumed run check that the Dot's bootloader names it an
  Echo Dot (2nd Generation) before the bootrom writes. An Echo (2nd
  Generation) that showed no light would have been given the Dot's preloader
  and bootloader.
- A run no longer erases boot0 when amonet's fastboot is not a Dot's. An
  unlocked Echo (2nd Generation) in amonet's fastboot read as an unlocked
  Dot, and the run would have written the Dot's preloader and bootloader to
  it.
- `stock` works on a Dot whose boot0 is larger than the stock preloader. It
  stopped with `preloader.img is not the size of boot0` on a Dot with a 4 MiB
  boot0.

## 0.2.0 - 2026-10-12

### Added

- `stock 8149`: Fire OS 6574.1 from 2026-09-29.
- The notice of a newer firebreak says how to upgrade, on a line of its own:
  the latest release's `firebreak.pyz` for a pyz, and `uvx firebreak@latest`
  for any other run.

### Changed

- `stock` without a build installs 8149. Before, it stopped with an error.
- The notice of a newer firebreak goes to stdout with the rest of the run,
  not to stderr.
- `--verbose`, `--report` and `--write-test` name a rooted Fire OS 5 by its
  unlock: `amonet-v1.1.0-booted` and `amonet-v1.1.0-bboe-booted`, not
  `rooted-amonet-v1.1.0` and `rooted-amonet-v1.1.0-bboe`.

## 0.1.0 - 2026-10-11

First release.

### Added

- Takes an Echo Dot (2nd Generation) over USB, from macOS, Linux or Windows,
  to one of four targets, from stock or from another target:
  - `amonet-biscuit-v1.1.0-bboe`, the default: rooted Fire OS 5.5.5.4 on
    amonet v1.1.0, with TWRP 3.7.0_9-bboe2.
  - `amonet-biscuit-v1.1.0`: the same, with amonet v1.1.0's TWRP 3.2.3.
  - `amonet-biscuit-v2.0.0`: rooted Fire OS 6 8146 on amonet v2.0.0.
  - `stock BUILD`: back to stock Fire OS 6 at build 4315, 4405, 5041, 6302,
    8138, 8142 or 8146, with the Dot erased.
- Picks up a stopped run where it left off.
- `--short` reaches the bootrom for a Dot that shows no light.
- `--report` prints what a support request needs.
- `--write-test` tells a failing eMMC from a failing USB cable.
- A run says when PyPI has a newer firebreak. `--no-update-check` skips it.
- Runs with `uvx firebreak@latest`, or as `firebreak.pyz` from a GitHub release
  on Python 3.9 or later.
