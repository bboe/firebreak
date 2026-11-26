# Changelog

This project adheres to [Semantic Versioning](https://semver.org).

## Unreleased

### Added

- `docs/devices.md` covers Fire OS 6575.1 build 8888, the one build Amazon
  began offering on 2026-11-25 to 17 of the Echoes here at once, read from all
  17 OTAs before ftvdb listed them. Only `boot` and `system` change: every LK,
  u-boot, TEE, `scp` and `mcupm` image matches the build before, and six
  devices ship a rebuilt preloader that keeps its size, its description and
  its anti-rollback version, so only the CSV tells those builds apart. Each of
  the 17 partition CSVs carries the build's rows.
- `report` decodes the eMMC's EXT_CSD revision and its wear: the pre-EOL
  state and both life estimates, as a range of rated life used. On a card
  older than eMMC 5.0 it labels those bytes as reserved, because only eMMC 5.0
  defined them.

### Changed

- A block read through amonet's payload, on a Dot or an Echo (2nd
  Generation), that gets back only the payload's own flush word says
  "amonet's payload answered, but the eMMC sent no data". A write that gets
  nothing back says "amonet's payload sent no acknowledgement". Before, each
  gave only a count of bytes. `docs/troubleshooting.md` says what to do next.
- `bootrom`'s prompt says that only amonet's payload can write a preloader
  back, so an eMMC that payload cannot reach keeps the Echo in its bootrom.

## 1.5.0 - 2026-11-25

### Added

- `survey` reads a block OTA whose bootloader is `images/u-boot.bin` and a
  signed copy of it, with no LK, preloader or TEE, as cypress's, hoya's,
  rhodes' and sycamore's are, and gives `odm`, `product`, `logo` and `vbmeta`
  rows of their own. It takes the codename from `ro.product.device` without
  `_ftv`, which hoya's later OTAs add, as it already did for `_puffin`.
  `docs/devices.md` covers all four, read from every OTA ftvdb lists, with a
  partition CSV each, so every Echo ftvdb lists is now covered.
- `docs/devices.md` covers crown's 8150, 8151, 8848 and 8851, the four OTAs
  ftvdb has gained since crown was read. 8848 and 8851 are Fire OS 6575.1 and
  bring a second LK, TEE and preloader.
- `survey` reads a block OTA whose `system` and `vendor` data is brotli
  compressed and whose LK and TEE are `images/lk.img` and `images/tee.img`, as
  athena's and theia's are. It takes the build properties from
  `system/build.prop` where an OTA carries no `target.build.prop`, and gives
  `vendor` a row of its own. Reading one needs brotli, which no route needs, so
  it installs as the `firebreak[brotli]` extra and an OTA that wants it says so.
  `docs/devices.md` covers athena and theia, read from every OTA ftvdb lists,
  with a partition CSV each.
- `docs/devices.md` opens with an index of all 39 devices: codename, the
  device it is, and the model its CSV rows carry.
- `survey` reads a Vega `.swu`, the container the Echo Hub, the Echo Spot of
  the 2nd generation, the Echo Show 5 of the 3rd, the Echo Dot Max, the Echo
  Show 11, the Echo Show 8 of the 4th and the Echo Studio of the 2nd ship
  instead of an Android OTA zip. It reads the CPIO archive's headers and the
  `sw-description` manifest inside it, and prints the build number, its build
  time, the device and a CSV row for every image the manifest names.
  `docs/devices.md` covers all seven, read from every OTA ftvdb lists, with a
  partition CSV each.
- `survey` reads a block OTA that carries `images/bootloader` and
  `images/bootloader_prod` in place of an LK, a preloader and a TEE, as the
  Echo Show of the 1st and 2nd generations, knight and bishop, do. It gives
  the two images their own CSV rows, and reports neither build descriptions,
  anti-rollback versions nor a TEE, which those OTAs do not carry.
  `docs/devices.md` covers both, read from every OTA ftvdb lists, with a
  partition CSV each.
- `survey` reads a block OTA that names `images/preloader.bin`, as the Echo
  Spot (1st Generation), rook, does. `docs/devices.md` covers rook, read from
  all 5 OTAs ftvdb lists, with `rook-partitions.csv`. Its OTA ships the
  preloader alone, with boot0's headers beside it, where every other block OTA
  here carries boot0 whole.
