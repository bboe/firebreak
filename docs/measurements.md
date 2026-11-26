# Measurements

Whole-run readings from hardware: the rings, the timings, and what an Echo's
bootrom does. [unlocking.md](unlocking.md) keeps the measurement each of its own
claims rests on, so this file holds only what belongs to no one step.

## The ring

An Echo Dot (2nd Generation). The estimates and the rings are from TWRP 3.2.3.
One root on macOS with TWRP 3.7.0_9-bboe1 came in under every estimate, its
replace step taking 37 s.

During `firebreak stock 6302`, from a rooted Dot not set up:

| ring | when |
| --- | --- |
| purple | rooted Fire OS 5, setup timed out (`anim_OOBE_start_error`) |
| off, about 12 s | `adb reboot recovery` |
| deep blue, about 10 s, a brighter segment turning in its last 3 | v1.1.0's TWRP starting, before adb answers |
| a blink off, then a cyan arc turning, about 3 s | TWRP up: `adb wait-for-recovery` returns |
| cyan, whole ring, steady | through the restore's steps |
| off, about 8 s | the reboot into stock |
| deep blue, about 50 s | stock Fire OS 6 booting |
| cyan and blue, turning | Fire OS 6 starting Alexa |
| orange | setup mode, about 90 s after the reboot |

During a root from stock 8138, in daylight, 14 min 49 s in all. That root went
through the bootrom, which a root from stock does not. A run from stock 5041 at
night showed the same, except that the fastbrick ring read white:

| ring | when |
| --- | --- |
| green | stock fastboot, from the button held at power-on |
| off 1 s, then yellow, shrinking to an arc over about 10 s | the fastbrick flashed |
| red-orange, about 7 s, then green, about 5 s, then off, about 5 s | the exploit, before TWRP |
| blue, about 9 s | v2.0.0's TWRP starting |
| a white flash, a blink off, a cyan arc | v2.0.0's TWRP up; the script reboots it at once |
| off, about 7 s | `adb reboot bootloader` |
| a white flash, then every color, turning, about 5 s | the exploit's unlocked fastboot |
| off, about 5 min | the bootrom step: `boot0` erased, then amonet v1.1.0 |
| blue, about 10 s, then every color, turning, about 3 s | v1.1.0's fastboot, while `tee2` and `recovery` are flashed |
| off, about 5 s | `fastboot oem reboot-recovery` |
| deep blue, about 13 s | v1.1.0's TWRP starting |
| blinks off, a cyan arc turning, about 5 s | adb answers, MTP not yet on |
| cyan, whole ring, steady | from MTP on, through the Fire OS push and install |
| off, green, off, green, off, about 5 s | the Fire OS install finishing |
| cyan, whole ring, steady | the boot image, /system and Magisk |
| off, about 6 s | the first reboot into Fire OS 5 |
| deep blue, about 35 s | Fire OS 5 booting |
| cyan and blue, turning, about 3 min | the first boot, until the setup app starts |
| orange | setup mode, about 1.5 minutes before the script finishes |

- A USB port that cannot power TWRP shows as a ring that restarts instead of
  reaching it: blue, about a second of turning cyan, little or no white, over
  and over. Reported 2026-10-25 on Windows, on 2 of 3 Dots after the unlock,
  with LK `63cb91b-20221007_072309`. A USB wall charger with the + button held
  reached white, and a port directly on the PC then carried the run through.
  The port that failed had run disc drives. Why TWRP is where this shows up is
  not measured.
- A port too weak for the Echo also drops it off USB during TWRP writes. On
  Windows 11, 2026-11-05, two Dots on one USB 2 port did that, and one of them
  then restored stock and unlocked from a USB 3 port on the same PC. So every
  stop or note that names a port that cannot power the Echo gives one retry:
  another USB port, of which a USB 3 port on the computer itself, with nothing
  else on it, is the most reliable. A powered hub may give more current; none
  was tried. While boot0 is erased, that retry comes only after a run in place,
  as [unlocking.md](unlocking.md) says beside the restore's boot0 window.
