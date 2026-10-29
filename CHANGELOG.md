# Changelog

This project adheres to [Semantic Versioning](https://semver.org).

## Unreleased

### Changed

- `unlock fireos6` roots the Fire OS 6 build already installed, with no wipe
  and no OTA install, so a device set up in the Alexa app keeps its Wi-Fi and
  Alexa setup. `--factory-reset` erases userdata and installs the target's
  build in both slots, which is what the target did before. A build firebreak
  does not know stops the run with nothing written.
- `stock 5.5.0.3` holds the Dot in its bootrom at the end, which the next run
  picks up with no button held. That restore writes the preloader from the
  bootrom, because the Dot's anti-rollback bars the old preloader until the
  RPMB is zeroed, so no kernel is left to ask a stock LK for fastboot. A power
  cycle starts stock 5.5.0.3 instead. `--end-in-fireos` starts Fire OS 5.
- A run that resumes through the bootrom writes amonet v2.0.1's chain, where
  every target wrote v1.1.0's before. `unlock fireos5` still writes v1.1.0's,
  because only that bootloader starts the 64-bit TWRP that target needs.
- amonet v2's fastboot writes that unlock's TWRP before it restarts the
  device, so a `recovery` that holds no TWRP still reaches one. From there
  `unlock fireos5` continues from v2's TWRP, where the bootloader is already
  amonet's, instead of erasing boot0 to reach the bootrom.
- `stock [BUILD]` leaves the device in fastboot at the end, so the next run
  needs no button held. `--end-in-fireos` starts the Fire OS it now holds
  instead, which is what a restore did before. `--fastboot` is gone, because
  it asked for what now happens anyway. `stock 5.5.0.3` ends in the bootrom
  over a serial port and then starts Fire OS 5, so it says so before it
  writes.
- `report` and `write-test` say why they stop in the warning color, after a
  blank line, where the reason ran straight on from the readings above it in
  the body color.
- `write-test` names the device it ran on, as `report` does. Its output is
  meant to be pasted into a support channel, and it said neither the model nor
  the USB ids. It also called the device `Echo` where it had no name to use.
- `report` and `write-test` ask for their output only if you want help, where
  they read as though every run belonged in the support channel. Either one
  also reads an Echo for its own sake.
- Six lines a run can print about an Echo (2nd Generation) said amonet v2,
  which is the Echo Dot's: that Echo has only amonet-radar v1.0.0. They name
  no version now. The ones left naming one are on paths only an Echo Dot
  reaches.
- An Echo (2nd Generation) reached through its bootrom is given TWRP. The
  bootrom route stops its plan at the reboot, before the plan's own write of
  `recovery`, and the step that writes it afterwards only did so for a
  bootloader whose build description the unlock names. radar's unlock names
  none, because kaeru reports the stock one, so nothing wrote TWRP and the run
  waited for a recovery that was never there.
- A bootrom step that refuses an Echo names the one it expected, where it
  said the step supports only the Echo Dot however it was run, and it now
  says to name the Echo with `--device`.
- `report` reads the Fire OS 5 system image of the Echo in front of it, says
  there is none, or says it cannot tell which Echo this is. It read the Echo
  Dot's whichever Echo it ran on, so on an Echo (2nd Generation) it printed
  another model's image, and only when this computer happened to hold one.
- `write-test` keeps its reading of the Echo's `dd` in the same column as
  every other reading, where naming the model there ran past the column and
  left the value hanging.
- Neither Echo (2nd Generation) target asks for `--run-on-unproven-path` any
  more. Both have run on one, and the risk that kept them behind the flag was
  a failure between the boot0 erase and the preloader write, which is now
  recoverable over USB rather than by opening the Echo.
- An Echo (2nd Generation) whose boot0 is erased is picked up from its
  bootrom, where the step refused any device but the Echo Dot. A restore
  clears boot0 before it writes the preloader back, so a run that failed in
  between left an Echo this could not reach. amonet-radar's chain was already
  the one to write there; only the choice of it was missing.
- `report` and `write-test` label their long steps by name alone, where each
  carried a `[ 1/ ?]` that never resolved. Neither follows a plan, so there is
  no count to fill in.
- A run waiting for a rooted Fire OS 6 to come back says to unplug the Echo's
  power cable and plug it back in, where it waited without a word. The Echo
  has shown nothing on USB after boot-root on every Echo (2nd Generation) run
  here, and amonet's own guide says the same.
- No state a run prints names an amonet version, because a version is only
  unique to one Echo: the Echo Dot's chains are amonet v1.1.0 and v2, and an
  Echo (2nd Generation) has neither. `amonet-v2-booted`, `amonet-v2-fastboot`
  and `amonet-v2-twrp` drop a version nothing reads, becoming `amonet-booted`,
  `amonet-fastboot` and `amonet-twrp`. The four `amonet-v1.1.0` states become
  `amonet-fireos5`, which is the chain they are on rather than one Echo's
  release of it. `amonet-v2-twrp-v1.1.0-table` becomes
  `amonet-twrp-boot-moved`, after the partition layout the probe actually
  reads.
- A run takes the earlier amonet it writes from the Echo in front of it. The
  downgrade and the probe read the Echo Dot's bootloader, TWRP and archive
  whatever Echo was plugged in, which was right only because no other Echo
  reports that bootloader. An Echo that has no such chain, which is every one
  but the Echo Dot, now reads the states above and reaches none of the Fire
  OS 5 ones.
- A run on an Echo (2nd Generation) takes the bootrom payload from that Echo's
  own archive, where it fetched a 73 MB Echo Dot zip for the one file. The
  payload in both is the same 20060 bytes, byte for byte.
- Ten messages say a run `continues` where they said it `goes on`, which
  ASD-STE100 discourages as a phrasal verb. The style this project writes in
  approves `continue`, and one of the ten already said it.

## 0.9.0 - 2026-10-25

### Added

- `stock 8344` returns a Dot to the newest build Amazon ships for it. It
  carries the same bootloader as 8338, `2c3569d-20260617_045829`, which the
  fastbrick already has a payload for. `docs/devices.md` now records what
  both builds hold.
- `stock --no-wait` starts the writes at once, without the 10 seconds that
  Ctrl-C cancels in. A run that is one of many does not need them. Only
  `stock` has that wait, so every other command refuses the flag, as they
  refuse the other flags they have no use for. It says `Starting now.`
  without the spaces that erase a countdown it never printed.
- `unlock fireos6` roots an Echo (2nd Generation) with amonet-radar v1.0.0, on
  Fire OS 6 6436 with `boot-root.zip`'s root adb. It is that device's default
  target, so a run that names only the device unlocks it, and a run that names
  nothing waits for the Echo to say which one it is. `--short` keeps taking the
  Echo Dot (2nd Generation), the one device with a bootrom route here. The one
  run that reached root on an Echo needed it power-cycled by hand at its first
  boot, so the target is refused without `--run-on-unproven-path`.
- `stock` returns an Echo (2nd Generation) to Fire OS 6436, the one build
  Amazon ships for it.
- `report` names fastboot's version beside adb's. Which commands a fastboot has
  depends on its version, so a refusal the report shows can be read.
- `--run-on-unproven-path` goes on with a target whose route is not proven on
  the device it is for. Both of an Echo (2nd Generation)'s targets are such
  targets, and are refused without it.
- A run waiting for TWRP that watches the Echo restart over and over says that
  a USB port which cannot power TWRP has done that, and how to tell: a USB wall
  charger with the + button held reaches white if TWRP can run. The run waited
  on that without a word before. It still does not stop: nothing times out
  while the Echo keeps coming and going.

### Changed

- The reminder that a run is waiting for fastboot says a green ring on a stock
  Echo and every color turning on amonet's, where it said only green. Both
  reach that reminder. A `report` waiting for the same thing says it in one
  line it repaints, which has no room for either ring, so that line names
  neither.
- No step label is wider than the room the progress line gives it, so the tick
  and the times after it no longer slide right on some steps. Naming the device
  in messages had made three of them too wide.
- What a run reports as done stands apart from the step it followed: the lines
  that say an image matches the manifest are their own block now, where they
  ran on from the step above them.
- A message names the device it is about, by the name help already gives it:
  a run on an Echo (2nd Generation) says so where every run said Dot. Help,
  and the notices that print before a run knows which device is plugged in,
  say Echo, which fits any of them.
- The fastbrick takes the payload map and the archive of the device's own
  unlock, and checks the product fastboot reports against the device the
  target is for. An Echo (2nd Generation) on Fire OS 5.5.5.4 takes
  amonet-radar's own image for that bootloader.
- A stock build the device has no OTA for is refused before anything is
  written. An Echo Dot's OTAs and an Echo's are different firmware, so the
  build is chosen once the run knows which it has.
- `stock` and `unlock fireos6` start the TWRP of an Echo already unlocked with
  amonet v2 themselves. Both asked for the + button, because the restart
  command that bootloader has was the only one tried. They now ask with the
  same two commands a `report` asks with, and a bootloader that takes neither
  still gets the + button.
- `report` and `write-test` end by saying the Echo stays in TWRP and that `adb
  reboot` leaves TWRP for Fire OS. They said it stays in its recovery and that
  `adb reboot` starts it again, which reads as starting the recovery again. Neither
  goes on in a recovery that is not TWRP, so TWRP is the only one either can be
  left in. A `report` that names the device it found then calls it by that
  name, where it said Echo: its own identification answers for a command that
  has no target.

### Fixed

- `unlock` roots a Dot on Fire OS 6 4310, 4313 or 4315 again. Those builds
  carry the bootloader `41fb3ce-20221007_151724`, and amonet v2.0.1 rebuilt
  the payload that unlocks it for the one bootloader the file is named after,
  so the unlock had flashed a payload that no longer took and left the Dot to
  boot stock. That bootloader now takes its payload from amonet v2.0.0, which
  is downloaded only for such a Dot.
- A read of a Dot's bootloader version that times out stops the unlock. It
  had come back as the same empty string an LK older than Fire OS 5.5.0.3
  answers with, and an empty pair of versions takes the payload built for
  those, so a fastboot that went away mid-unlock could have had that payload
  run on a bootloader nothing read.
- A Dot whose bootloader firebreak has no unlock payload for, and which is no
  older than the newest it does have one for, is refused before anything is
  written, and told its bootrom can still unlock it. Such a Dot was given the
  payload for an older bootloader, which runs on the Dot rather than being
  stored, so it ran code built for different bytes.
- A download that the mirror does not answer falls back after 8 seconds rather
  than 60. A network that drops the packets rather than refusing them stalled a
  run for a minute per download before it opened your browser.
- `report` starts the recovery of a Dot unlocked with amonet v2 from fastboot.
  It asked with a command that bootloader refuses, ignored the refusal, waited
  3 minutes for adb and then said the Dot was most likely in Amazon's recovery,
  though it had never left fastboot. It now falls back to a command that
  bootloader does take, and asks for the + button only when no command reaches
  the recovery, with what fastboot answered to each.

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