- `docs/devices.md` covers eight more devices `survey` already read: checkers
  and cronos, the Echo Show 5 of the 1st and 2nd generations, croissant, the
  Echo Flex, cupcake, the Echo Input, octave, the Echo Studio, pablo, the Echo
  Sub, and sapphire and kyanite, the Echo Link and Echo Link Amp. Each is read
  from every OTA ftvdb lists, with a partition CSV each, and a section gathers
  the eleven devices whose LK carries commit `6f7225e`.
- `survey` reads an OTA whose payload names a `uboot` partition, with four
  `brhgptlk` copies in place of a preloader or an `lk`, as the Echo and Echo
  Dot of the 4th generation and later do. For those it reports the `timestamp`
  each FIT image's root node carries, one line each for `uboot`, the TEE,
  `scp` and `mcupm`, in place of the build descriptions and the anti-rollback
  versions, which those images do not hold.
- `docs/devices.md` covers laser, brownie, ganache, cannoli, cheesecake and
  churro — the Echo (4th Generation), the Echo Dot (4th and 5th Generations),
  both Echo Dot with Clock variants and the Echo Pop — each read from every OTA
  ftvdb lists, with a partition CSV each, and a section on what the six have in
  common.
- `survey` reads an OTA whose payload names four `brhgptpl` partitions and no
  `preloader`, as the Echo Dot (3rd Generation) Refresh of 2019, crumpet, does.
  It takes the preloader from inside the first of them, and gives all four
  their own CSV rows.
- `docs/devices.md` covers crumpet, read from all 18 OTAs ftvdb lists, with
  `crumpet-partitions.csv`.
- `docs/devices.md` covers pascal, the Echo (3rd Generation), sonar, the Echo
  Plus (1st Generation), and lidar, the Echo Plus (2nd Generation), each read
  from every OTA ftvdb lists, with a partition CSV each. `survey` already read
  all three.
- `docs/devices.md` covers doebrite, the Echo Dot with Clock (3rd Generation),
  read from all 5 OTAs ftvdb lists, with `doebrite-partitions.csv`. It is built
  as crumpet is, so `survey` already read it.

### Changed

- An Echo whose Fire OS 5 setup cannot move to Fire OS 6, a radar or a Dot
  older than 5.5.5.4, no longer only stops. On a terminal, `unlock` asks
  whether to erase it and continues as `--factory-reset` on `yes`. Otherwise it
  stops and prints the whole command to run with `--factory-reset`.
- A command that firebreak prints for a uvx run includes `--managed-python`
  when the run uses a Python that uv installed. This also applies to the
  upgrade notice. Before, those commands left the option out.
- A build description with no commit before it, which is every crumpet and
  every donut preloader, reports the build timestamp rather than `<none>`. The
  donut table's `pl_build_desc` column holds those timestamps now, and its rows
  split where one covered several preloaders.

## 1.4.5 - 2026-11-20

### Changed

- A failed read of which Echo this is, from its bootrom, ends its step with a
  cross and its time rather than a check mark and `skip`.

## 1.4.4 - 2026-11-19

### Changed

- A run that cannot read the bootloader in an Echo's flash from its bootrom
  says which read failed and why.

## 1.4.3 - 2026-11-17

### Changed

- `short --device radar` says where an Echo (2nd Generation)'s test point is:
  the same passive as an Echo Dot (2nd Generation)'s. Both name it the same
  way, and warn off C52 beside it.
- A fastbrick that does not start points to `short` and the device's XDA
  thread.
- An unlock that roots an Echo ends by crediting the unlock's author, Roger
  Ortiz, with links to support that work and to the unlock's XDA thread.

## 1.4.2 - 2026-11-17

### Changed

- Support moved to `#firebreak-support` in the 0x7E Labs Discord, and asks
  for the failed run's own output as well as `report`'s.

### Fixed

- `unlock` stopped on an Echo (2nd Generation) whose bootloader reports an
  8-digit commit, `ae269a7b-20170719_072038`, saying it could not read the
  version. It now reads a commit of 7 or 8 digits.

## 1.4.1 - 2026-11-16

### Fixed

- `backup` estimated each partition from the speed of a pull alone, so a
  step took 3 to 4 times its estimate. It now uses the rate a whole backup
  measured.
- Two steps of `unlock fireos6`'s move from Fire OS 5 pushed their estimate
  and check mark out of line. They are renamed `waiting for 4315's migration`
  and `waiting for 4315 to reach Alexa`, which also says what each waits for.