- The ring turns orange before the boot is done. On a Dot, 2026-10-04, the
  setup app started and the ring turned orange 30 s before `BOOT_COMPLETED`
  went out, and the first `su` came 13 s after that. The last step ended about
  a minute later, 322 s after `adb reboot`, estimated from the Dot's uptime
  because the step logged no time. That minute held Magisk's first `su`, the
  2-second probes and `hide_updater`'s `dumpsys package`.

## Whole-run timings

Each row's state is the one the run started from, and each run went with no
one touching the device unless the row says otherwise. A row naming several
builds is that many runs, whose totals agreed inside the range given unless the
row gives one of its own. The rows name states as those runs printed them:
`amonet-booted`, `amonet-fastboot` and `amonet-twrp` are `unlocked-booted`,
`unlocked-fastboot` and `unlocked-twrp` since 2026-11-05.

| from | to | took |
| --- | --- | --- |
| rooted, with amonet's TWRP 3.2.3 in `recovery` | `unlock fireos5` | 9 s: bboe2 written through `su`, and done |
| amonet-fireos5-bboe-booted | `unlock fireos6` | 5 min 11 s, 2026-10-09, by the plan. The zip took 5 min 22 s, its install 19 s and its reboot 19 s |
| amonet-booted | `unlock fireos5` | 7 min 42 s, with no bootrom |
| stock-fastboot | `unlock fireos5` | 8 min 3 s, and 8 min 4 s again on 2026-10-26 over 11 steps: the fastbrick, then the route from amonet-booted. From 5.5.5.4, whose LK takes the default `fastbrick.img`, 8 min 6 s on 2026-10-25 |
| amonet-fastboot, on amonet v2's own bootloader | `unlock fireos5` | 7 min 40 s, 2026-10-26, over 10 steps and with no bootrom. The run opened at 6 steps and the gate's `False` re-planned it to 10. adb answered 24 s into Fire OS 5's boot and held through setup mode |
| stock-fastboot | `unlock fireos6` | 4 min 54 s to 5 min 18 s, 2026-10-24 to 10-29, from 8149, 8344, 4315 and 8149 with `--factory-reset`. The slot guard passed after each install. 4315's LK takes amonet v2.0.0's image, where the other three take v2.0.1's |
| stock-fastboot, on 8338 | `unlock fireos6` | 1 min 18 s, 2026-10-26, patched in place: no wipe and no OTA install, where `--factory-reset` takes 7 steps |
| stock-fastboot, on 5.5.0.3 | `unlock fireos6` | 4 min 56 s, 2026-10-26, whose slot holds no Fire OS 6, so the run took the fallback's 8 steps |
| bootrom, held | `unlock fireos6` | 6 min 05 s, 2026-10-26, with no button held: joining the payload under 1 s, then v1.1.0, v2.0.1 and the fallback's installs |
| bootrom, held after `stock 5.5.0.3` | `unlock fireos6` | 5 min 16 s, 2026-10-26 |
| bootrom, held after `stock 5.5.0.3` | `stock 8149` | 4 min 26 s, 2026-10-26, over 27 steps |
| amonet-booted, amonet-fireos5-bboe-booted or amonet-fireos5-bboe-twrp | `stock BUILD` | 3 min 11 s to 4 min 4 s, 2026-10-24 to 10-26, for 8146, 8149, 8344, 4315, 4405, 5.5.5.4 and 8338, over 17 steps each, and stock's first boot 32 to 34 s where `--end-in-fireos` was given. The images came from the cache in some runs and were built from the OTA in others, which changed nothing |
| unlocked-booted, then stock-fastboot | `stock BUILD`, then `unlock fireos6` | 2026-11-06, on Linux, every biscuit build `BUILDS` held unverified: Fire OS 6 4310 to 8349 and Fire OS 5.4.2.7 to 5.5.5.0, 42 builds, each restored and then unlocked from its own locked fastboot. Every restore took 2 min 46 s to 3 min 6 s over 17 steps. Each unlock opened with the fastbrick, so the fastboot `stock` left was locked: amonet v2.0.0's for 4310 and 4313, v2.0.1's for the rest. It took 1 min 14 s to 1 min 24 s rooting the restored Fire OS 6 in place, and 3 min 55 s to 4 min 6 s for a Fire OS 5 build, where it installs 8149 into both slots. Each Echo then read `sys.boot_completed` 1, stayed up a minute, and ran the build with root adb. None failed |
| unlocked-twrp, then stock-fastboot, on 8888 | `stock 8888`, then `unlock fireos6` | 2026-11-26, on Linux, the first runs of build 8888. The restore took 3 min 21 s over 16 steps, and its preloader, LK and TEE matched the OTA's manifest. The unlock opened with amonet v2.0.1's fastbrick, so the fastboot `stock` left was locked, and took 1 min 22 s over 5 steps, rooting 8888 in place rather than installing 8349. The Echo then ran `Fire OS 6575.1 (NS65751/8888)` with root adb |
| unlocked-booted, then bootrom, held | `stock 5.5.0.3-1973`, then `unlock fireos6` | 2026-11-06, on Linux. The restore took 2 min 57 s over 19 steps and ended `waits in its bootrom`. The unlock joined that payload with no button held and took 4 min 32 s over 17 steps, its RPMB write skipped because the restore had zeroed it, and installed 8149 into both slots. The Echo then read `sys.boot_completed` 1, stayed up a minute, and ran 8149 with root adb |
| amonet-booted | `stock 5.5.0.3` | 3 min 38 s, 2026-10-26, from rooted Fire OS 6 over 19 steps. It ended `waits in its bootrom`, with the payload still on its serial port, and no reboot after the preloader. From v2's TWRP it is 18 steps |
| amonet-twrp, amonet-booted or amonet-fastboot | `bootrom`, `twrp`, `fastboot` | 10 s to 20 s, 2026-10-29, the first entry commands on hardware. `twrp` from amonet-fastboot wrote nothing, by `restart_refusals()` alone. A second run in any of those states reported the state and did nothing |
| amonet-twrp or amonet-booted, on a radar | `bootrom` | 34 s and 37 s, 2026-10-30 and 11-01. A second `bootrom` answered `already waits in its bootrom` in 7 s and then in 4 s, joining a live payload by probe without disturbing it, where nothing in the cache said one was there |
| bootrom, held, on a radar | `unlock` | 1 min 29 s on v1.0.0, 2026-10-30, and 1 min 31 s on v1.0.1, 2026-11-01: the hold joined by probe with no step of its own, and the TEE, bootloader, kaeru and TEE payload all skipped as already right |
| amonet-booted or amonet-fastboot, on a radar | `stock BUILD` | 2 min 31 s to 2 min 43 s, 2026-11-01, for 8344, 8149, 8349, 4305 and 5.5.5.4. `misc` and both tables skip as already right, so 14 of 17 steps write; `tee2` skips too on 8149, and on 5.5.5.4 **both LK writes skip**, because amonet's `lk.bin` is that build's own LK. 4305 and 5.5.5.4 are block OTAs, whose images come from the OTA and whose `/system` is built from the transfer list |
| amonet-v2.0.0-booted, on a radar | `stock 6436` | 3 min 37 s once TWRP was up, 2026-10-17, over 17 steps. Its table and `tee2` already matched stock. Stock 6436 started 24 s after the reboot, and fastboot then read `unlock_status` `false` with LK `63cb91b-20221007_073612`. amonet-radar v1.0.0 rooted it again in 8 min 28 s |
| unlocked-booted, then stock-fastboot, on a radar | `stock BUILD`, then `unlock fireos6` | 2026-11-07, on Linux, every radar build `BUILDS` held unverified: Fire OS 6 4929 to 8338, 14 builds, each restored and then unlocked from its own locked fastboot. Each restore took 3 min 53 s to 3 min 58 s over 17 steps, and each unlock 1 min 23 s to 1 min 45 s, rooting the restored build in place with amonet v1.0.1. Both are read by the wall clock, the start of `uv run` included. Each Echo then read `sys.boot_completed` 1, stayed up a minute, and ran the build with root adb. 6436, held unverified because nothing had unlocked from it, was among them. None failed |
| unlocked-booted, on a donut | `stock BUILD`, then `unlock` | 2026-11-07 and 11-08, on macOS, every donut build but 8349: Fire OS 6 1895 to 8344, 25 builds, each restored and then unlocked from the bootrom with the button held. Each restore took 5 min 11 s to 5 min 25 s over 16 steps, and 6 min 41 s at most, by the wall clock with the start of `uv run` included. The unlocks include the wait for the password and the button, so only the fastest, 1 min 53 s, is a reading. Each Echo then read `sys.boot_completed` 1, stayed up a minute, and ran the build with root adb. Three needed a second pass. 1895 starts with adb off, so its restore waited for adb until it was stopped, and it was unlocked by hand. 6009's first push of `system_b` lost adb's reply, and a rerun wrote it cleanly. 8142's first stock boot was unplugged part way, and it then showed nothing on USB through two more replugs. A rerun left alone came up in the usual time |
| stock-fastboot, locked, on a radar | `unlock` | 1 min 10 s to 1 min 16 s, 2026-11-01, from 8338, 8344, 8349, 8149 and 4305. The 8338 run took 2 min 42 s instead, because nothing showed on USB after the zip until the power was cycled, which the run asked for after a minute; `fastboot` then reached amonet-fastboot 8 s later |
| stock-fastboot, locked on 5.5.5.4, on a radar | `unlock` | 3 min 54 s, 2026-11-01, which installed 8149 over both slots. No `--factory-reset`: a slot holding Fire OS 5 reads as no build, which takes the install path anyway |

