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
row gives one of its own.

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
| amonet-booted | `stock 5.5.0.3` | 3 min 38 s, 2026-10-26, from rooted Fire OS 6 over 19 steps. It ended `waits in its bootrom`, with the payload still on its serial port, and no reboot after the preloader. From v2's TWRP it is 18 steps |
| amonet-twrp, amonet-booted or amonet-fastboot | `bootrom`, `twrp`, `fastboot` | 10 s to 20 s, 2026-10-29, the first entry commands on hardware. `twrp` from amonet-fastboot wrote nothing, by `restart_refusals()` alone. A second run in any of those states reported the state and did nothing |
| amonet-twrp or amonet-booted, on a radar | `bootrom` | 34 s and 37 s, 2026-10-30 and 11-01. A second `bootrom` answered `already waits in its bootrom` in 7 s and then in 4 s, joining a live payload by probe without disturbing it, where nothing in the cache said one was there |
| bootrom, held, on a radar | `unlock` | 1 min 29 s on v1.0.0, 2026-10-30, and 1 min 31 s on v1.0.1, 2026-11-01: the hold joined by probe with no step of its own, and the TEE, bootloader, kaeru and TEE payload all skipped as already right |
| amonet-booted or amonet-fastboot, on a radar | `stock BUILD` | 2 min 31 s to 2 min 43 s, 2026-11-01, for 8344, 8149, 8349, 4305 and 5.5.5.4. `misc` and both tables skip as already right, so 14 of 17 steps write; `tee2` skips too on 8149, and on 5.5.5.4 **both LK writes skip**, because amonet's `lk.bin` is that build's own LK. 4305 and 5.5.5.4 are block OTAs, whose images come from the OTA and whose `/system` is built from the transfer list |
| amonet-v2.0.0-booted, on a radar | `stock 6436` | 3 min 37 s once TWRP was up, 2026-10-17, over 17 steps. Its table and `tee2` already matched stock. Stock 6436 started 24 s after the reboot, and fastboot then read `unlock_status` `false` with LK `63cb91b-20221007_073612`. amonet-radar v1.0.0 rooted it again in 8 min 28 s |
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