## 1.4.0 - 2026-11-16

### Changed

- `unlock fireos6` moves an Echo Dot (2nd Generation) on Fire OS 5.5.5.4 to
  Fire OS 6 and keeps its setup, Wi-Fi and Alexa registration included,
  where it erased it. It takes Amazon's own route: it installs the bridge
  build 4315, starts it once so Amazon's migration moves the setup and 4315
  finishes its own setup online, then installs 8349 over it. Amazon's
  migration leaves out the signing algorithm 8349 needs to reach Alexa, so
  firebreak adds it before 8349 goes on. It asks first, and keeps Amazon's
  updates off at each step.
  Any other Fire OS 5, and an Echo (2nd Generation) on Fire OS 5, stops with
  nothing written; `--factory-reset` erases it as before.
- `unlock` takes `--force`, which answers that question.

### Fixed

- `unlock fireos5` asked for the fastboot gesture when the rooted Fire OS 5 it
  just installed refused this computer's adb key. It now stops with a message,
  as `unlock fireos6` does.

## 1.3.0 - 2026-11-12

### Changed

- `unlock fireos6` installs the target's Fire OS 6 build, 8349 on every
  device, over an older Fire OS 6 and keeps the Echo's userdata, where it
  rooted the build already installed. A rooted Echo on an older build now
  goes to TWRP for it, where `unlock` said it was rooted and stopped. An Echo
  on 8349 is rooted in place as before.
- Progress lines write each step's estimate as `~40s`, with no space, as its
  elapsed time and the total already are. The label column is one character
  wider.
- `stock` and `unlock fireos6 --factory-reset` install Fire OS 6 8349 on an
  Echo Dot (2nd Generation) and an Echo (2nd Generation) when no build is
  named, where they installed 8149. So does `unlock fireos6` on an Echo with
  no Fire OS 6 installed, such as one on Fire OS 5. Amazon's update server
  offers stock 8149 an update to 8349, so a stock Echo left on 8149
  downloads and writes it again by itself.

### Fixed

- `restore` of an Echo Dot (3rd Generation) backup takes the backup's
  device for an unnamed bootrom it reaches at any point in the run. A donut
  whose boot0 a stopped restore cleared cycles through its bootrom, and a
  run that started between two cycles stopped with "firebreak cannot tell
  which Echo this is".

## 1.2.0 - 2026-11-11

### Changed

- `unlock` lets only the computer that runs it into the Echo's adb, over USB
  and Wi-Fi, on Fire OS 5 and 6. A rooted Fire OS 6 Echo previously gave root
  adb to anyone on its network.
- Progress lines right-align each step's estimate against its ✅ and drop the
  parentheses around the estimate and the total. The label column gains the
  4 characters that saves, so the longest label no longer pushes its line
  right.

### Fixed

