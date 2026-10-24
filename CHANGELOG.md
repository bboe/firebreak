# Changelog

This project adheres to [Semantic Versioning](https://semver.org).

## Unreleased

### Fixed

- A download that the mirror does not answer falls back after 8 seconds rather
  than 60. A network that drops the packets rather than refusing them stalled a
  run for a minute per download before it opened your browser.

## 0.8.0 - 2026-10-24

### Changed

- Unlocking a stock Dot downloads everything it needs unattended. A run opens
  your browser for a download only when the unattended one fails, and checks
  the pinned hash either way.
- Unlocking is its own command: `firebreak unlock [TARGET]`, where TARGET is
  `fireos5` or `fireos6`. Each takes the newest amonet firebreak supports for
  that Fire OS, so a target no longer names a version. `unlock` with no target
  takes `fireos6`.
- `firebreak` with no target no longer unlocks the Dot. It warns which command
  replaced the old default and prints the help. The warning goes away in
  firebreak 1.0.
- `amonet-biscuit-v1.1.0`, `amonet-biscuit-v1.1.0-bboe` and
  `amonet-biscuit-v2.0.0` still work and name the command to use instead. They
  go away in firebreak 1.0. `amonet-biscuit-v1.1.0` installs TWRP
  3.7.0_9-bboe2 rather than amonet's own TWRP 3.2.3, and
  `amonet-biscuit-v2.0.0` writes amonet v2.0.1; both say so.
- amonet v2.0.1 replaces v2.0.0. v2.0.1's kaeru boots the active slot, where
  v2.0.0's boots `boot_a` whatever slot is active.
- A Dot on 8338's bootloader is unlocked by amonet v2.0.1's own fastbrick
  payload for it. 0.7.0 patched that bootloader's own `lk.img` instead, which
  also erased `boot0` to reach the bootrom; nothing erases `boot0` before the
  exploit runs now.
- The `amonet-v2.0.0-*` states `--verbose` prints are now `amonet-v2-*`, and
  the messages that named amonet v2.0.0's chain name amonet v2. Both releases
  write the same `lk.bin`, `preloader.img`, `twrp.img` and `tz.img`, so the
  state a Dot reaches does not say which one unlocked it.

### Removed

- No target installs amonet's own TWRP 3.2.3. A Dot already running it reaches
  `fireos5` with one write to `recovery`, and needs no stock restore.

### Fixed

- `unlock` on an Echo (2nd Generation) stopped with a download error rather
  than unlocking it.

## 0.7.0 - 2026-10-21

### Added

- `stock 8338` installs Fire OS 6 8338. It is not the default; `stock` with no
  build still installs 8149.
- A Dot on a bootloader that no fastbrick image unlocks is now unlocked by the
  bootloader's own code. The run builds a payload from that build's `lk.img`,
  turns off the lock check, and erases `boot0` to reach the bootrom. Before,
  every flash returned at once and the run stopped with `the unlock did not
  start`. 8338 is the first such build.
- `stock [BUILD] --fastboot` leaves the Dot in fastboot at the end, so the next
  run needs no button held.

## 0.6.1 - 2026-10-14

### Fixed

- A run on a Python from the Microsoft Store stops at once and says how to
  use another Python: `uvx --managed-python firebreak@latest`, or for
  `firebreak.pyz`, python.org's Python or uv's. Before, the unlock tried its
  flash 10 times and stopped with `the unlock did not start`: the Store's
  Python keeps firebreak's files where fastboot cannot see them.
- A root that ends on Fire OS 5 no longer stops with `... is not hidden`
  when the updater cannot be hidden in the first seconds after boot. It
  tries again for up to a minute.

## 0.6.0 - 2026-10-14

### Added

- `--write-test --short` tests the eMMC and USB through the bootrom, for a
  Dot that shows no light. It tells an eMMC that refuses writes from bytes
  that do not arrive.

### Fixed

- A run with no cache directory stopped with `FileNotFoundError` before it
  found the Dot. It now creates the directory.

## 0.5.0 - 2026-10-14

### Added

- `firebreak survey OTA` prints what docs/devices.md lists for an Amazon OTA
  zip: its build descriptions, anti-rollback versions, TEE hashes and
  partition hashes. It needs no Dot.
- `stock` returns a Dot to stock Fire OS 5.5.0.3, 5.5.3.1, 5.5.4.6, 5.5.4.9,
  5.5.5.0 or 5.5.5.4.

### Changed

- A run fetches each OTA from Amazon's CDN by a pinned URL. It no longer asks
  ftvdb.
- The step counter no longer jumps when a run starts from stock Fire OS 5
  fastboot.
- A download's progress label keeps the end of the file name, where the build
  is.

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