Where the time goes, from the step timings those runs printed:

- A `/system` write is the floor: 79 to 81 s on a Dot, 48 to 50 s on a radar,
  and a restore writes two of them. Every other step of a Dot's restore is
  under 7 s, except `restarting into fastboot` at 10 s and 5.5.0.3's preloader
  at 8 s. A radar's restore waits 17 s for TWRP and 8 s for that restart.
- Fire OS 5's first boot is 318 to 321 s, most of an 8-minute
  `unlock fireos5`. Fire OS 6's is 23 to 25 s, and a rooted radar's 19 to
  22 s, except for the 8338 run above, where it read 104 s because the power
  cycle it asked for falls inside that step.
- An OTA install is 96 to 103 s for the first slot and 115 to 116 s for the
  second on a Dot, so the pair is most of a 5-minute `unlock fireos6` from
  stock. A radar is faster: 69 s and 87 s, in the one run that installed over
  both slots.
- A fastbrick takes 8 to 13 s on its first flash, and the TWRP behind it comes
  up 27 to 35 s later. `boot-root.zip` takes 8 to 13 s.
- A chain written through a held bootrom is 27 to 38 s, and amonet's fastboot
  answers 8 s after the reboot that follows.

Odds and ends:

- `bcbtool get_active` printed a bare `a` or `b`, and each OTA install changed
  it. The downgrade ran on the stock partition table the zip left.