- `twrp`, and a run that starts from rooted Fire OS 6, reach an Echo Dot (3rd
  Generation)'s TWRP through a `boot-recovery` request in `misc`. `adb reboot
  recovery` there could start Fire OS instead, and `twrp` then rebooted it
  again and again.
- `unlock fireos6` blocks updates on a build with no `otad`, such as the Echo
  Dot (3rd Generation)'s 1895, where it stopped with the active slot not
  blocked. There it disables `update_engine` besides blocking the update
  hosts.
- `unlock fireos6 --factory-reset` erases an Echo that already runs rooted
  Fire OS 6 and installs both slots, where it said the Echo was rooted and
  did nothing.

## 1.1.1 - 2026-11-10

### Fixed

- `unlock fireos6 --factory-reset` on an Echo Dot (3rd Generation) no longer
  stops between its two slot installs, where it booted Fire OS instead of
  TWRP.
- `twrp`, `backup` and `restore` unlock a locked Echo Dot (3rd Generation)
  from its bootrom, where they stopped. `restore` also names one already in
  its bootrom from the backup.
- `unlock fireos6` deletes the zips it pushes to `/sdcard` once installed,
  and pushes `update.zip` once rather than once per slot.

## 1.1.0 - 2026-11-10

### Added

- `unlock fireos6` turns off Amazon's updates. After `boot-root.zip`, it
  disables the `otad` service in each Fire OS 6 slot and points the update
  hosts at `127.0.0.1` in that slot's `/system/etc/hosts`. Fire OS 6 has no
  `pm`, so the updater cannot be hidden as on Fire OS 5. Measured on all
  three, each unlocked from stock on 2026-11-07, a donut on 8349 and a
  biscuit and a radar on 8149: `otad` did not start after a reboot, and the
  update hosts resolved to `127.0.0.1`.
- `backup` copies every partition of an Echo's eMMC, both boot areas and both
  copies of its partition table into a directory, with a `backup.json` that
  says how to put each byte back. A partition that begins with an image from
  an OTA firebreak can download names that image and copies only the rest.
  The partition hash tables moved from `docs/` into the package, so a backup
  can read them.
- `restore` writes a backup back onto the Echo it was read from, byte for
  byte, except the gaps between partitions. It rebuilds and checks every area
  before it writes, and downloads the OTAs the backup names from Amazon.
- `stock` takes 8344 on an Echo Dot (3rd Generation) and 8349 on an Echo Dot
  (2nd Generation). Each writes the same LK, TEE and preloader as a build
  already supported on that device.
- `stock` takes every OTA ftvdb lists: 49 builds for the Echo Dot (2nd
  Generation), 21 for the Echo (2nd Generation) and 26 for the Echo Dot (3rd
  Generation). Each is marked verified once it has been restored to and
  unlocked from on hardware. `stock` asks before it restores any other, and
  `--force` answers for it. Every OTA was
  downloaded, matched against ftvdb's md5 and surveyed, and the partition hash
  tables gained the 17 builds they lacked.
- `firebreak builds` lists every build `stock` takes for each Echo, with its
  Fire OS version. `stock --help` names only each Echo's default build, and
  a build `stock` does not take points to `firebreak builds`.
- Every Echo Dot (2nd Generation) build on ftvdb is verified.
- Every Echo (2nd Generation) build on ftvdb is verified.
- Every Echo Dot (3rd Generation) build on ftvdb is verified.
- `stock 5.5.0.3-1973` installs the second 5.5.0.3 build Amazon shipped for
  the Echo Dot (2nd Generation), which added the `COMPUTER` wake word.
  `5.5.0.3` is still the first, build 1969.
- An Echo Dot (3rd Generation) on 4655's LK, `0db8914-20221005_072344`, is
  recognised.

### Changed

- A Fire OS 5 root, like the new Fire OS 6 step, blocks
  `d1s31zyz7dcc2d.cloudfront.net`, `prod.ota-cloudfront.net` and
  `d1s31zyz7dcc2d.cloudfront.prod.ota-cloudfront.net` too, where Amazon
  serves Echo OTAs. The last is the host in the download URLs Amazon's
  check-in hands out today. A Fire OS 5 root no longer lists Fire TV's
  `amzdigital-a.akamaihd.com`.
- `--help` names all three Echoes, and its description is shorter.
- `--credits` ends its help in "and exit", as `--help` and `--version` do.
- Support moved to `#echo-support` in the
  [0x7E Labs Discord](https://discord.gg/huE5XhWbsz): the README, `report`
  and a failed run's advice name it.
- `stock --force` starts the writes without the 10-second countdown, as
  `--no-wait` did.

### Deprecated

- `--no-wait` is a hidden alias for `--force`, and prints a warning. It goes
  away in 2.0.

### Fixed

- A Fire OS 5 root blocks `amzdigitaldownloads.edgesuite.net`, where a 2016
  Dot downloaded its OTA. The hosts file named
  `amzndigitaldownloads.edgesuite.net`, which does not exist.
- `stock` tries a partition write up to 3 times, waiting for the Echo to
  reconnect between tries, where one lost reply from adb stopped the run.
- `stock 1895` on an Echo Dot (3rd Generation) ends once the Echo reboots,
  because that build starts with adb off and the run waited for it forever.
- `stock` ends once its Echo has shown nothing on USB for 5 minutes after
  the reboot, where it waited 10 and then failed. Stock turns adb off
  during its first boot, so an Echo power-cycled then never shows again.
- An unlock that stops on the installed Fire OS 6 build says that Fire OS and
  its data are as they were, where it said the Echo was not modified after
  writing its bootloaders and TWRP.
- An Echo Dot (3rd Generation) unlock that starts with the Echo already in
  its bootrom says why before sudo asks for a password, where it asked with
  no word of explanation.

## 1.0.0 - 2026-11-05

### Added

- An Echo Dot (3rd Generation) unlocks on Windows. Its bootrom is reached
  through UsbDk, which takes the device from MediaTek's serial driver while
  libusb holds it, so the bootrom keeps its COM port for naming the Echo. The
  README's Windows section installs UsbDk and libusb. Measured on Windows 11
  on 2026-11-05: stock 8349 to rooted 8349 in 13 steps.
- A run names an Echo Dot (3rd Generation) rather than calling it an unknown
  device, and `report` prints it. donut declares the unlock kamakiri-donut
  v1.0.0 and a `fireos6` target, whose route runs the unlock through a step of
  its own and carries on from the TWRP it leaves. A donut in fastboot is named
  by its `product`, and one in its bootrom by the hardware code that bootrom
  reports, read inside the single handshake a bootrom gives per power-on. So
  `firebreak unlock fireos6` resolves a donut without being told which Echo it
  is. The whole route has run on a donut, on 2026-11-03 from a once-unlocked
  Echo and on 2026-11-04 from one genuinely stock and locked, both of them to
  rooted Fire OS 6 8349 in 12 steps, and with `--factory-reset` in 14 steps
  and 7m 14s. It is the first unlock that
  is not amonet's, and the first whose entry a serial port cannot carry: a USB
  control transfer sets its payload running. So `pyusb` is pinned as a third
  dependency.
- `firebreak stock` takes an Echo Dot (3rd Generation) back to Amazon's Fire
  OS 6 8349 and locks it again. Its OTA carries every image the restore needs,
  and the one it reads off the Echo matches the stock partition byte for byte.
  A device whose unlock leaves `misc` alone is written no `misc` image, since
  the block written otherwise is amonet's and that offset holds slot state on
  a donut. The restore ends in the firmware rather than fastboot, because the
  command that reaches a donut's fastboot belongs to the bootloader the
  restore has just written over. Measured twice: 15 steps in 5m 02s from TWRP,
  and 16 in 5m 26s from rooted Fire OS, both to stock 8349.
- `firebreak fastboot` reaches an Echo whose Android does not take `adb reboot
  bootloader`. Such a device names the bootloader command that does reach its
  fastboot, and a run writes that command into `misc` and reboots. Measured on
  a donut, where the old way rebooted in a loop and left `misc` untouched: the
  Echo now comes up in fastboot in eleven seconds, and the command clears
  itself, so nothing is left to undo.
- libusb is never bundled, because it is a native library rather than a wheel.
  A run that needs it and has not got it says so and names `brew install
  libusb`, in place of pyusb's own `No backend available`.

- An Echo Dot (3rd Generation) unlocks from Linux, with no `sudo`. A Linux
  kernel refuses the trigger that macOS sends, so every host but macOS starts
  stage 1 with kamakiri-donut's own sequence: an overflowed `SET_LINE_CODING`
  on interface 0, then command `0xDA`. The run detaches `cdc_acm` from that
  interface first. On 2026-11-04 it ran from the bootrom to rooted Fire OS 6
  8349 in 13 steps and 3m 22s, and from genuinely stock in 12 steps and
  3m 07s.
- `firebreak reboot` starts the Echo's firmware, as an ordinary power-on
  does. It reboots a TWRP or a fastboot, leaves an Echo that already runs its
  firmware alone, and says to power cycle one held in its bootrom. It writes
  nothing. An Echo that shows nothing on USB for 2 minutes is said to be
  possibly running with adb off, as stock Fire OS is once registered.

### Changed

- README opens by crediting Rortiz2, whose unlocks firebreak runs, and links
  their XDA thread for each of the three Echoes. Credits and `--credits` name
  amonet-radar and kamakiri-donut as theirs too.
- README, the package description and the contributor notes name all three
  Echoes firebreak supports, not only the Echo Dot (2nd Generation), and the
  README's target table gives an Echo Dot (3rd Generation)'s results. README
  also says what each host needs that it left out: `brew install libusb` on
  macOS for a donut's bootrom, and on Linux the udev rules and `plugdev` group
  that let a user run firebreak without `sudo`, the same commands a run prints
  when it cannot open the Echo.
- A donut's bootrom that Linux denies libusb, by `EACCES`, prints
  those udev commands, as every other refused USB open does. Before, it
  pointed at a README section that held no rules. A busy interface or a
  bootrom gone from USB names its own error and no udev rules.
- A run that stops while boot0 holds no preloader says what to do if the
  next run fails the same way: unplug the Echo, run firebreak again, then plug
  it into another USB port, best a USB 3 port on the computer itself. A TWRP
  that never comes up, keeps restarting, or never finishes starting gives
  the same retry. On Windows 11 on 2026-11-05, two Dots dropped off a USB 2
  port during TWRP writes, and one then restored stock and unlocked from a
  USB 3 port on the same PC.
- The states every unlocked device shares are renamed `unlocked-booted`,
  `unlocked-fastboot` and `unlocked-twrp`, from `amonet-booted`,
  `amonet-fastboot` and `amonet-twrp`. A donut never runs amonet, yet
  `--verbose` and `firebreak reboot` named it there. The Fire OS 5 states and
  `amonet-twrp-boot-moved` keep their names. What a run prints says
  `rooted Fire OS 6` for the booted one, as it says `unlocked fastboot` and
  `TWRP` for the other two.
- No error message calls an unlock a payload any more, which is this project's
  word and not an owner's. Only an OTA's own `payload.bin` keeps the name,
  because that is what Amazon calls the file. The refusal for a bootloader
  firebreak cannot unlock says
  what happened first and why second: `firebreak cannot unlock this Echo (2nd
  Generation). LK <lk_build_desc> is newer than any firebreak knows how to
  unlock.`, in place of a sentence that led with the bootloader it had never
  heard of and ended in what it did not do. On a device whose test point is
  known it says the fastboot route is what cannot unlock it, and that
  `firebreak short` holds its bootrom instead, because the bootrom route takes
  any bootloader. A bootrom stage that does not
  start, and a device the unlock refuses, both say "the unlock" where they said
  "the payload". A device
  firebreak cannot unlock at all says that, rather than calling a 2017
  bootloader too new. The note after an Echo is parked in its bootrom says only
  what to do with it, where it first explained that amonet's payload was
  holding the bootrom and that the next run would join it.
- A run that cannot yet tell which Echo is in front of it says so at once,
  where it waited a minute before saying anything. The longer note, which says
  that a fastboot and a recovery both answer and that an Echo showing no light
  never does, still follows after 30 polls.

### Removed

- The target names that carried an amonet version, `amonet-biscuit-v1.1.0`,
  `amonet-biscuit-v1.1.0-bboe` and `amonet-biscuit-v2.0.0`, as the README
  promised for 1.0. Use `firebreak unlock fireos5` or `firebreak unlock
  fireos6`. A plugin's `DeviceConfig` loses `was_called` with them. A run with
  no command prints the help and no longer warns which command replaced the
  old default.
- `firebreak.pyz`. A release now carries the wheel and the sdist alone, and
  `uvx firebreak@latest` is the one way to run it. Nothing is known to have
  used the pyz, and it cost more than it paid for: because a zipapp carries no
  dependencies, a run had to decide at runtime whether its own child could
  `import serial`, download pyserial's wheel from PyPI when it could not, and
  thread that path through `sys.path` and every child's `PYTHONPATH`. That
  machinery is gone with it, so pyserial is now an ordinary pinned dependency
  and a run that cannot import it is a broken install rather than a case to
  recover from.

### Fixed

- An Echo Dot (3rd Generation) in its stock fastboot is told so at once and
  asked for its bootrom, with the hold started before the cable goes in.
  Before, the unlock printed nothing there and stopped after 10 minutes with
  "has been stock fastboot for 10 minutes", because no step of a donut's
  unlock starts in fastboot. `firebreak fastboot` tells a donut to start the
  hold a second or two after the cable goes in, which reaches fastboot, and
  `stock` on a donut with nothing to restore names `unlock`, not amonet v2
  and its + button.
- A write in TWRP that lost its read of where the partition starts waits for
  the Echo to reconnect and reads it again. Before, it took adb's own error as
  the start and stopped the run with a wrong partition table. On Windows,
  2026-11-05: `/dev/block/mmcblk0p13 starts at adb.ex: device
  'SERIAL' not found, not 294912`.
- `firebreak short` on an Echo Dot (3rd Generation) refuses at once and names
  `firebreak unlock fireos6`. So does `firebreak bootrom` on a donut that is
  already in its bootrom. Before, `short` asked for a test point that a donut
  does not have. A second run, on a bootrom whose one handshake was spent,
  then failed on that handshake.
- An Echo the run cannot name yet, held in its bootrom, fetches amonet's
  archive only once its bootrom's hardware code says the chip is amonet's. A
  donut was named that way after a 74 MB download it never used.
- `firebreak twrp` on a locked Echo says the unlock rewrites its bootloaders,
  its TEE and its recovery, in place of saying it erases everything. On a
  radar it kept userdata; no other device has been read.
- A waiting line and the restore's `Starting now.` end at their last word on
  a terminal that shows colour, in place of trailing spaces.
- `survey` reads an OTA whose payload names two TEE partitions, where it
  refused such an OTA with `the OTA has no tee image`. Every Echo Dot
  (3rd Generation) OTA names `tee1` and `tee2` and writes the same image to
  both. A build's CSV gains a row for each partition, and the TEE the survey
  reports is the first of them, with a warning where they differ.
- A restore takes its TEE image from such an OTA too, where only `survey`
  could read those names and the restore stopped on the same message.
- A route for a device unlocked with kamakiri is chosen by the target rather
  than the device, so `firebreak stock` on an Echo Dot (3rd Generation)
  restores it instead of unlocking and rooting it again.
- The tests that read the GCPU routines out of a cached preloader skip the
  ones belonging to a device with another engine, where a cached Echo Dot
  (3rd Generation) preloader failed four of them.
- An unlock that needs a password asks for it before it asks for the button,
  not while the button is being held. The prompt had arrived mid-hold, so
  letting go to type it started the Fire OS and the gesture had to be done
  again. It also says why it asks, and names the Echo it has identified, in
  place of a bare `Password:` with nothing before it.
- `firebreak bootrom` refuses a device it has no bootrom chain for before it
  restarts the Echo, not after. On an Echo Dot (3rd Generation) it rebooted
  into TWRP first and then refused, though the device was named before it
  started.
- A bootrom libusb can see but not open is refused with a message naming the
  udev rules that give a user access to it, in place of a traceback. On Linux
  no run elevates, so a missing rule showed that way.
- A bootrom reaches its unlock on Linux, where the kernel's `cdc_acm` driver
  held the interface libusb needs and the run stopped with `[Errno 16]
  Resource busy`. A run off macOS detaches that driver first, and says so
  where it cannot.
- The exploit's trigger says what it answered where the payload does not come
  up, in place of swallowing it.
- The password for the privileged call is asked for again once the bootrom has
  answered, because sudo's own timestamp can expire during the button hold and
  the download, which put the prompt back where it was.
- A message that names the state an Echo is in says `stock fastboot`,
  `unlocked fastboot` or `TWRP`, where it printed the state's own name and
  called every unlocked bootloader amonet's whatever had written it. A run
  says which state it found only when the Echo was already there rather than
  mid-run, and a guided unlock is shorter by two lines that repeated the
  gesture beside them.
- An Echo Dot (3rd Generation) is asked for its bootrom, with its own gesture,
  where the unlock prompts asked for fastboot mode and offered a green ring to
  wait for. That unlock starts in the bootrom and never visits fastboot, and
  the hold has to last until the run says the bootrom answered.

## 0.11.0 - 2026-11-01

### Added

- `unlock` roots an Echo (2nd Generation) on Fire OS 6 8338, 8344 and 8349,
  and `stock` installs them, where it offered none of the three and `unlock`
  refused their bootloader. amonet-radar v1.0.1 is the first release with an
  image for `2c3569d-20260617_051433`, which Amazon shipped to that device on
  2026-10-14, 10-21 and 10-27. It also gives `63cb91b-20221007_073612` an
  image of its own, where v1.0.0 gave it the default. Its
  `fastbrick-20260617.img` is radar's own, not the biscuit image of the same
  name, read from its tail against 8349's bootloader.
- v1.0.1 rebuilt three files v1.0.0 shipped: `radar-kaeru.bin`, which the chain
  writes to `expdb`, the default `fastbrick.img`, and `fastbrick-20220524.img`.
  Everything else it writes is byte for byte v1.0.0's, the bootrom payload
  included, so the plan is unchanged.
- Measured on a radar on 2026-11-01, over thirteen runs: `unlock` took a locked
  8338 to rooted Fire OS 6 8338 in 2 min 42 s, the first unlock of
  `2c3569d-20260617_051433` on hardware. `stock` then restored 8344, 8149,
  8349, 4305 and 5.5.5.4, and an `unlock` followed each one. So every image
  v1.0.1 rebuilt or added ran on an Echo, and `boot-root.zip` rooted all three
  new builds in place.

## 0.10.0 - 2026-10-30

### Added

- The bootrom and the preloader are states a run can see: `bootrom` where USB
  holds `0e8d:0003` and `preloader` where it holds `0e8d:2000`, read from the
  same USB list the device names come from, so it works on macOS, Linux and
  Windows without pyserial. `report` prints them, and a command that cannot
  act on one says what does.
- `firebreak fastboot`, `firebreak twrp` and `firebreak bootrom` reach one
  entry point and stop there, so a stage can be tested from the state it
  starts in. `twrp` on an unlocked Echo writes nothing: it restarts into the
  recovery already there, and says to come back with `--force` where that is
  not a TWRP. Each asks before a write it needs, and `--force` answers in
  advance.
- `stock 5.5.5.4` returns an Echo (2nd Generation) to Fire OS 5.5.5.4, where
  `stock` there took only the Fire OS 6 build it installs when left out.
- `unlock fireos6 --factory-reset` installs the same build `stock` installs
  when left out: 8149 on both devices, where a Dot got 8146 and an Echo 6436.
  Each device keeps one build rather than two, so the two cannot drift apart.
  The build is no longer the one amonet's own procedure installs, and the
  targets no longer say it is.
- `stock` with no build on an Echo (2nd Generation) installs Fire OS 6 8149,
  where it installed 6436. 8149 is the newest build firebreak offers that
  device, and it is the one `unlock` then roots in place.
- `stock` on an Echo (2nd Generation) takes thirteen builds, every OTA ftvdb
  lists for it except 8338, 8344 and 8349. Those three carry a bootloader no
  amonet-radar payload unlocks, so a restore to one of them would leave an
  Echo firebreak cannot unlock again. `docs/devices.md` records all sixteen.

### Changed

- `firebreak short` is a command of its own, where it was `--short` on other
   commands. All it does is reach the bootrom of an Echo that shows no light
   and hold it: it says where the test point is before it waits, and
   `--device` picks whose. It refuses nothing: a run that names no device, and
   one naming a device whose test point no one has found, are both told that
   firebreak cannot say where to short it, and both wait for a bootrom anyway.
   Nothing it does writes to the Echo.
- `--device` is `firebreak short`'s alone, and every other command stops where
  the Echo names no device rather than ask for one. A fastboot, a recovery and
  the bootloader in an Echo's flash each say which device it is, and those
  cover every state a command writes from, so a name off the command line
  could only overrule what the Echo said or stand in for an Echo nothing here
  has measured. `short` keeps it because an Echo that shows no light names
  nothing, and the run has to say where the test point is before it waits.
- `--run-on-unproven-path` is gone. It gated the short on a device with no
  known test point, which writes nothing and so needed no gate, and a target
  that says it is unproven, which no target says.
- The `bootrom-held` and `boot0-erased` files in the cache are gone, and
  nothing firebreak does now depends on what an earlier run wrote down. A run
  asks the Echo whether a payload is holding its bootrom, by sending the first
  byte of a payload command and watching for the bootrom's echo of it. It
  remembers an erase of its own for as long as that run lasts, which is what
  keeps `Only boot0 was erased.` true. What this costs: with nothing on USB a
  run can no longer name the Echo, so one that needs the name waits until the
  bootrom appears and names itself from flash.
- `stock`, `unlock` and `write-test` no longer short anything: park the Echo
  with `firebreak short` first, and the run after it joins the payload waiting
  there.
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
  says to unplug it and run firebreak again, which reads the name from the
  Echo itself.
- `report` reads the Fire OS 5 system image of the Echo in front of it, says
  there is none, or says it cannot tell which Echo this is. It read the Echo
  Dot's whichever Echo it ran on, so on an Echo (2nd Generation) it printed
  another model's image, and only when this computer happened to hold one.
- `write-test` keeps its reading of the Echo's `dd` in the same column as
  every other reading, where naming the model there ran past the column and
  left the value hanging.
- Neither Echo (2nd Generation) target is held back any more. Both have run
  on one, and the risk that kept them behind a flag was a failure between the
  boot0 erase and the preloader write, which is now recoverable over USB
  rather than by opening the Echo.
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