- Not run: the plan on amonet v1.1.0's partition table in v2.0.0's TWRP, and
  `short` to amonet v2.0.0.
- Measured on a Dot, 2026-10-10, each run from where the last ended:
  amonet-fireos5-bboe-booted to `amonet-biscuit-v2.0.0` in 4 min 54 s, then
  `amonet-biscuit-v1.1.0` in 7 min 47 s, then v2.0.0 from TWRP 3.2.3 in
  5 min 17 s, then `amonet-biscuit-v1.1.0-bboe` in 7 min 48 s. Each table copy
  took under 1 s, on all three TWRPs the backup copy went in as 33 records and
  read back whole, and the Dot booted rooted each time. The same four runs on
  another Dot from Windows, with `/system` in slices, took 4 min 51 s,
  8 min 17 s, 5 min 14 s and 8 min 16 s.

## What libusb can do on macOS

Measured on 2026-11-02, on a Dot held in its bootrom by amonet's payload, to
find out what an Echo Dot (3rd Generation) unlock would need of a host. That
unlock loads its payload through USB control transfers, so it cannot go through
pyserial; see [unlocking.md](unlocking.md#an-echo-that-shows-no-light).

- The bootrom offers two interfaces: 0 of class `0x02` subclass `0x02`, and 1
  of class `0x0a`, whose bulk endpoints are `0x81` in and `0x01` out with
  64-byte packets. It carries no USB strings, which agrees with the reading
  below.
- Unprivileged, macOS answers `EACCES` to every question about its own driver
  on both interfaces, yet the data interface still carries the whole payload
  protocol: the payload answered its read-memory command, the switch to the
  user area took, block 0 of that area ended `55 aa`, and the table read back
  all 16 partitions in order. So the OS driver holds interface 0 alone. The
  root run said so by name: it detached interface 0 and found no driver on
  interface 1.
- Endpoint 0 is the exception. A plain `SET_LINE_CODING` is refused with
  `EACCES` unprivileged, and takes its 7 bytes under root, where the
  configuration descriptor reads back `09 02 43 00 02 01 00 80 00`. So that
  unlock needs **root on macOS**, where nothing else about this transport
  does.
- The transport is not what limits a run. 1 MiB off `lk_a` took 2.03 s through
  libusb and 2.02 s through pyserial, 0.49 MiB/s either way, which agrees with
  the 0.66 MB/s amonet's own script read on a radar. The payload and the eMMC
  set the rate.
- pyserial worked again directly after the unprivileged run, with no reset and
  no power cycle. The root run is not so tidy: detaching interface 0 removes
  the `/dev/cu.usbmodem` node, and pyserial cannot see the bootrom again until
  something attaches it back or the Echo is power cycled. Anything that uses
  both must give the interface back.
- **A privileged detach does not hand endpoint 0 to an unprivileged process.
  It takes away what that process had.** With the driver on interface 0, an
  unprivileged libusb lists the Echo and drives the free interface. With the
  driver detached by root, the same process lists **no devices at all**, while
  `ioreg` still shows the device registered and active. So one privileged
  command per plug is not a way to keep a run unprivileged: either the step
  holds the device open as root throughout, as the run above did, or it cannot
  reach endpoint 0. What is left for a tool that may not ask for root is an
  unlock that needs no control transfer.

## An Echo (2nd Generation) in its bootrom

Measured on one radar on 2026-10-27, from TWRP, by clearing boot0's header by
hand and reading the ports back.

- An empty boot0 reaches the bootrom over the cable it is already on. The Echo
  came up as `0e8d:0003`, with no test point and no case opened. So the short
  is for the other failure, an intact boot0 whose preloader never starts LK.
- The bootrom does not wait forever. It answered for **about 40 seconds**, then
  went quiet and did not come back for the four minutes that followed. Its own
  watchdog takes it. That is why `load_payload` writes `0x1971` to
  `0x10007008` every second while it waits for the operator: once the payload
  is running the window stops mattering, and before that it is 40 seconds per
  power cycle, repeatable. A run that starts the step first and asks for the
  power cycle second loses nothing, where one that asks first can miss.
- The bootrom carries no USB strings: `0e8d:0003` with an empty manufacturer,
  against the preloader's `MediaTek` `MT65xx Preloader`. Reading vendor and
  product ids rather than names is what lets the step tell them apart.
- amonet-radar v1.0.0's own `bootrom-step.sh` put it back in 68 seconds, over
  the same step order firebreak's plan uses, and it ended in unlocked fastboot.
  Its reads ran at 0.66 MB/s and its writes at 0.47 to 0.55 MB/s.
- A read over the payload matched what TWRP had read from the same partition:
  `lk_a`'s first 356856 bytes hashed to amonet's own `bin/lk.bin`, by both md5
  and sha256. So eMMC access through the bootrom agrees with eMMC access
  through TWRP.

Measured again on 2026-10-30, on a rooted radar on Fire OS 6.5.5.5
(NS6555/4315), over the entry commands rather than by hand.

- Every entry point runs as it does on a Dot: `fastboot` from rooted Fire OS in
  8 s, `twrp` from that fastboot in 19 s, `fastboot` back in 8 s, each
  reporting a state it was already in without touching the Echo. `bootrom`
  erased boot0 from amonet's fastboot and had the payload in 2 s.
- The bootloader read names this one. `reading which Echo this is` took 2 s and
  said `Echo (2nd Generation)` with no `--device`, where `unlock` and `stock`
  both name a target two devices share. So the read picks either device from
  its own flash, not biscuit alone.
- A second `bootrom` joined the hold in 2 s, and `fastboot` from that bootrom
  refused and named `unlock`, as on a Dot.

## An Echo Dot (3rd Generation) in its bootrom

Measured on 2026-11-02, on the first donut to reach this project, over libusb
and over a serial port. Every reading below is from that one unit, and nothing
was written to its flash.

- It reports hardware code `0x8167`, sub code `0x8a00`, hardware version
  `0xcb00` and software version `0x0001`. mtkclient names that code
  `MT8167/MT8516/MT8362`, so one bootrom covers the family, and calling donut
  an MT8516 elsewhere is not contradicted by it.
- Its target config is `0x000000e5`: secure boot set, serial-link
  authorization clear, and **DA authorization set**. So the `0xDA` command is
  refused without an authorized download agent, which is what this family's
  exploit is for rather than a fault.
- **A word write lands over libusb and not through macOS's CDC driver.** The
  watchdog disable at `0x10007000` returned its status over the bulk endpoints,
  both through the kit and through this project's own code, and returned
  nothing at all through a serial port, twice, on a port that carried the
  handshake and every echo of that same command. So a donut needs libusb
  whatever starts its payload. No other device here shows that difference, and
  the mechanism is unread.
- **amonet's GCPU route does not carry to this chip.** Driven with mtkclient's
  published values for `0x8167`, a GCPU base of `0x1020D000`, a range check at
  `0x102968` and a jump register at `0x1029AC`, the first GCPU write, 9 words
  at the engine's `LENGTH`, answered `0x1d02` in place of its status, moments
  after the watchdog write at `0x10007000` had succeeded on the same
  connection. The bootrom's own write check covers the engine's registers on an
  MT8167 where it does not on an MT8163, so the engine cannot be the way in.
  That is why this family's kit exploits USB instead, and it closes the
  question of whether a second payload client alone would have been enough.
- The kit's pointers are mtkclient's published ones for this code: `0x100A00`
  for the payload, `0xd2e4` for the send pointer and `0xd7ac` for the register
  access. So its literals are right for this bootrom.
- The kit's own run reached `cmd_da` and was refused with `0x1d1a`, after macOS
  carried its 12-byte `SET_LINE_CODING`, 7 of line coding, a zero and a 4-byte
  pointer, and reported all 12 delivered. So the host did not stop it, and
  where the overflow lands is the remaining suspect. The kit is developed on
  Linux, which its own ModemManager check shows. The same run on Linux settled
  it on 2026-11-04: the kit's attack works there, and firebreak now uses it on
  every host but macOS. [unlocking.md](unlocking.md#echo-dot-3rd-generation)
  has the reading.

## What a bootrom gives you before it is exploited

Measured on 2026-11-03, on a donut restored to stock and on a biscuit, both in
their bootrom over libusb, and on the donut over its CDC serial port as well.
Nothing was written to either device's flash.

- **A bootrom gives one handshake per power-on, not one per connection.** On a
  donut, a second `0xa0` after a completed handshake drew no `0x5f` for the
  full `HANDSHAKE_TIMEOUT`, over libusb and over the serial port, on a device
  that was still listed and still opened without error. `usbdl`'s own message
  already says it: *the port needs a replug*. So whatever handshakes a bootrom
  must also be what drives it, and nothing can handshake a device to look at it
  and then hand it on.
- **`0xFD`'s second halfword is a status, not a version.** A donut answers
  `81670000` and a biscuit `81630000`, so the code differs and the status is
  `0x0000` on both. The `0x8a00` sub code recorded above comes from a different
  command, and `hardware_code` checks the status now. mtkclient reads the reply
  the same way.
- **`0xFD` works over the CDC serial port on a donut**, answering the same
  `81670000` that libusb gets, with the handshake taking 1 ms. So the serial
  port carries the echo commands on a donut; it is the word *write* that
  returns nothing, and only that.
- **Before the handshake a bootrom answers `0xFD` with a single `0xfe`.** No
  code, no echo. So nothing identifies a device before the handshake is spent.
  A stray pre-handshake byte did not stop the handshake that followed.
- **A donut's bootrom and a biscuit's are identical over USB.** Both report
  `bcdDevice` `0x0100`, `bcdUSB` `0x0110`, device class `0x02`, **no string
  descriptors at all** for manufacturer, product or serial, and the same two
  interfaces: `0x02` with one 64-byte endpoint at `0x84`, and `0x0a` with
  64-byte endpoints at `0x81` and `0x01`. So the descriptors cannot say which
  Echo is in front of a run, and only the hardware code can.

## A stock Echo Dot (3rd Generation) in fastboot

Read on 2026-11-03 from the donut above, restored to stock, by `getvar`.

- `product` is `DONUT`, so the device file's value is right and firebreak names
  it "Echo Dot (3rd Generation), by its fastboot product DONUT".
- `unlock_status: false`, `secure: yes`, `prod: 1`, `rpmb_state: 1`, and the
  three antirollback versions are each `0x0001`.
- `lk_build_desc` is `6f7225e-20230407_013816`, which donut already declares.
  `pl_build_desc` is `9eb982d-20231103_081354`, where `survey` reads
  `20231103_081354` from the same build's OTA. The timestamp is in the
  preloader as text, after a `Build Time: %s` string, and the commit is not:
  it sits in a literal pool as the word `0x09eb982d`, which no search for a
  string can find. 8349's preloader holds that word, and 1895's does not.
- `max-download-size` is `0x8000000`, `kernel` is `lk`, `version-preloader` is
  `0.1.00` and `version` is `0.5`.
- **It answers no A/B slot variables at all.** `current-slot`, `slot-count`,
  `has-slot:boot`, `slot-successful:a` and `slot-unbootable:a` all come back
  empty on a device whose table has both slots. So fastboot cannot say which
  slot is active and cannot set one, and `bcbtool` from a recovery is the only
  way at it, which is what the kit's own guide uses.

## A handshake crosses transports

Measured on 2026-11-03, on the stock donut above, on one power-on.

- **A handshake taken over the CDC serial port still counts over libusb.** The
  port handshaked, answered `0xFD` with `81670000`, and was closed. libusb then
  opened the same endpoints and `disable_watchdog` wrote `0x10007000` with no
  second handshake, and a second write went through after it, so the stream
  stays in step. That is what lets a donut be named over the serial port and
  then exploited over libusb on the same power-on.
- **Pick the first command after the switch with care.** `read_words` of one
  word at `0x10007000` answered argument status `0x0003` rather than `0x0000`,
  the same status the kamakiri ladder tolerates, and the failure left unread
  bytes behind: the write after it then read `0x00` where it wanted `0xd4`'s
  echo. So that first reading looked like the handshake had been lost when it
  had not. The command echoes had matched, which a bootrom that has not
  handshaked does not do, since it answers `0xfe` instead.
