# Unlocking

firebreak takes an Echo from stock Fire OS 6 to a rooted one. It polls
the Echo every 2 seconds, does the stage for the state it finds, and stops when
the Echo is in the state its optional target names. The table gives the stages
for the default, `unlock fireos6`; [Targets](#targets) has the
others, and [Back to stock](#back-to-stock-the-stock-target) the `stock` target.
[Each device](#each-device) holds what is true of one device alone.

| state | how it is recognised | what the run does |
| --- | --- | --- |
| stock-booted | `adb get-state` says `unauthorized`, or Fire OS 6 without root | prints the fastboot gesture, and the + gesture for a Dot already on amonet v2.0.0 |
| stock-fastboot | `unlock_status` is `false`, and `lk_build_desc` is none of the two below | the device's fastbrick |
| stock-fireos5-fastboot | `unlock_status` is `false`, and `lk_build_desc` is the device's Fire OS 5 chain's, `f379dba-20170906_000423` on a Dot, which that chain keeps: Fire OS 5's own fastboot, locked, on a stock Dot or one on the chain. A device that declares no chain cannot reach it | the same |
| bootrom | no adb or fastboot, and USB holds `0e8d:0003` | nothing: a chain goes in through the payload there, which `unlock` and `stock` write |
| preloader | no adb or fastboot, and USB holds `0e8d:2000` | waits: every boot passes through this for about 0.8 s. One that never leaves it needs the test point |
| emos | no adb or fastboot, and one serial port with USB ID `1949:2007` | `/init recovery` at emOS's serial console |
| no-system | adb answers as `device`, and `adb shell` fails with `exec '/system/bin/sh' failed` | `adb reboot recovery`, for every target |
| amonet-booted | Fire OS 6, and `id` or `su -c id` answers uid 0 | `adb reboot recovery`, into the device's own TWRP; ends an `unlock fireos6` run |
| amonet-twrp | unlocked, `lk_build_desc` is not the device's Fire OS 5 chain's, `mtp` in `sys.usb.config` | moves boot in the table to make room for that chain, then reboots so the kernel rereads it |
| amonet-twrp-boot-moved | amonet-twrp, and `sgdisk --print` lists `boot_a_x`, the boot moved layout's name | writes the Fire OS 5 chain and Fire OS 5.5.5.4, preloader last |
| amonet-fastboot | unlocked, `lk_build_desc` is not the device's Fire OS 5 chain's | starts the device's own TWRP where the bootloader is the one its unlock declares, and downgrades to its Fire OS 5 chain through the bootrom where it is not |
| amonet-fireos5-fastboot | `unlock_status` is `true`, and `lk_build_desc` is the Fire OS 5 chain's | that chain's TEE and its TWRP, 3.7.0_9-bboe2 on a Dot, then recovery |
| amonet-fireos5-twrp | recovery, the Fire OS 5 chain's `lk_build_desc`, a `ro.twrp.version` that is not the chain's, `mtp` in `sys.usb.config` | writes the chain's TWRP to `recovery`, reboots into it |
| amonet-fireos5-bboe-twrp | recovery, the Fire OS 5 chain's `lk_build_desc` and its `ro.twrp.version`, `mtp` in `sys.usb.config` | Fire OS 5.5.5.4, boot and /system patches, Magisk 17.3 |
| amonet-fireos5-bboe-booted, rooted | `sys.boot_completed` is 1 and `su -c id` answers uid 0; `recovery` hashes as the Fire OS 5 chain's TWRP, or as anything else | the target's state: hides the updater and checks it; another: writes the target's TWRP to `recovery` |

- The four amonet-fireos5 states and stock-fireos5-fastboot are a device's Fire
  OS 5 chain, which only biscuit declares: its LK, the TWRP it installs, that
  TWRP's hash, and the unlock that writes it. No state names an amonet version,
  because a version is only unique to one device: biscuit's chain is amonet
  v1.1.0 and radar has no v1.1.0 at all. The probe asks the chain of the device
  the target names, or of every device that declares one where no target has
  named it yet, as in a `report` before it says which Echo this is. A device
  without one, radar and crown, reads the amonet states instead, and a locked
  one reads stock-fastboot rather than stock-fireos5-fastboot.
- A probe can land part way through a boot. TWRP answers adb before it sets
  `ro.twrp.version`, and while USB drops for MTP, `adb shell` answers with
  adb's error text. Either would read as amonet v2.0.0's and start a downgrade.
  So an `lk_build_desc` not shaped like `f379dba-20170906_000423`, or a version
  not starting with a digit, reads as `starting`. The downgrade checks the
  shape too.
- An empty `lk_build_desc` would read as amonet v2.0.0's and repeat the
  downgrade, `boot0` erase included. So an empty or timed-out fastboot read,
  and any poll that times out, reads as `starting` too.
- A rooted Fire OS 6 Dot is on amonet v2.0.0, because Fire OS 6 has no root
  without the unlock. Its root is Magisk's `su`, or an `adbd` that runs as
  root and no `su` at all, which the XDA thread's `boot-root.zip` leaves. So
  the probe asks both.
- A Dot unlocked with amonet v2.0.0 that boots Fire OS 6 without root also
  answers `unauthorized`, so it reads as stock-booted. amonet v2.0.0 removes
  stock fastboot, and the action-button gesture on an amonet v2.0.0 Dot was
  never tried. So the message also names + at power-on, which starts v2.0.0's
  TWRP.
- On a stock Dot with LK `63cb91b`, 2026-10-12, the gesture on one USB port
  of a Mac laptop left a solid blue ring, and the Dot showed nothing on USB.
  On another port the same gesture gave a green ring and fastboot. The same
  day, from stock 8149, the gesture on the first port went green, so the
  cause is not known. The gesture's message says to try again or try another
  port when the ring stays solid blue.
- `su` answers about 27 seconds into Fire OS 5's first boot, while
  `dumpsys package` still answers `Can't find service: package`. So rooted
  also needs `sys.boot_completed` to be 1.
- A Dot whose `/system` write stopped part way starts Fire OS 5's kernel, and
  the ramdisk's adbd answers as `device`. There is no shell, so `adb shell`
  fails with `exec '/system/bin/sh' failed`, and Fire OS never finishes. A run
  that waited for it as `booted` stopped after 10 minutes. So that answer reads
  as no-system, and the run reboots the Dot into recovery. adbd does that with
  no shell, and the rerun's TWRP stage writes `/system` again. Within one run
  it cannot happen: the write that stops part way stops the run.
- A sound boot does not give that answer. Fire OS 5's `init.rc` runs
  `mount_all` in `on fs`, and starts adbd later, with `class_start core` in
  `on boot`. Fire OS 6's adbd is `disabled` and starts from the
  `sys.usb.config` triggers, which run after `late-init`, and `init.aosp.rc`
  has `/system` mounted by the end of its `fs` stage.
- adbd's other wording of the failure, if one exists, reads as booted, as
  before. That costs the 10-minute wait, not a wrong reboot.
- Each state is acted on at most once per run, so a stale read cannot repeat a
  stage. The downgrade ends with amonet-fireos5-fastboot's stage, and counts as
  both.
- That stage needs amonet's fastboot, and the bootrom step does not always
  leave the Dot in it. On a resumed run reported from Windows the step wrote
  v1.1.0 and the Dot came back in v1's own **locked** fastboot: a solid green
  ring, `unlock_status` `false`, and `restricted on locked hw` from the first
  `fastboot flash`, which is all a locked LK answers. So the stage reads
  `unlock_status` first and returns where it is `false`, and a stage that
  returns that way counts none of the states it would otherwise pass. That
  leaves stock-fireos5-fastboot's own stage to unlock the Dot again, where the
  once-per-run rule would otherwise have the run wait out its 10 minutes on a
  state already counted. The chain then goes in from v2.0.0's TWRP, which is
  the route a rerun took to rooted Fire OS 5 in 7 min 45 s.
- Why the Dot came back locked is not known. Its table already held
  `boot_a_x`, so the surgery had finished, and the preloader and LK were
  v1.1.0's. What that leaves is the microloader in amonet's own `boot_a` and
  `boot_b`, or the boot control block.
- The script waits without limit for an Echo and for the fastboot gesture. Any
  other state unchanged for 10 minutes stops it, and the next run redoes that
  stage.
- Rooting formats userdata. A registered Echo loses its Wi-Fi and its Alexa
  registration, and finishes in setup mode.
- After boot0 is erased the Echo shows up only as the bootrom's serial port,
  which no probe sees. A run that erases boot0 records that for itself, in
  memory, from just before the erase until boot0 is written back: amonet's
  `Reboot to unlocked fastboot`, or the Echo seen booted or in fastboot, which
  only a preloader in boot0 reaches. TWRP does not count, because it keeps
  running from RAM after the restore to stock clears boot0. Nothing is written
  to the cache, so the next run starts over and reads the Echo instead.
- Which chain the bootrom writes follows the target, and nothing else.
  `unlock fireos5` takes amonet v1.1.0's, which is its goal. `stock` and
  `unlock fireos6` take amonet v2.0.1's and continue from v2's TWRP, which saves
  them the hop: v1.1.0's chain bought nothing but a recovery, on the boot-moved
  table a restore then has to undo, and the one reported Dot that came back
  **locked** from a bootrom step came back from that chain.
- The short does not come into that choice. It decides how the bootrom is
  reached, and every part of it -- the port listing, the countdown, the missed
  shorts -- is done before the payload runs, where the chain is a plan the
  payload carries out with the short already off. The one thing the two share
  is the boot0 header clear, which `short` leans on for its marker below and
  which both chains have in front.
- v2.0.1's chain from the bootrom is amonet's own `bootrom-step.sh`, which runs
  `modules/main.py`: the table reverted to stock, the RPMB zeroed, `tz.img` to
  `tee2`, `lk.bin` to both slots, kaeru to `expdb`, `tee-payload.bin` to
  `tee1`, the preloader to boot0, `FASTBOOT_PLEASE` in `misc`, then a reboot.
  That is `UNLOCK_TO_FIREOS6`'s plan step for step. **Read from amonet's
  script, not measured through firebreak's own payload.**
- The one step firebreak adds in front is the boot0 header clear. biscuit's
  script writes the preloader late and leaves the old one in place until then,
  so a stop part way through leaves a Dot that starts a preloader its chain
  cannot follow, and only the eMMC short reaches that. With the header gone
  first, the same stop leaves the bootrom, which is what every other route
  here rests on. amonet-crown v2.0.1's `main.py` added that step for this
  reason -- "should the script stall" -- with the same `EMMC_BOOT` and zeros
  over 8 sectors that `ClearBoot0Header` writes, so the step is amonet's own
  fix carried back to biscuit.
- After v2.0.1's chain the run waits for any fastboot rather than for a
  bootloader version. amonet v2 patches the stock LK and keeps its build
  string, so `lk_build_desc` cannot tell its fastboot from a locked stock one;
  `unlock_status` can, and the stage that follows reads it. A Dot that comes
  back locked there is left to the fastbrick, as it is on v1.1.0's chain.
- That stage writes amonet v2's own TWRP to `recovery` and restarts into it,
  which is what v2.0.1's `fastboot-step.sh` does. A restore leaves whatever
  `recovery` already held, so the Echo cannot be trusted to have a TWRP there.
- Measured on a Dot, 2026-10-26, from `stock 5.5.0.3`, which parked it in its
  bootrom in 3 min 49 s over 19 steps: `unlock fireos6` joined that payload and
  wrote amonet v2.0.1's chain through it in 38 s. boot0's header cleared first,
  the RPMB was already zero and skipped, the table was already stock and
  needed no action, and the writes took `tee2` 10 s, both LK slots 5 s, kaeru
  2 s, `tee1` 6 s and the preloader 8 s. amonet's fastboot answered 8 s after
  the reboot, the gate matched, v2's TWRP went in, and TWRP was up 19 s later.
  The whole root to Fire OS 6 8146 took 5 min 16 s, against 6 min 05 s for the
  same pair through amonet v1.1.0.
- That run measures the gate's string. An amonet v2 Dot in its own fastboot
  reported `63cb91b-20221007_072309`, which the step that follows proves,
  because it wrote the TWRP rather than restarting alone.
- A run that finds no Echo runs the bootrom step again, without the erase. A
  run stopped inside amonet's payload leaves the Echo there, and the payload
  never restarts. The resume used to send every MediaTek port the payload's
  reboot command, `0xf00dd00d` then `0x3000`, and the Dot came back as its
  bootrom within 5 seconds; it now joins that payload instead, which costs no
  reboot and works whatever boot0 holds.
- On macOS, a run stopped 12 seconds into amonet's `tz` write resumed this
  way: amonet found the bootrom 4 seconds after the run started, and the root
  finished.
- From Linux, with boot0 erased, the resume continued after 30 seconds, twice,
  with no one touching the Dot. From macOS the bootrom gives one window per
  power-on: after `adb reboot` from TWRP it appeared 4 s later, stayed 40 s,
  and then showed nothing on USB for the 2.5 minutes watched. Only a replug
  opened another window.
- So a resume started inside that window needs no replug: a Dot was
  replugged, and a resume started 8 s after its bootrom appeared took that
  port. The reset command had reached the bootrom first, and the handshake
  still went through. A resume started after the window closes asks for the
  replug.
- A run stopped while amonet sends its payload, before the payload runs,
  leaves the bootrom inside its write command, waiting for the rest of the
  payload's words. The reset command reaches it as data. amonet's handshake
  sends `0xa0` and waits for `0x5f` with no limit, and the bootrom echoes a
  word only after 4 bytes, so 3 reads in 4 wait out amonet's 5-second
  timeout. Stopped 0.3 s into a 0.8 s send, about 12 KB were left: 12 hours
  of handshake. The run had disabled the watchdog, so only a power cycle
  clears it.
- So the handshake gives up after 10 seconds without `0x5f`, where a live
  bootrom answers in about 2 ms. The run then asks for a replug, waits for
  the port to go and come back, and tries again. Under `short` it stops
  instead: a replug without the short brings up the preloader, and the
  Enter that ends amonet's short prompt has already been sent, so a second
  short would get no countdown. On a Dot stopped that way, the resume asked
  for the replug 10 s after it took the port, and the same run finished the
  root to the bboe TWRP in 9 min 6 s.
- The replug gets its own 10 minutes for the port to return, and the step
  stops 30 minutes after it starts. Without that cap, a bootrom that answers
  `0x5f` and nothing more is reopened every 10 seconds for good: a probe run
  reached 51 handshakes. On the erase route nothing else ends the run.

## Which device is plugged in

- Before a run that installs a target, firebreak names the device and refuses
  a target made for another one, before it downloads anything. `report`
  prints the same, and does not refuse. `write-test` does not check: it
  writes only `cache`, by name, on any device.
- It counts every USB device from MediaTek (`0e8d`) and Lab126 (`1949`), and
  from Google and HTC only the IDs an Echo uses: TWRP's `18d1:d001` and
  `18d1:4ee2`, and fastboot's `0bb4:0c01`. A phone in Android's generic
  `mtp,adb`, `18d1:4ee2`, still counts.
- With `ANDROID_SERIAL` set, only the USB device with that serial counts.
  Without it, two Echo devices that name two different devices name none.
- In fastboot it asks `getvar product`, which needs no authorization:
  `BISCUIT` or `RADAR`.
- Elsewhere it reads the USB product string, `iProduct`, which the host has
  even when adb answers `unauthorized`. Fire OS sets it to
  `ro.product.model`, and TWRP to its own model. biscuit is `AEOBC` in Fire
  OS 5 and 6, `Echo Dot (2nd Gen)` in v2.0.0's TWRP and bboe2, and `Echo Dot
  2nd Gen` in v1.1.0's TWRP 3.2.3. radar is `AEORD` and `Echo (2nd Gen)`.
  The vendor and product IDs are the same on both, so they cannot tell them
  apart.
- macOS reads `ioreg -a -l -p IOUSB`, Linux `/sys/bus/usb/devices`, and
  Windows `DEVPKEY_Device_BusReportedDeviceDesc` through PowerShell, which
  gives no manufacturer. Each read `AEOBC` from a Dot on Fire OS 6, the macOS
  one with adb `unauthorized`, where `adb devices -l` gives no model. The
  read took about 0.05 s on macOS and 0.8 s on Windows. radar's strings are
  read from its images, not from a radar.
- When no USB product names the device and adb answers in a recovery, it asks
  `ro.product.device`. One radar's TWRP 3.7.0_9-0 gave only `Echo` on USB, so
  without this a run on it waited for a name that never came.
- A device that matches nothing, or no device, is let through: the checks
  before each write still guard it. The bootrom and the preloader name no
  product, so an Echo that shows no light is left to the bootrom step's own
  check.
- Two devices can have a target of the same name: `stock`, and the default
  when no target is named. Then the device found chooses which one runs. Until
  one is found, the run waits, as it waits for an Echo, and says once that an
  Echo that shows no light never names one. It never guesses: each unlock
  writes a preloader made for its own device, and nothing here has run one
  device's preloader on another. A target name that only one device has is
  checked as above.
- An Echo in its bootrom names no device on USB, and carries the answer in
  its own flash: `lk_a` and `lk_b` hold `product`. So where the target name is
  one two devices share, a run that reads `bootrom` reads that bootloader
  before it chooses the target. It joins a payload that
  already holds the bootrom, and starts one where none does. Such a run was
  going to exploit that bootrom anyway, so the read costs nothing: the chain
  step joins the same payload rather than starting another. The read happens
  before the target is chosen, so a run that ends in a refusal, as `unlock
  fireos5` on a radar does, has run the payload before it refuses.
- Nothing in the cache names the Echo any more, and nothing on the command
  line does either: `--device` is `short`'s alone. A bootloader that names no
  product, or a partition table that does not read, leaves a run with no name,
  and it stops rather than take one from the person running it. Two Echo
  devices swapped between runs are each named by their own flash. `short` is
  the exception because where the test point is differs by device, and the run
  has to say that before any bootrom answers.
- In fastboot, the report also prints `antirback_pl_version`,
  `antirback_tee_version` and `antirback_lk_version`.
- The report shows only the first 4 characters of a serial number. Amazon's
  start with a prefix that may name the device type: `G090` on every biscuit
  seen here.

## A Dot on emOS

- EchoMuse's emOS replaces Fire OS's boot image with its own init. It runs no
  adbd, so adb and fastboot see nothing. Its init offers a root shell on a
  USB serial port instead: `1949:2007`, named `EchoMuse` and `emOS`, with the
  Dot's serial number. Measured on a Dot with emOS 0.10 on amonet v2.0.0.
- That shell's `/init recovery` reboots into the bootloader's TWRP, and the
  port goes away within a second. From v2.0.0's TWRP, 20 s later, the root
  continues as from amonet-twrp. `stock` takes the same path: from emOS
  0.10 on amonet v1.1.0 with TWRP 3.7.0_9-bboe2 it restored 8146 in 3 min
  3 s.
- Finding the port by USB ID needs pyserial, so the probe runs a child that
  imports it. It runs only when adb lists no Dot.
- A port that will not open, as on Linux without the udev `tty` line, stops
  the run with the rules and the commands that add them.
- A program that has the port open keeps firebreak out. On macOS, with
  EchoMuse's wizard tab still open in Chrome after it installed emOS 0.10,
  2026-10-12, pyserial's open failed with errno 16, `EBUSY`. The run had
  printed Linux's udev commands, which do not apply. So `EBUSY` reads as
  busy. The udev commands are Linux's only, so any failed open off Linux
  reads as busy too. Windows was not measured. The message names the
  wizard's tab.
- The child opens the port and sends a newline. A prompt ending in `#` gets
  `/init recovery`. One ending in `password:` stops the run: EchoMuse's
  dashboard sets that password, and the user types the command or clears
  it. Nothing that matches in 5 seconds stops the run too.
- pyserial opens a port raw. A port left to echo, as a terminal opens one,
  feeds the shell its own output and every command returns 127.

## An Echo that shows no light

- A Dot whose preloader runs but never starts LK shows no light and offers
  no fastboot: only `0e8d:2000`, the preloader, for about a second every
  30 seconds. That cadence is biscuit's. Its boot0 is intact, so only the eMMC
  test-point short reaches the bootrom. `short` runs the bootrom step for
  it, with no erase.
- The preloader port is not only a failure sign. Measured on a radar on
  2026-10-27, every ordinary boot offers `0e8d:2000` for about 0.8 seconds
  before LK takes over, on three boots, one of them with a button held. It
  enumerates as `MediaTek` `MT65xx Preloader`, with no serial number, so the
  port tells one Echo from another no better than it tells a radar from a
  biscuit.
- Holding mic-mute at power-on latches that radar into a preloader loop: the
  same 0.8 second window every 3.74 seconds, over 41 appearances in 150
  seconds, with a dark ring and no adb. The button is read at start-up only,
  so the loop continues after it is released, and a power cycle with nothing
  held ends it. amonet v2.0.0 added this as its "Preloader USBDL recovery
  mode". The radar it was measured on runs amonet's own preloader, not
  Amazon's, so whether a stock Echo offers it is unread.
- Neither the gesture nor `FACTFACT` sent to the preloader reached fastboot.
  mtkclient's four ways to crash a preloader into the bootrom all failed on
  Amazon's: each came back as the preloader. Its register writes echoed but
  took no effect.
- The bootrom step takes only a port it can identify as the bootrom,
  `0e8d:0003`, vendor and product both, and skips a stock preloader's, which
  `short` reports as a missed short. amonet would otherwise take whichever
  port appears first.
- Before it resolves its plan, the step reads the first 512 KiB of `lk_a` and
  `lk_b` over the payload, so the wrong device hears that first. Each LK
  names its fastboot product as `\0product\0NAME\0`: `BISCUIT` in every
  biscuit LK, stock Fire OS 5.5.0.3 to 8149 and amonet v1.1.0's and v2.0.0's,
  and `RADAR` in every radar LK, each by 0x4c000. The step refuses an LK that
  names another product, and refuses when neither names `BISCUIT`. One LK is
  enough, because the plan writes `lk_a`, then `lk_b`, so a run cut short
  leaves the other whole. It looks only on a table whose CRCs pass; a torn
  table continues to the plan, which refuses it.
- Nothing else in this step can tell a biscuit from an Echo (2nd Generation):
  its table has biscuit's 16 partitions and the same bootrom answers. Without
  the check, `short` on a radar that shows no light would write biscuit's
  amonet v1.1.0 chain, preloader included.
- A radar reached its bootrom on 2026-10-27, so the sentence above is no
  longer read from the code alone. Both are MT8163, and amonet ships one
  `brom-payload/build/payload.bin` for both, 20060 bytes, byte for byte the
  same. That payload ran on the radar and reported `BROM USBDL is enabled`,
  which `check_brom` reads from devinfo at `0x10206060`, bit 8. Not every Echo
  is said to have that bit clear: the Echo Show 5 of either generation, and the
  Dot 3rd Generation, are reported to have no bootrom USBDL at all, which would
  make a brick on those permanent. The fuse is per product, so a shared SoC
  settles nothing on its own.
- That report does not hold for the Dot 3rd Generation as written.
  kamakiri-donut v1.0.0 drives `0e8d:0003` over raw USB, and its own
  `main.py` clears boot0's header before it writes anything so that a stalled
  run reaches the bootrom without a short. A bootrom that answers is a brick
  that can be undone. Nothing here has read a donut's fuse, so what the bit
  says on that device is still unknown, and the claim is kept above rather
  than deleted.
- kamakiri-donut v1.0.0 starts its payload through USB control transfers, not
  through the bootrom's write-words command. It sends a CDC `SET_LINE_CODING`
  of 11 bytes where the descriptor declares 7, reads nine bytes of the
  configuration descriptor to trigger it, and repeats the pair to walk a saved
  pointer one byte at a time. That gives it the bootrom's `cmd_da` as an
  arbitrary read and write, which places its stage1 at `0x100A00`. A serial
  port sends no control transfer, so pyserial cannot carry this step whatever
  else is reshaped. The GCPU route is no way around it: a donut refuses the
  engine's own registers, measured in
  [measurements.md](measurements.md#an-echo-dot-3rd-generation-in-its-bootrom).
- Its payload is two stages, where amonet ships one. stage1 answers
  `\xa1\xa2\xa3\xa4` and takes two framed commands: `0x4000` loads stage2 at
  `0x201000`, and `0x4001` jumps to it. stage2 then answers
  `\xb1\xb2\xb3\xb4` and speaks amonet's payload protocol, including
  biscuit's `0x1003`, `0x1004` and `0x5000`. It adds `0x3001` to kick the
  watchdog and `0x6000` to set the fastboot flag. So the two stages cost a
  loader, not a protocol.
- One write of `0x22000000` to `0x10007000` does not hold donut's watchdog as
  it holds biscuit's. The kit writes `0x1971` to `0x10007008` every second
  before the exploit, and kicks through `0x3001` after every batch of blocks.
- `bin/lk-donut.bin` holds `DONUT\0` at `0x2c0c4`, after an RSA exponent, and
  holds no `\0product\0DONUT\0` anywhere. So the product check above would
  refuse a donut rather than name it, where amonet's own `bin/lk.bin` holds
  `\0product\0BISCUIT\0` for biscuit and `\0product\0RADAR\0` for radar. The
  kit writes this LK byte for byte for 6009 and later, so it is a stock donut
  LK. All four readings are from v1.0.0's files on 2026-11-02; no donut ran
  them.
- It reads ports from pyserial's USB list and opens only the bootrom's, where
  amonet opened every port to see it. On Linux the preloader's
  `/dev/ttyACM*` is `dialout`'s, and the udev rule covers only `0e8d:0003`,
  so amonet's way would never see a missed short.
- It remembers each port by name and USB ID, and checks every port on each
  poll. The bootrom usually reuses the preloader's name: on Linux both are
  `/dev/ttyACM0`, and macOS names a port by its USB location. A port whose ID
  cannot be read yet, or that will not open yet, is looked at again on the
  next poll.
- The probe reads those two from the USB list the device names come from, not
  from a serial port: `ioreg` on macOS, `/sys/bus/usb/devices` on Linux and
  `Get-PnpDevice -PresentOnly` on Windows. So it needs no pyserial, and on
  Windows it sees a bootrom whose VCOM driver is missing, where a port listing
  would show nothing at all. The read is kept for a second, and for 10 on
  Windows, where it starts PowerShell.
- A preloader is not a failure. Every ordinary boot offers `0e8d:2000` for
  about 0.8 seconds before the bootloader takes over, so a run that polls
  through a reboot sees it in passing, and a 2-second poll misses it as often
  as not. What it says is that boot0 holds a preloader, which is true of a
  healthy Echo. Only a preloader that keeps coming back and never starts a
  bootloader is the failure, and nothing can tell those apart in one read. So
  `preloader` is a state a walk waits through, and a walk stuck in it for 10
  minutes is what names the test point.
- Which Echo a bootrom belongs to comes from the Echo, not from the cache.
  Once the payload runs, `bootrom` reads the partition table and up to 512 KiB
  of `lk_a` and `lk_b` over it, and takes the device whose product the
  bootloader names, as the chain write already does before it writes anything.
  Measured on a Dot, 2026-10-29: 2 s, against 5 s for the handshake and the
  payload before it.
  A run that finds a payload already holding the bootrom takes the same read,
  so a hold is reported by what the bootloader says rather than by what the
  last run wrote down. A marker's name is then a fallback for the words a
  message uses before any read, and nothing more: it never becomes the device
  the run believes in, so the bootloader read corrects it rather than arguing
  with it. A device the run was **given**, by a USB product or by `short`'s
  `--device`, is another matter: a bootloader that names a different one stops
  the run with nothing written, because something it was told is wrong. Two
  Echoes
  with erased boot0s and one marker between them land here, and the swapped one
  is named by its own bootloader. A torn table names no Echo, and the run
  carries on with what it had.
- Knowing a payload is already running is not in the probe, because that needs
  the port opened and its signature read. `bootrom` does that itself, and the
  markers keep their own job, which is to say what boot0 holds.
- A payload is asked what only a payload can answer: `bootrom` switches the
  eMMC to the user area through it and reads block 0, which has to end
  `55 aa`. No shorter question tells a payload from a bare bootrom, because a
  bootrom answers payload bytes of its own: measured on 2026-10-29, it
  returns each byte sent, plus one.

  ```text
  sent      f0 0d d0 0d | 00 00 50 00 | 00 20 10 00 | 00 00 00 04
  received  f1 0e d1 0e | 01 01 51 01 | 01 21 11 01 | 01 01 01 05
  ```

  A running payload answers that same read with `14 00 9f e5`, the first word
  of payload.bin, twice over. So a check on the length or the shape of an
  answer passes on a bare bootrom, and the handshake's own rule, that a
  bootrom echoes a byte as it is, does not hold before the handshake.
- Switching that area is not only how the probe asks. `bootrom.read` switches
  no area of its own, so a payload another run parked can be sitting on boot0,
  where a read of the partition table would read boot0's first sectors
  instead. The probe leaves every payload it finds on the user area, as the
  join that reads a table has always done.
- The probe takes 1.07 s where a payload answers and 5.03 s where none does,
  both measured. The bootrom pays the port's own 5 second timeout, because
  the read waits for a block that never comes.
- A whole payload frame sent at a bare bootrom costs the handshake behind it.
  Three runs on 2026-10-29 did that and then failed their first handshake, `no
  0x5f answered 0xa0 within 10 seconds`, taking 76 s, 79 s and one power cycle
  where a handshake alone takes about 5 s. The cost was time, not corruption:
  each frame asks for 516 bytes a bootrom never sends, so it waits out the 5
  second read timeout, and a bare bootrom only answers for about 40 seconds
  per power-on. `handshake()` already flushes the port on every attempt, so
  the bytes themselves were never the problem.
- One byte costs nothing, which is what the run sends. A payload frame starts
  with the magic `f0 0d d0 0d`, so `0xf0` is the first byte of a real command.
  A bare bootrom echoes it as `0xf1` and the frame is abandoned there; a
  payload is still waiting for the other three magic bytes and says nothing,
  so the run writes the rest and the command completes. Either way the port
  sits on a frame boundary and neither state is left mid-command.
- Measured on a radar on 2026-10-30. At a bare bootrom `0xf0` came back as
  `0xf1` in 0.0002 s, five times out of five, and the handshake straight after
  those five probes took under 0.01 s. At a payload holding the bootrom
  nothing came back for the full 0.5 s window, the completed frame read block
  0 correctly, and a normal join after it still worked, so the hold survived.
  0.2 ms against a 0.5 s window is a margin of 2500, which is why calling a
  live payload dead is not a practical worry.
- The short is `firebreak short` alone. A target run never asks for
  a short: an Echo that shows no light is parked in its bootrom by
  `firebreak short` first, and the target run that follows joins the
  payload waiting there, by the same hold a `stock 5.5.0.3` restore leaves. So
  one command asks for the test point, and a run that writes firmware never
  waits on an operator with a wire in hand.
- `short` reads better with `--device`. Nothing on USB says which Echo is
  dark, and the run has to name the test point before the owner shorts it, so
  that name can only come from the command line.
- Where the test point is differs by device, and nothing else about the short
  does: both are MT8163, both answer the same bootrom, and amonet ships one
  payload for the two. So `short` refuses nothing. A device whose test point
  no one has found, which today is radar, and a run that names no device at
  all, are both told that firebreak cannot say where to short it, and the run
  waits for a bootrom anyway. Nothing is written while it waits, and the
  bootloader read names the Echo afterwards, so `--device` only picks whose
  test point to describe.
- amonet takes any port that appears after it lists the ports at start. So
  `short` asks for the short only once amonet logs that it is waiting, and
  sends no reset first: an Echo plugged in earlier would be in that list and
  never count as new.
- The short must be off before the payload starts the eMMC, its first act.
  Nothing before that touches the eMMC, and the handshake disables the
  watchdog. So the run holds amonet at its "Remove the short" prompt, counts
  down 5 seconds, then lets it continue.
- amonet's first write clears boot0's header. Under `short` its bootrom step
  notes boot0 as erased just before each write, after amonet's first boot0
  check, as the erase path notes it before the erase. A run that stops before
  that leaves boot0 intact. A run that fails after it is resumed by a plain
  rerun, which reads the bootrom it finds rather than any record of it.
- The bootrom step logs the error for a port it still cannot open after 1
  second, once, and the run shows it at once. udev can set a new port's mode
  a moment after it appears, so a first failure alone means nothing. A
  missing udev rule or ModemManager would otherwise hold a `short` run
  silent for 10 minutes.
- The payload starts the eMMC once. With the short still on, either it never
  comes up and amonet times out waiting for it, or the bootrom step's first
  read, the partition table's `55 AA`, fails. Both stop the run before amonet
  writes anything, and a new short starts over.

## One command per entry point

`firebreak fastboot`, `firebreak twrp` and `firebreak bootrom` reach one state
and stop there. A target walks from wherever the Echo is to a goal, which makes
testing a single stage mean reaching its state by hand first.

- Each walks the states it can act on and waits out the rest. Where adb
  answers, that is a reboot; where it does not, the device's own gesture, which
  it waits for without a limit as a target run does. Any other state stops the
  run rather than guessing: `twrp` refuses a booted Echo with no root, because
  the recovery a reboot would reach is Amazon's, not a TWRP.
- A state that does not move for 10 minutes stops the run, as it does for a
  target. The gesture is the exception, because it waits on a person.
- Nothing on USB is a wait, because that is what a reboot reads as. In a run
  that erased boot0 itself it is not: that Echo starts nothing but its bootrom,
  so no fastboot and no recovery can ever appear, and `fastboot` and `twrp`
  stop rather than wait for a state they cannot reach. A later run has no
  record of the erase and waits instead, until the bootrom appears and says so
  itself. The way out of a bootrom is a chain, which `unlock` and `stock`
  write.
- The macOS read is not always steady. On 2026-10-29 the IOUSB plane left a
  live bootrom out of three reads over about 30 seconds and then listed it
  again by itself, 207,395 bytes against the 210,142 that hold it. **Why is
  not known**: opening and closing its port, `fastboot devices` and
  `adb get-state` were each tried afterwards and none of them reproduced it. A
  run that reads `none` where a bootrom is plugged in has met this.
- `fastboot` writes nothing. `twrp` writes nothing either where the bootloader
  is already unlocked: it restarts into the recovery that is there and takes
  it where a TWRP answers, because an unlocked Echo usually holds one. No TWRP
  in 90 s means that recovery is not one, and the run says to power cycle and
  come back with `--force`, which writes the device's own TWRP as the unlock
  route does. A locked Echo has no such hope: `twrp` runs the fastbrick there,
  which unlocks it and erases everything. `bootrom` clears boot0's header, or
  erases boot0 from fastboot, which is what leaves an Echo startable from its
  bootrom alone.
- No command but `short` takes `--device`, and a run that cannot name the Echo
  stops rather than ask for one. Every state these commands write from names
  the device itself: a fastboot answers `getvar product`, a TWRP gives its
  model on USB or `ro.product.device` over adb, and a bootrom carries the
  answer in `lk_a` and `lk_b`. One radar's TWRP 3.7.0_9-0 gave only `Echo` on
  USB and that prop named it, which is the nearest any device here has come to
  saying nothing. So an Echo in one of those states that still names nothing
  is one nothing here has measured, and a name off the command line would
  write to it on a guess. `short` is the exception because the Echo it is for
  shows no light and names nothing until its bootrom answers. Where the name
  is only wording, as it is for a hold that writes nothing, a run says `Echo`
  and carries on.
- Every message names the Echo from what the run has read, which for these
  commands is a device and never a target: a run with no target says `Echo`
  where it knows the name, as `firebreak short --device biscuit`
  did. A prompt also names it when the question is asked, not when the table
  of states is built, because `twrp` builds that table before `walk` reads
  the Echo at all.
- A run probes a bootrom port before it handshakes at one, because a payload
  holding the bootrom answers no handshake: the run would spend the 10 second
  limit and then ask for a replug, which on an intact boot0 starts the
  firmware instead. `write-test` probes for the same reason, since it meets a
  live payload where the short always met a bare bootrom.
- A test that joined a hold leaves it held. The bootrom write test reboots
  the payload at the end, which is right where it started one, and wrong
  where another run was holding the bootrom: with boot0 intact that reboot
  starts the firmware, and the next run would find no hold to join.
- Guessing the wrong state first is what used to be expensive, and it is why
  there was a marker at all. Measured on a radar on 2026-10-30: a handshake
  sent at a payload holding the bootrom fails after its 10 seconds, and the
  join that follows fails too, so the hold is gone and only a power cycle
  brings the bootrom back. The split frame above never makes that guess. It
  reads the state off the wire in one byte and is harmless in both
  directions, so there is nothing left for a marker to say.
- `bootrom-held` is gone, and the measurement above is what removed it.
  Removing it had been tried on 2026-10-29 and put back, because the probe of
  the day sent a whole frame and cost the handshake behind it. A file that
  says which of two states an Echo is in is only as good as the last run that
  wrote it, and a stale one changed what a run did to an Echo; the wire does
  not go stale.
- Nothing passive tells the two apart. Both answer `0e8d:0003`, because the
  payload keeps the bootrom's own USB stack, so no id, string or descriptor
  differs. The one passive signal is the watchdog: a bare bootrom's serial
  port goes away about 40 seconds after a power-on, where a payload's stays,
  which a run could only use by waiting those 40 seconds every time.
- That radar recovered itself. The run was already waiting when its first
  handshake failed, and the bootrom came back 405 s later, so the chain went
  through with nothing typed again.
- `bootrom` waits for the Echo as the other two do, rather than reading the
  state once. Nothing on USB is what a reboot reads as, and an erased boot0
  only answers for 40 seconds per power-on, so a run that is already waiting
  catches that window where a run that refused would have to be typed again
  inside it. It says what it is waiting for: boot0 erased means power it on.
- A target run waits through a preloader too, and `route.py` had to be taught
  it: on an ordinary boot the preloader shows for about 0.8 s, which closed
  the open progress line mid-wait, reset the restart counter that catches a
  boot loop, and read as a state the run had reached. A preloader that is
  still there after 10 minutes names the test point instead.
- Neither write runs on a device firebreak cannot write a chain back through.
  `bootrom` clears boot0 only where a bootrom unlock exists, and `twrp`
  unlocks only where a fastbrick does, both checked before the question is
  asked. An Echo Show 8 is the case that matters: it has no chain and no
  fastbrick, and firebreak names it from its TWRP, so without the check
  `bootrom` would clear its boot0 and leave nothing able to put a preloader
  back.
- An erase has to be called, not passed. `await_bootrom_port` takes the erase
  only as a flag, to tell a preloader that appears from a failure, so the
  caller runs it before it waits, as the unlock route does. A run that passes
  the erase and never calls it waits for a bootrom on a Dot still sitting in
  fastboot: measured on 2026-10-29, 133 seconds with nothing erased and
  nothing restarted. The wait after an erase is a minute, as the route
  allows, not the half hour a run that waits on a person gets.
- The restart is `restart_refusals()` and nothing else, the same two commands
  the unlock route sends after its write, so no image is sent. Calling the
  unlock stage with `carries_twrp=False` would not do: that argument means the
  route carried no TWRP into `recovery`, so it writes one without reading the
  bootloader at all.
- Nothing can read `recovery` from fastboot to settle it in advance, so trying
  the restart is the only cheap way to find out: see
  [Unlock: amonet v2](#unlock-amonet-v2) for what that fastboot does and does
  not answer. The unlock route writes instead, because it needs a known TWRP
  rather than any TWRP.
- So each asks before it writes, says what the write does, and stops when the
  answer is not `yes`. Ctrl-C at the question stops it too, and leaves the Echo
  as it was. `--force` answers in advance. Nothing else in firebreak
  asks a question, so a run whose input is not a terminal cannot be answered:
  it stops and names `--force` rather than waiting on a prompt no one sees.
- `bootrom` reaches a TWRP first where adb answers, as `twrp` does, and clears
  boot0's header from there. So a rooted Echo takes one command rather than
  two, and the only states it refuses are the ones no route runs from: a locked
  fastboot, which cannot erase boot0, and a booted Echo with no root, whose
  recovery is Amazon's.
- `bootrom` ends with amonet's payload holding the bootrom, and nothing in the
  cache records that. The next run probes the port and joins the payload it
  finds, so a second `bootrom` run reports the hold rather than reaching the
  bootrom again, as `fastboot` and `twrp` report a state they are already in.
  Which device it is does not come into holding a bootrom -- one payload runs
  on both, byte for byte -- so a run reads the name out of the bootloader in
  flash rather than asking anyone for it.
- `boot0-erased` is gone too, and with it the last thing firebreak believed
  about an Echo it had not read. It said what boot0 holds, which an Echo that
  is powered off cannot be asked, so it could only ever be a claim about the
  last Echo some earlier run touched. What it bought was a name and a wording
  before the Echo was reachable, not a decision: a bootrom that appears
  answers for itself, on its USB id and then in its flash. A run keeps the
  fact in memory for as long as it is the run that erased boot0, so its own
  errors still say `Only boot0 was erased.`
- `bootrom` reads which Echo it holds from the bootloader in flash, and a
  target run reads the same way before it chooses its target:
  [Which device is plugged in](#which-device-is-plugged-in) says why, and what
  that read costs.
- `write-test` takes the bootrom route when one of those markers is there,
  rather than asking for a short of its own.
- The three stages `twrp` reuses read their device from the target, which these
  commands do not have. They read `current_device()` instead: the target's
  device where a target names one, and the name read off the Echo where none
  does.
  `tests/test_needs.py` resolves that call, so a stage's downloads are still
  checked against its code.

## Recording a run

- [The simulator](simulator.md) runs firebreak against a simulated Dot, and
  records every command for a diff.
- `--verbose` prints each `adb` and `fastboot` command and its exit status
  with the time, and each state the run sees. The 2-second polls are not
  printed.
- In verbose mode, or when the output is not a terminal, a stage prints a line
  when it starts and when it ends, with no running count. In verbose mode
  both lines start with the time. Output that is not a terminal also gets
  no download meter. Either would fill a log with `\r`
  frames.
- A running stage shows a Braille spinner where its mark will go, and a
  finished stage prints ✅. Where the output's encoding cannot represent them,
  the spinner is `|/-\` and the mark is `done`. On Windows that is output
  redirected to a file: since Python 3.6 a console reports UTF-8 whatever its
  code page.
- A finished line is at most 79 columns, so it does not wrap on an 80-column
  terminal. That caps a stage label at 36 characters.
- Steps are numbered from 1 in each run, against the total that
  [Targets](#targets) says how the run counts. The restore stage is 16 of
  them, and 17 from a rooted Echo, with the reboot into recovery. A restore
  write whose target already reads back the right md5 ends `skip`, in place
  of its seconds.
- A plan carried out from TWRP prints one line per stage, not one per write,
  so a root from stock prints 11. The boot0 clear, the table and every write
  but TWRP and the preloader share one line, such as
  `write amonet v1.1.0-bboe`. TWRP and the preloader keep their own lines,
  the preloader because a stop after it cannot be undone. Other writes in a
  row that share a label share a line, such as the table's primary and
  backup. A shared line ends `skip` only when every write in it was skipped.
  `--verbose` still prints every command. The bootrom step still prints one
  line per write.
- Each stage's estimate is an upper bound: the slowest time measured for it on
  any host, plus 5%, rounded up to the next 15 seconds, or the next 5 seconds
  under a minute, over roots on macOS, Linux and Windows 11. An estimate is
  only ever raised. It is in seconds, as the time beside it is. On 2026-10-12
  Fire OS 5's first boot took 319 s on Linux against 240 s, and its /system
  108 s on Windows 11 against 100 s. A Fire OS 6 slot took 119 s on Linux, 1 s
  under its 120 s. A Mac took 272 s, 41 s and 85 s. One case is left out: a
  first run on a computer that finds the Dot already in TWRP waits up to 35 s
  more for the system image.

## Reporting a problem

- `report` collects firebreak's version, the host, the state, the build,
  the eMMC, the partition table with each name's node, and the kernel's own
  mmc lines. The version matters because `uvx firebreak@latest` can run a
  newer firebreak than the run that failed.
- Only a recovery answers all of that, so it starts one. An Echo already in a
  recovery is left alone: the one a failed run left is the safe place to be.
- From fastboot it asks with `fastboot oem reboot-recovery`, then with
  `fastboot reboot-recovery`. Measured 2026-10-25 on a Dot unlocked with amonet
  v2, LK `63cb91b-20221007_072309`: the oem command answers
  `FAILED (remote: 'unknown command')`, and `fastboot reboot-recovery` answers
  `Rebooting into recovery OKAY`, in TWRP 20 seconds later. Every `short` run
  measures the oem command on amonet v1.1.0's LK, `f379dba-20170906_000423`.
  The oem command goes first because a MediaTek LK can carry `reboot-recovery`
  out by writing `misc`'s boot control block, where the slot's priority and
  tries live, and nothing here measures whether this one does. A `stock` run
  that followed one skipped its `misc` write, which a write skips only when the
  partition already matches the image, so that Dot's `misc` still held what
  stock holds. That is as far as this is measured.
- The two spellings are one command. `fastboot reboot recovery` and
  `fastboot reboot-recovery` both send `reboot-recovery`: the host validates
  the target itself and rejects an unknown one without sending anything, read
  on fastboot 37.0.0, which answers `usage: unknown reboot target xyzzy`. So
  the radar's reading, `OKAY` in 0.076 s on `63cb91b-20221007_073612` with the
  recovery up 24 s later, and the Dot's, 0.463 s on
  `63cb91b-20221007_072309`, measure the same device command on two devices.
- Both arrived in the same fastboot. Android 9's `fastboot.cpp` takes
  `reboot [bootloader|emergency]` and holds no `reboot-recovery` at all;
  Android 10's takes `bootloader`, `recovery` and `fastboot` as targets and
  carries the command as well. So this step needs a fastboot from
  platform-tools r29 or newer, where the start-up check asks only for `-S`,
  which every release back to r19 has. An older host fails the command itself,
  and the stage reads that like a refusal from the device: the message then
  names the + button, and says the Echo's fastboot took neither command, for
  what is the host's age.
- A refusal the next command recovers from is dropped; `lk_build_desc`, which
  every report names, says which commands a bootloader has. Both failing prints
  what each said and asks for the + button. Ignoring those statuses cost that
  Dot's report: 3 minutes of waiting, then "most likely in Amazon's recovery"
  for a Dot still in fastboot. A non-zero `adb reboot recovery` is reported but
  stops nothing, since a reboot over adb can lose its reply after the Echo acted.
- `system_a` is the reason it exists. Fire OS 5's image is 805,257,216 bytes
  against a 805,306,368-byte partition, so the write has 48 KiB of headroom
  and nothing checks it. Build 8149's report showed only a mismatched md5.
- Wear comes from sysfs where a part reports it, and the erase count only
  from the kernel log, which reaches back about 3,000 seconds, so uptime is
  printed beside it. `cid` and `serial` are left unread, and GUIDs and the
  Echo's serial are masked: the run sets `ANDROID_SERIAL` to the Echo it picks,
  and the mask reads it.
- The kernel log's mmc lines are its last 60, and the card's first line is
  read on its own, so a log that still reaches the boot says so even after
  60 later lines.
- Each answer the report parses into claims comes behind a marker of its own,
  because adb cuts the tail: `sgdisk`'s table, `/proc/partitions`, the `by-name`
  listing and the kernel log's two reads. One that does not arrive whole is
  printed as it came, or not matched at all, rather than parsed into claims
  about which names point nowhere. The other answers are printed as they came. A
  failed system write discards the image's first slice and keeps the record of
  its size, which is the number a report is run for.
- The report reads the Echo's state without the root run's probe, which stops
  on a partition table it cannot read: a damaged table is the case a report
  is run for. Any recovery is left alone, and one that is not TWRP stops the
  report rather than being restarted. An Echo that runs Fire OS without root
  is not restarted either, because its recovery is Amazon's. An unlocked
  fastboot is restarted into its recovery, which holds Amazon's until a root
  run writes TWRP; when no adb recovery answers within 3 minutes, the report
  says that is the likely reason. The Echo is left
  in its recovery afterwards, and the report ends by saying so.
- `write-test` separates the card, the cable and the host, which a failed
  install's md5 cannot. It writes one pattern over two paths that share no
  hardware: into `/tmp`, which is RAM, for adb and the cable with no eMMC in
  it; and from the Echo to its own `cache`, for the card with no USB in it.
  The eMMC leg writes the file the USB leg verified, so both carry the same
  bytes, and it is skipped when the USB leg proved nothing.
- It writes over `cache`, which holds nothing the Echo needs, so a
  part-written `system_a` stays as evidence. `unlock fireos5` does not format
  `cache`, so the filesystem this test leaves is the one the Echo boots with.
  The pattern is not zeros, because a card that writes nothing passes a zero
  test. It is every byte value followed by a
  word, so nothing a transport mangles goes unnoticed, and its odd length makes
  a slice written at the wrong offset hash differently.
- `cache` is formatted **first**, and small enough that its own blocks end well
  before the pattern starts, so the writes stay raw, like the `/system` write
  they stand in for, nothing is mounted while they land, and a run stopped part
  way leaves an Echo that still boots. The layout is pinned rather than inherited,
  because the boundary has to be an input: `-J size=4 -N 8192` with `-O
  ^sparse_super,^resize_inode -E packed_meta_blocks=1` puts the primary
  superblock, the group descriptors, the bitmaps, the inode tables and the
  journal inside the first 6.11 MiB of a 784 MiB cache, measured, against a 16
  MiB margin. `^sparse_super` also puts a backup superblock in every block
  group, at 128, 256 and up to 768 MiB (mke2fs 1.47), and the pattern overwrites
  those. The filesystem still mounts on its primary, and the last format writes
  all of it again: a filesystem over all of `cache` but its last 1 MiB.
- A write that does not answer in 30 minutes leaves `cache` as it is.
  `dd` may still be writing on the Echo, and a format under it could leave a
  filesystem that reads as fresh and is not. The one already there ends
  before the pattern starts, so the Echo still boots, and a rerun formats it
  first.
- `e2fsck` will not catch it if that boundary is wrong. With the default
  layout the journal is one extent at 12.33-28.33 MiB, and after overwriting
  from 16 MiB `e2fsck -fn` passed all five passes on a filesystem missing
  12.3 MiB of its 16 MiB journal: the journal's superblock survived, and its
  body is not checked on a clean filesystem. A mount, a write, an unmount and
  a second `e2fsck` are what prove a journal works.
- A test that cannot run must not read as a card that failed. So the digest
  comes back behind a marker, the writing `dd`'s errors are kept, and a
  refused `umount`, a target that is not a block device and a format that did
  not happen each say so: the read-back names the node it wrote, and a file in
  TWRP's RAM `/dev` would match itself. The reverse holds too: a `dd` that
  cannot write the card ends with a marker of its own, which blames the card.
  Each skip says which of its four reasons it was. The whole command is one
  line with no quotes, or Windows loses it.
- Measured on bryce in TWRP 3.7.0_9-bboe2: 128 MiB over USB at 20 MiB/s, then
  768 MiB written and read back at 18 MiB/s, both digests matching.

### A cache with no filesystem

- An Echo whose `cache` holds no filesystem roots fine and then cannot boot.
  `fs_mgr_mount_all` fails in init's `on fs`, so `post-fs-data` and
  `class_start main` never run: `zygote`, `netd` and `installd` have no
  `init.svc.*` property at all, while every `class core` service is up. So the
  Echo answers adb as root, `su` works, `/system` is mounted and read correctly
  -- and `sys.boot_completed` never arrives. It reads like a bad `/system` or a
  slow first boot. The reason is in dmesg, not logcat: `e2fsck: Bad magic
  number in super-block`, then `fs_mgr: Failed to mount an un-encryptable or
  wiped partition`, then `fs_mgr_mount_all returned unexpected error 255`.
- `unlock fireos6` wipes cache and `stock` formats it. `unlock fireos5`
  formats userdata
  only, so a cache damaged before a run survives it.
- `write-test` runs the test through the bootrom instead where a marker says
  a bootrom holds the Echo. `firebreak short` is how to reach that
  on one that shows no light and so has no recovery. It reads the last 64
  blocks of `cache` three times, then writes 1, 34 and 64 blocks and reads each
  back, then writes the first read back. 34 is the partition table, the first
  bootrom write of a short run; 64 is the most one command carries.
- v2.0.0's payload answers a block write only when the eMMC took it, and the
  same silence follows when the bytes never all arrive. So after a write with
  no answer the test sends a 4-byte memory read, `0x5000`. A payload that
  answers took the whole write and refused it, which blames the card; one that
  answers with the write's own acknowledgement was slow; one that stays silent
  is still waiting for bytes, or for the card.
- After a write the card refused or answered late, the test puts `cache`'s
  blocks back. After one the payload lost track of, it cannot, and says to
  unplug the Echo: the pattern stays at the end of `cache`, which holds nothing
  the Echo needs.
- A late answer is followed by the ping's own 4 bytes. When they do not come,
  the ping filled the end of a write that lost bytes on USB, so that blames
  USB, not the card.
- It reads the table first and skips a table that is not intact, so a stale
  `cache` entry cannot point the writes at another partition.
- Measured on a Dot from Windows 11, with boot0's header cleared so no short
  was needed: three reads agreed, writes of 1, 34 and 64 blocks read back
  unchanged, and `cache` read back as it was.

## The host

- Python 3.9 or later, because stock macOS's `/usr/bin/python3` is 3.9.6. CI
  runs its `--help` on that interpreter, and `tests/test_python_floor.py` checks
  that the package uses no module, attribute or import 3.9.6 lacks.
- The standard library only, so the script runs on stock macOS, Linux and
  Windows. adb and fastboot are the only external tools.
- A Python from the Microsoft Store writes under `%LOCALAPPDATA%` into its
  own `Packages\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0\LocalCache`
  copy, and the processes it starts do not see that copy. Measured on Windows
  11 with Store Python 3.13.14, alone and under a uv environment: Python saw a
  file it wrote, and a `cmd` it started in that folder did not, by a relative
  or an absolute path. The fastbrick's `fastboot` loads its image from the
  cache, which fits one user's run on that Python: each of its 10 flashes
  exited 1 at once.
  The run stops when its Python, or the one its environment was made from,
  is under `WindowsApps`. It names `uvx --managed-python`, or for a pyz, a
  python.org `python.exe` by its full path or `uv run --managed-python
  --no-project python`. It does not name `py`: the launcher lists the Store
  Python too, and `py -3.13` ran it on that host.
- Do not pipe a `fastboot` read into `head`. The closed pipe stops the host
  part way through the transfer and leaves the rest of the device's answers
  queued, so the next command reads the previous one's output: after a cut
  `getvar all`, 2026-10-29, `fastboot fetch` printed `partition-size` lines
  and `getvar product` answered with bytes that decode to nothing. The queue
  drains by itself over the commands that follow, and the link then answers
  in step again. No reboot and no replug were needed.
- On a terminal, `ERROR:` lines are red and warnings yellow. `NO_COLOR`,
  `TERM=dumb`, a pipe or a file turns that off. On Windows only Windows
  Terminal (`WT_SESSION`) gets color; the old console prints the escape codes
  as text. A blank line separates one kind of message from another.
- adb must be 1.0.36 (platform-tools r24) or newer: 1.0.32 answers
  `wait-for-recovery` with `unknown host service` and passes `shell -n` to the
  device. Ubuntu 22.04 and 24.04 ship 1.0.41. fastboot must accept `-S`, as
  every release back to r19 does. Every run checks `adb version` and
  `fastboot --help` for `-S`, the stock target included, because a route to
  stock can pass through fastboot. Old releases, run with no device, set
  these floors.
- Downloads go to `$XDG_CACHE_HOME/firebreak` (default `~/.cache/firebreak`),
  or `%LOCALAPPDATA%\firebreak` on Windows. The script moves what the old
  `overdub-firmware`, `overdub-root` and `overdub-stock` directories hold into
  it before it reads the cache, so an interrupted downgrade's marker
  survives. A name already in the new directory stays in the old. Each
  is checked against a pinned SHA-256 before use and on every run. A stock
  build's extracted images go to `stock-<device>-<build>`, named for the
  device because a build number does not name one build: biscuit's OTAs and
  radar's share numbers while shipping different firmware, and a block-style
  OTA keeps a `system.img` whose sidecar hash matches, so the other device's
  image would have been written with nothing to catch it. A folder from
  before that keeps its old name, is never read again, and holds its images
  until the cache is cleared. The amonet
  trees unpacked from the two zips are not, and neither is the system image
  built from Fire OS's.
- The system image's directory is named after the zip's hash, so a new zip
  builds a new image. Its `md5` file is written last and synced with the
  slices before the directory is renamed into place. It names the image's
  md5, its 4 KiB blocks and its slice count, and the script trusts a directory
  only when all three are there and every slice starts with the gzip magic. It
  rebuilds otherwise, so a directory from a firebreak that wrote one
  `system.img.gz` is rebuilt, and one from overdub's `dot_firmware.py`, which
  writes the same slices, is used as it is. If the md5 read back still fails
  after the last try, the script deletes the first slice, which works even
  when another process holds the rest open.
- Each stage names the downloads it uses. A run fetches those of the stages
  on the route from the Echo's state to the target's goal, and no others. A
  `stock` run that finds TWRP fetches only the build. A run to
  `unlock fireos6` from v1.1.0's TWRP does not fetch Fire OS 5.
- `tests/test_needs.py` checks each stage's downloads against its code, for
  every target. It reads the source of the stage and of each firebreak
  function it calls, and collects the downloads passed to `fetch` and
  `unpack`. It runs nothing. It decides an `if` only when the condition has
  no call, such as a check on the target's goal; otherwise it takes both
  branches. A stage must name every download its code always makes, and
  nothing else. The one exception is v1.1.0's zip in the LK check, below,
  which a stage may name.
- amonet v1.1.0's zip is a need only where the Dot still runs v1.1.0's LK.
  On amonet v2's TWRP the LK check matches v2's `lk.bin` first, so a run to
  `unlock fireos6` from stock fastboot does not fetch it. Were `lk_a`
  to match neither, the check would fetch it itself.
- Every unlock from stock fetches amonet v2.0.1's zip, because the fastbrick
  payload for the Echo's bootloader is in it. The bootrom step names it too:
  an Echo whose `boot0` is erased cannot be revived without it. amonet publishes
  it only as an XDA attachment, which refuses an unattended download, so the
  zip has a second source that a run takes first, and the thread in a browser
  is the fallback. That keeps the route unattended while the first source
  answers.
- The first source gets 8 seconds, where a source of last resort gets 60. The
  60 is a socket timeout rather than a deadline for the whole transfer, so it
  bounds a stall and not a slow link. A refusal, a 403 and a 404 all come back
  at once; only a network that drops the packets waits out the timeout, and
  that wait lands in front of the browser the run falls back to.
- A zip's unpacked tree lives under the name its `Download` carries, and
  `unpack` rebuilds it only when that directory is missing. Re-pinning a zip
  that keeps its old directory name therefore downloads the new archive and
  continues using the old tree. v2.0.1's name carries a `-2` for that reason.
- A download sends firebreak's own `User-Agent`. Cloudflare answers
  `Python-urllib` with a 403 and the body `error code: 1010`, which bans a
  request by its browser signature. Amazon's CDN, GitHub and PyPI all serve
  that agent as well, so every download sends it rather than only the ones
  that need it.
- The run downloads nothing while it waits for an Echo it has not seen. That Echo
  can be another device, or can need nothing. An Echo that waits where the next
  state is known starts the downloads in a background thread: an unmodified
  Echo, booted, comes back in its own fastboot after the gesture, and amonet
  v2.0.0's fastboot comes back as its TWRP. So the downloads overlap the
  gesture.
- `boot-root.zip` may come through the browser, so the background thread never
  fetches it. The main thread fetches it before the other downloads, so the
  one step that can need the user comes first and does not land in the
  gesture's instructions. The ordering still holds now that the browser is
  only a fallback: it stops mattering when no download needs a browser at all.
- The run names the device before it starts that thread, and again before the
  first stage. A device plugged in after the run started is then refused
  before the route's downloads. The probe of a rooted Fire OS 5 Dot downloads
  nothing: it compares `recovery` against TWRP 3.7.0_9-bboe2's pinned size and
  SHA-256, and a recovery that is not that one needs no name of its own.
- The main thread waits for that thread's locks half a second at a time.
  On Windows, Ctrl-C does not interrupt a blocking lock wait, so one long wait
  would ignore it until a 397 MB download ended.
- The downloads are at most about 476 MB. With the unpacked trees and the system
  image, the cache holds about 1.3 GB.
- Before each stage, the script waits for every download on the route and
  checks it. A bad download then stops the run with the Echo unchanged. A route
  can end before the goal: emOS reboots into a recovery the run names only
  when it sees it. The next stage then downloads the rest.
- The downloads run one at a time, in the route's order, so the first stage's
  come first: amonet v2.0.0's zip for the fastbrick. Fire OS is 397 MB of the
  476, and one download filled the line at about 40 MB/s, so parallel
  downloads would only delay that zip.
- Nothing deletes a download, so a later run downloads nothing. A rooted run
  prints the cache's path and size and says it is safe to delete.
- The emOS probe and the bootrom step need pyserial, which a wheel or source
  install declares as a dependency, pinned to the same version the download
  holds. A test reads the pin out of `pyproject.toml` and checks it names that
  wheel, so the two cannot drift.
- A pyz carries no pyserial, so the run fetches the pinned pure wheel from
  PyPI when the host has none and imports pyserial from that zip: on this
  process's `sys.path` for the bootrom, on the emOS child's `PYTHONPATH`. A
  host with pyserial fetches nothing.
- A run asks PyPI once whether a newer firebreak exists, through
  update_checker, after it refuses root and before it starts adb, so a root
  run cannot leave a root-owned `~/.cache`. It prints a notice only when one
  does, with the way to upgrade: the latest release's `firebreak.pyz` for a
  pyz, and `uvx firebreak@latest` for any other run, as the README gives
  both. The command or link goes on a line of its own, outside the 79-column
  wrap, so a copied line holds all of it.
- The check keeps each answer for an hour. `--no-update-check` skips it. A
  child never checks.
- Each request has a 1 s timeout: with PyPI unreachable through a dead proxy,
  a run that stopped at the adb check took 1.2 s. The timeout does not cover
  DNS: with a resolver that never answers, the same run took 8.8 s. A failed
  check is also kept for an hour. The check catches every exception, so it
  cannot stop a run.
- The pyz bundles update_checker: its 2 modules and its `dist-info`, which
  holds the BSD-2-Clause notice. The build installs the pinned dependencies
  from `pyproject.toml` into `build/bundle` and zips `firebreak` and
  `update_checker*` from there. The bundled version is the pin, and a test
  checks the pyz holds it and no pyserial.
- The pyz has no `dist-info` for firebreak, so firebreak's version is
  `__version__` in `firebreak/__init__.py`. hatchling reads the package's
  version from there too, and a test checks the installed one equals it.
- The one child left is emOS's, `python -m firebreak _child emos`, with the pyz
  or `site-packages` on its `PYTHONPATH`. A path to re-run would not do: the
  wheel's Windows launcher is an `.exe`.
- `-m` puts a child's working directory first on its import path, so a child
  runs in the cache or amonet's `modules`, never where the run started. A
  `firebreak` directory there would replace the package, and a `serial.py` the
  pinned wheel. The child drops that entry before it does anything else. It
  checks the entry first: under `PYTHONSAFEPATH` Python adds no such directory.
- `adb get-state` reports `unauthorized` on stderr, so the script reads both
  streams.
- Without `ANDROID_SERIAL`, the run uses the one Echo on USB in
  `adb devices -l`, and ignore network adb: a rooted Echo with tcp/5555 open
  would make `adb get-state` answer `more than one device/emulator`.
  The run picks again on every poll, because each reboot drops the Echo
  off USB. With two Echo devices on USB the run stops and asks for
  `ANDROID_SERIAL`, which fastboot follows too.
- An `ANDROID_SERIAL` of the form `host:port` is refused: TWRP starts no
  Wi-Fi, and fastboot and the bootrom are USB-only.
- Windows 11's adb prints no `usb:` field, so there a line counts as USB unless
  its serial is `host:port` or `emulator-*`.

### What adb shell carries

- Binary from the host goes by `adb push`, binary from the Echo by
  `adb exec-out`, and `adb shell` carries only text whose shape is checked.
  The one exception is the `/system` write, which puts the image on `adb
  shell`'s stdin where a probe has shown that this host's adb carries 1 KiB
  holding 0x1a unchanged, and pushes it in pieces where it has not.
- A Windows adb reads its own stdin in text mode, where 0x1a ends the file, so
  `adb shell` truncates a stream there. Every other byte survives: NUL, CR, LF
  and EOT all arrive. Fire OS 5's system image holds 1,421,626 of them and the
  first is at offset 238, so 238 of 385,745,930 bytes reach the Dot and
  `gunzip` writes 12.
- Nothing reports it. A pipeline carries its last command's status, so `gunzip`
  fails, `dd` exits 0, and the only symptom is an md5 that does not match --
  which reads as a failing eMMC. On Fire OS 6, which has no `gunzip` at all,
  the same stream also exited 0 having written nothing. So each such command
  ends in a word of its own, `gunzip` touches a file when it fails, and `dd`'s
  own status ends the pipeline. The word is what the host accepts: silence is
  a failure, because `adb shell` can exit 0 whatever happened remotely, and a
  `dd` that cannot write the card would otherwise read the same as a stream
  that arrived.
- `gunzip` reports a damaged gzip but not a missing one. toybox 0.7.6 exits 1
  on a stream cut at 0x1a (`gzclose: Illegal seek`) and on a corrupted body
  (`gzread: incorrect data check`), so the marker appears for both. On input
  with no gzip magic it exits 0 and behaves like `cat`: 17,000 bytes in,
  17,000 straight out, which `dd` would then write to the partition. So each
  slice is checked for the gzip magic on the host before the cache is used.
  A build that did not finish never reaches the cache: it is renamed into
  place only after its `md5` file is written.
- A slice that arrived intact, by its md5 on the Echo, and still did not unpack
  can only be bad on the host. The sliced route deletes it and stops, so the
  next run rebuilds the image rather than failing the same way. The stream
  route cannot tell which slice failed, so it unpacks each on the host and
  deletes the ones that fail there too.
- Outbound is the same class. `adb shell` on Windows expands LF to CRLF, so the
  partition table, its backup copy and `misc`'s boot control block come off
  the Echo by `exec-out`, and each read checks its own length.
- `exec-in` is not the way round it. It is binary-safe, but it returns before
  the Echo has finished -- 4.7 MB still in flight at 16 MiB, complete and
  identical 5 s later -- and reports no status at all: `exec-in 'exit 7'`
  answers 0. On amonet v2.0.0's TWRP a pipeline through it either fails at once
  or hangs with nothing started on the Dot.
- Measured on one Dot from two hosts minutes apart, same recovery: Windows 11
  with adb 36.0.1 against macOS with adb 37.0.0.

### Linux permissions

- adb, fastboot and the bootrom's serial port need the Echo's USB devices open
  to the user. Ubuntu's `android-sdk-platform-tools-common` and
  android-udev-rules, which LineageOS points to, list other Lab126 products
  but not a booted Fire OS 5, `1949:0110`. Fire OS 6 is MediaTek's
  `0e8d:201c`, which Ubuntu's package marks as an adb device and a
  distribution without it leaves to root. Other guides for this Dot use
  `sudo`.
  These rules, in `/etc/udev/rules.d/51-echo-dot.rules`, cover every state,
  the serial port included:

  ```text
  SUBSYSTEM=="usb", ATTR{idVendor}=="1949", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="4ee2", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="d001", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", ATTR{idProduct}=="0c01", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="201c", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="tty", ATTRS{idVendor}=="0e8d", ATTRS{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  SUBSYSTEM=="tty", ATTRS{idVendor}=="1949", ATTRS{idProduct}=="2007", MODE="0660", GROUP="plugdev", TAG+="uaccess"
  ```

  Then `sudo udevadm trigger`. A rooted Fire OS 5 is `1949:0110` (adb alone, set
  in its boot image; the `mtp,adb` Fire OS 5 otherwise runs is `1949:0112`),
  a rooted Fire OS 6 8146 `0e8d:201c` (adb alone, one interface), TWRP
  `18d1:d001` and `18d1:4ee2`, fastboot `0bb4:0c01`, the bootrom
  `0e8d:0003`, and emOS's serial console `1949:2007`. The `usb` line for `1949`
  covers emOS's USB device but not its `/dev/ttyACM*` node, which is `dialout`'s
  without the `tty` line.
- `uaccess` covers a user at the machine; over SSH the user must be in
  `plugdev`. A new group reaches only new processes, and a running adb server
  keeps its old permissions: with the group added and the old server up,
  `adb devices` listed nothing. So after `adb kill-server`, `sg plugdev -c`
  runs a script with the group, without a new login.
- The script refuses to run as root: the downloads would belong to root, and
  the rules make `sudo` needless.
- It checks at start that the process has `plugdev`, even for a desktop user
  covered by `uaccess`, so the check is one question. A user not in the group
  gets the rules and the commands to add them, starting with `groupadd -f
  plugdev` because Fedora and Arch have no such group. A user in `/etc/group`
  whose shell predates that gets `adb kill-server` and the `sg` line. The `sg`
  line repeats the command as run, interpreter, path and flags included, because
  `./firebreak.pyz` is wrong from another directory.
- Without the rules adb lists the Echo as `no permissions`. When that lasts 5
  seconds and nothing else listed is usable, the run stops and prints
  the same rules and commands. A shorter spell is udev still setting
  permissions. A phone the user cannot open, beside an Echo that answers, does
  not stop them.

## Unlock: amonet v2

- A Dot in v2's unlocked fastboot reaches its TWRP with
  `fastboot reboot-recovery`, so every target starts it from there rather than
  asking for the + button, which is left for a bootloader that takes neither
  that command nor the oem one. Both are asked for, in that order, because
  `State.AMONET_FASTBOOT` is any unlocked LK that is not v1.1.0's: biscuit's
  older ones and radar's, where neither command is measured. The transition
  sits beside v1.1.0's fastboot in the table every target shares.
- The stage writes the device's own TWRP to `recovery` first, as amonet's
  `fastboot-step.sh` does, but only where `lk_build_desc` is the one the
  device's unlock declares as its own. Nothing else promises a TWRP is there:
  a `stock` run writes no `recovery`, and a chain write stopped between its
  reboot and its TWRP leaves whatever was there before. Nothing can read it
  back from there either, so the write is what makes the restart safe:
  measured on amonet v2's LK `63cb91b-20221007_072309`, 2026-10-29,
  `fastboot oem help` and `fastboot get_staged` both answer
  `unknown command`, and `fastboot fetch` reports no `max-fetch-size` at all.
  `getvar` gives each partition's size and type, which says nothing about its
  contents. The gate is what makes
  the write safe, because a recovery image must match the execution state its
  LK starts a kernel in, and that state is a property of the chain: see
  [Which TWRP each route needs](#which-twrp-each-route-needs). An unlocked
  bootloader the device does not declare takes the restart alone, as before.
- Only biscuit declares one, `63cb91b-20221007_072309`, which amonet v2's
  `lk.bin` reports because it patches Fire OS 6's LK and keeps its build
  string. A locked stock 8146 reports it too, so the string alone proves
  nothing; read in the unlocked branch, where a stock Dot cannot be, it does.
- What that fastboot reports, read whole on 2026-10-29 from a Dot on amonet
  v2.0.1: `unlock_status` `true`, `lk_build_desc`
  `63cb91b-20221007_072309`, `pl_build_desc` `531fa14-20170929_175430`,
  `kaeru-version` `2.0.0-gab93750`, `brom-cmd-dis` `0`, `rpmb_state` `1`,
  `unlock_code` `0x16aab1acfcfd6bec`, `max-download-size` `0x6d00000`,
  `boot-reason` `BCB`, `current-slot` `a`, `slot-count` `2`, `kernel` `lk`,
  `prod` `1`, `warranty` `no`, `secure` `yes`, the three anti-rollback
  versions, the serial, and a size and type for each of the 16 partitions.
  `secure` stays `yes` on an unlocked Dot, so it says nothing about the
  unlock.
- Two of those are leads nothing here has followed. `kaeru-version` names the
  payload amonet v2 writes to `expdb`, so a bootloader that reports one is
  amonet's rather than a stock LK that shares its build string, which is what
  the gate above works around. And `brom-cmd-dis` looks like the bootrom USBDL
  fuse that `check_brom` reads from devinfo over the payload, which would tell
  a device whose bootrom is reachable from plain fastboot. **A stock LK reports
  neither**, read on 2026-11-01 from a radar left in fastboot by `stock 8349`:
  each `getvar` printed the name with nothing after it and finished, which is
  how fastboot reports a variable a bootloader does not know. So the
  `kaeru-version` gate holds on the one stock bootloader it has been asked,
  and an amonet LK is the only one measured to answer. **Neither is read from
  amonet v1.1.0's LK, or from a device whose fuse is set**, so the values
  themselves are still one reading on one bootloader.
- `unlock fireos5` overrides the stage, because for that target v2's fastboot
  can be the way into the bootrom. Where the bootloader is the declared one,
  the run writes that TWRP and continues from v2's TWRP to write v1.1.0's
  chain in place, which is the route the section below prefers anyway, and
  boot0 is never erased. The erase and the bootrom are for an unlocked
  bootloader that is not amonet's, where no TWRP can be written safely and
  the bootrom does not care which LK is there.

- The unlock that holds a device's fastbrick payloads maps an
  `lk_build_desc` to its image, and `fastbrick.img` takes any other. On
  biscuit the map is `fastbrick-20221007.img` for `63cb91b-20221007_072309`
  and `41fb3ce-20221007_151724`, and `fastbrick-20260617.img` for
  `2c3569d-20260617_045829`. amonet's own map lists only the first of the
  20221007 pair; the second ships in 4310, 4313 and 4315, takes that image
  from the release below, and the default image does not unlock it. On radar
  the map is amonet-radar's own: `fastbrick-20220524.img` for
  `59779ca-20220524_183401`, Fire OS 5.5.5.4's LK, `fastbrick-20221007.img`
  for `63cb91b-20221007_073612`, `fastbrick-20260617.img` for
  `2c3569d-20260617_051433`, and the default for `41fb3ce-20221007_153017`.
  The stage unpacks the archive the map names for the
  bootloader in front of it, which is the unlock's own unless `payloads` say
  otherwise, so an Echo takes amonet-radar v1.0.1's payloads rather than a
  biscuit zip's.
- A `lk_build_desc` that is not one of the LKs the device's module lists, and
  is dated no earlier than the newest it does list, stops the stage before the
  flash. The fallback is a payload built for an older bootloader, which is
  sound for an older LK that ships no payload of its own and is a guess on one
  Amazon has not shipped yet: the flash goes to the `brick` target, which runs
  the payload rather than storing it, so a wrong one runs wrong code. The
  threshold is the newest date the device's own LKs carry, so adding an LK
  moves it, and an unknown LK on that same date is refused too: 4315's LK and
  8338's share a date with another, so one date can carry two bootloaders. A
  description the stage cannot read is refused as well, where an LK that
  reports none at all is the oldest kind and keeps the fallback. A device that
  lists no LK of its own refuses every bootloader, which is what a device
  whose payloads nobody has mapped should do.
- Each payload's tail is byte-derived from the LK it targets, which is how a
  mapping can be checked without a Dot. Of the 33,951 distinct 16-byte windows
  in `fastbrick-20260617.img`'s last 137,684 bytes, read at a **4-byte
  stride**, 33,950 appear in 8338's `lk.img`, against 30,851 in 8149's.
  `fastbrick-20221007.img`'s tail is the mirror of that. The stride is what
  makes these numbers reproducible: at every offset the same comparison gives
  135,411 and 135,403, which say the same thing in different units.
- The layout behind that, read on 2026-10-31 from the images alone, because
  both kits ship prebuilt images with no builder and no source. A specialised
  Fire OS 6 payload is a constant 114,294,904-byte sled, then the target LK
  from its offset 632, cut so the image ends at the hook. The hook is the only
  place the copy differs from the LK: 8 bytes at LK `0x21bec` on biscuit, where
  `01 46 02 48 78 44 ff f7` becomes `00 4c 20 47 84 ff ca 4b`, an
  `ldr r4,[pc,#0]; bx r4` and the literal `0x4bcaff84`. Nothing else in the
  137,596-byte tail changes. The Thumb-2 reading is by eye from the bytes.
- So rebuilding for a new LK is: slice the new LK, apply the same patch.
  biscuit's `63cb91b-20221007` and `2c3569d-20260617` LKs take the same offset
  over the same original bytes with the same replacement and the same branch
  target, four years and two LK sizes apart. radar's two do the same at its own
  offset. So within a device the hook is tied to Amazon's LK source rather than
  to a build.
- **A hook does not carry between devices.** radar's `2c3569d` payload patches
  **4** bytes at LK `0x21866`, `04 f0 d1 fa` becoming `8e f7 8e ec`, a
  retargeted `bl` rather than biscuit's load and branch. Different offset,
  length and shape. The byte pattern biscuit hooks occurs twice in every LK
  here and radar's second occurrence shares 30 of the 32 bytes that follow
  biscuit's, which is enough to look conclusive and is not. The sleds do not
  carry either: biscuit's and radar's specialised images agree for 16 bytes.
  Only the sled's length is shared.
- `fastbrick-20220524.img`, radar's for 5.5.5.4, is laid out the other way
  round: 5.5.5.4's LK sits at image offset 712, verbatim for 356,224 bytes to
  the end of the LK's own content, and the sled follows it. So the layout above
  is the Fire OS 6 one rather than the only one.
- The payload checks the device itself, and it is an IDME check rather than a
  USB one. It switches the eMMC to BOOT1, reads IDME and compares
  `device_type_id` against a literal of its own: `A3S5BH2HU6VAYF` in every
  biscuit image, `A7WXQPH584YP` in every radar one, the default included. Its
  strings are `Device type check:`, `Actual device type ID: %s`,
  `Expected device type ID: %s` and `Device mismatch, aborting!`, the last of
  which `stage_fastbrick` reads for. So the check guards
  against the wrong device and not at all against the wrong LK.
- Every image carries both `Mode: VBAR overwrite (%s handler)` and
  `Mode: PTR overwrite (func @ 0x%08lX)`. A specialised image has the LK copy
  and the function patch, so it takes the second; the default carries no
  bootloader at all, so it takes the first, overwriting the exception vector
  table instead, which is tied to no one build. That is a mechanism for the
  default crossing LKs, and it fits the default unlocking radar's `63cb91b`
  while failing biscuit's `41fb3ce`.
- Two things are still missing to build one here. The branch target
  `0x4bcaff84` is an absolute DRAM address that depends on where the overrun
  lands, so another device's needs its LK load address read or measured. And a
  wrong payload runs wrong code at the `brick` target, so trying one needs a
  device that can be recovered, which means the short.
- `fastbrick-20260617.img` unlocked a Dot on `2c3569d-20260617_045829`,
  2026-10-25, on the first flash of the run: a `stock 8344` left that
  bootloader, and the run that followed rooted the Dot. So the mapping that
  payload's tail predicted holds on a Dot.
- `41fb3ce-20221007_151724` takes its payload from amonet v2.0.0, where
  every other bootloader takes the unlock's own v2.0.1. v2.0.1 rebuilt
  `fastbrick-20221007.img` for the bootloader it is named after: 135,408 of
  the 135,416 distinct 16-byte windows in its last 137,684 bytes are in
  8149's `lk.img`, against 107,166 in 4315's, where v2.0.0's tail is close
  to neither. Measured: v2.0.0's unlocked a 4315 Dot on 2026-10-05 and
  again on 2026-10-25, one flash each; v2.0.1's left it to boot stock
  twice, after a flash that ran past 8 seconds as a started exploit does.
  The default image is no way out of that bootloader, which refused it 10
  times and by hand answers `the command you input is restricted on locked
  hw` after the send.
- v2.0.1 rebuilt the default `fastbrick.img` too, 129,517 bytes of the same
  114,294,816, and that one still unlocks: `beb022a-20211202_231918` on
  2026-10-25, rooted by `unlock fireos5` in 8 min 6 s. Its tail carries no
  bootloader, where a specialised payload's is a copy of one: 383 of its
  31,400 windows are in 5.5.5.4's `lk.img`, in either release. Fire OS 5's
  other three LKs take it too, last measured on v2.0.0's copy.
- A payload archive is unpacked once the stage knows the bootloader, so only
  a Dot on 4310, 4313 or 4315 fetches v2.0.0's 56 MB, and it does so while
  the Dot waits in fastboot. It is on the XDA thread like v2.0.1's, so it
  takes `browser=True`, the prefetch leaves it alone and the mirror answers
  first. That download is unmeasured: the run that took it had the archive
  cached.
- An LK older than Fire OS 5.5.0.3 reports no `lk_build_desc` at all, and no
  `pl_build_desc` either. The stage reads both and takes `bin/fastbrick.img`
  where neither answers, as amonet's own script does on an empty field.
  `pl_build_desc` is absent before 5.5.0.3 and present in every build after
  it, so an Echo that gives it without `lk_build_desc` is not an old
  bootloader, and the stage stops there without writing. `getvar` returns an
  empty string alike for a timed-out read, a variable the LK does not
  implement, and one it implements but leaves blank, so the stage cannot tell
  those apart. It reads both strictly, and a read that times out stops the
  run. A fastboot that answers an error without naming the variable still
  reads as an LK that does not implement it; nothing here measures what such
  a read looks like.
- The unlocked branch of `probe` still reads an empty `lk_build_desc` as
  `starting`, because amonet's own LK reports the field: an empty read there
  is an Echo part way through a boot, not an old bootloader.
- On a stock Dot that reported neither field, 2026-10-24: rooted Fire OS
  5.5.5.4 in 8m06s.
- A flash that returns means the exploit did not start, so it is retried, up to
  10 times. A flash still running after 8 seconds means the exploit is running:
  the script stops fastboot and leaves the Echo to reach TWRP.
- `eMMC-RO` or `Device mismatch` means the payload refused, and the Echo is
  unchanged.
- `fastbrick.img` unlocked a stock radar on its Fire OS 6 LK,
  `63cb91b-20221007_073612`, on the second flash of that run.

## Targets

| target | ends in | stops at |
| --- | --- | --- |
| `unlock fireos5` | amonet v1.1.0, TWRP 3.7.0_9-bboe2, rooted Fire OS 5.5.5.4 | amonet-fireos5-bboe-booted |
| `unlock fireos6 [--factory-reset]`, the default | amonet v2.0.1's TWRP, `boot-root.zip` on the Fire OS 6 installed; with `--factory-reset`, or no Fire OS 6 installed, on 8149 in both slots | amonet-booted |
| `stock [BUILD]` | Amazon's Fire OS 6 `BUILD`, 8149 when left out, the whole Echo erased | stock-booted |

- Each poll picks the stage for the state found and the target, so a run
  goes from any state to any target, a rooted Echo included. Every state has
  at most one stage per target, so a table does what a search over the
  stages would.
- Each stage in the table says how many steps it prints and which state it
  leaves the Echo in. Before each stage the run walks the table from the
  current state to the target's and shows that total. A walk that meets a
  state it cannot predict past, such as emOS, whose TWRP depends on the
  chain under it, shows `?`. An Echo that lands somewhere else is walked
  again from there, so the total changes only when the Echo surprised the
  run. Step numbers only go forward.
- amonet v1.1.0's own unlock and the bboe one write the same /system, boot
  image and Magisk. Only `recovery` differs, and the write from amonet v2's
  TWRP puts the target's own TWRP there. A Dot already on amonet's TWRP 3.2.3
  reaches `unlock fireos5` with that one write, from Fire OS through `su`, and needs
  no stock restore.
- Booted Fire OS 5 has no `md5sum`. So the probe and the write read
  `recovery` back through `adb exec-out` and `su`, and hash it on the host.
  On a Dot, 13,953,024 bytes took 2.2 s. One read, at the larger image's
  length, answers for both TWRPs.

### Install: Fire OS 6 with boot-root.zip

- With `--factory-reset`, the XDA procedure: in the device's amonet TWRP it runs
  `twrp wipe cache`, `twrp wipe data`, and `twrp install` of the OTA twice,
  with a reboot into recovery between, then `twrp install` of
  `boot-root.zip` and a reboot.
- It pushes the OTA to `/sdcard` before each install. A `/sdcard` on a
  `/data` that did not mount is TWRP's RAM: the push and its read-back pass,
  and the reboot loses the file.
- The XDA procedure flips the active slot with `bcbtool` between the two
  installs. The run does not: a TWRP install of an A/B OTA writes the
  inactive slot and makes it active, so the flip would make the second
  install write the same slot again. The run reads `bcbtool get_active`
  before and after each install, and stops unless it changed.
- A USB drop during `twrp install` ends `adb shell` with 255, but TWRP continues
  installing. On a radar, an install that lost adb 17 seconds in finished
  about 80 seconds later and changed the slot. So the run reads the slot only
  once adb answers and no `update_engine` runs, for up to 10 minutes. TWRP's
  `ps` is toybox, whose `CMD` column is the kernel's `comm`, cut to 15
  characters: `update_engine_sideload` prints as `update_engine_s`, so a
  count of the full name is always 0 and only the shorter name counts the
  install. Measured on a radar, 2026-10-17: each install lost adb, the first
  for about 3 minutes, and the run continued after each.
- The reboot into the rooted system is tried again only while `adb get-state`
  still says `recovery`. A dropped reply can arrive after the Echo has already
  acted on the reboot, and a second `adb reboot` then lands on a system that
  is starting. That interrupts the boot before it marks itself good, and each
  interrupted boot spends one of the boot control block's tries: after an
  `unlock fireos6` install a Dot's `misc` read 3 tries on slot b, so three of
  them would hand the Echo back to the other slot.
  `get-state` saying `device` means the reboot took, so the run continues. Two
  minutes of no answer at all is not a boot that is working, since the
  measured first boot is 24 seconds, so the run tries the reboot again.
- `boot-root.zip` patches both slots. It is an XDA attachment, and XDA sends
  a script a JavaScript challenge in place of the file. So before it touches
  the Echo, the run opens it in the user's browser and waits up to 2 minutes
  for it in `~/Downloads`, matched by size and sha256 `de49cc88...`. With no
  graphical browser, the run stops and says where to get the file.
- Once the cache holds the file, the run deletes its copies from
  `~/Downloads`. A new file with other bytes is deleted only when the browser
  recorded the attachment as its source.
- Safari unpacks a zip into `~/Downloads` and moves the zip to the Trash. So on
  macOS the run also looks in `~/.Trash`. When it opened the browser and took
  the file from there, it also deletes a new directory that holds exactly the
  zip's files.
- `boot-root.zip` goes the same way. On that radar it lost adb 2 seconds in
  and printed nothing, yet TWRP's log shows it patched both slots. So the run
  reads TWRP's log until the last `Installing zip file` is `boot-root.zip`'s
  and the `Updater process ended with RC=` line after it, and continues only on
  `RC=0`. The `adb reboot` after it also found no device and left the Echo in
  TWRP, so the reboot is tried 3 times, each after `adb wait-for-recovery`.
- `RC=0` alone does not show that the zip patched anything: it skips a slot
  with no `default.prop` and still ends with 0. The run also needs the zip's
  `slot _a: neutering ota updates` line, for the active slot, in TWRP's log.
- Without `--factory-reset` the run skips the wipes and both OTA installs. It
  mounts the active slot's `system` read-only, reads `ro.build.version.name`,
  then installs `boot-root.zip` over what is there. The zip finds its targets
  in any build: the adbd site by a byte pattern, the SELinux policy through
  `magiskpolicy`. A build with no OTA in firebreak's list stops the run with
  nothing written. The fastbrick takes only the LKs the listed builds ship, so
  the kernel boots under the amonet LK it was built beside.
- A slot with no Fire OS 6, as after the route from amonet v1.1.0, leaves
  nothing to keep, so the run installs the target's build as
  `--factory-reset` does. The OTA downloads in the background either way. A
  read without its `build-ok` marker stops the run: a USB drop must not lead
  to a wipe.
- Patching in place keeps userdata, and `boot-root.zip`'s own
  `init.fosflags.sh` keeps adb on where stock's turns it off once the Echo is
  registered. Measured 2026-10-18 on stock 8149 set up in the Alexa app: 78 s
  to rooted 8149, its saved Wi-Fi online 30 s after boot, still taking
  changes from the app. Its voice was not tested.
- Fire OS 6 without root for a minute after the install means
  `boot-root.zip` did not take, and the run stops. A single such read during
  the first boot does not stop it.
- No target shorts anything. `firebreak short` parks the Echo in
  its bootrom, and the target run after that writes the chain its resume
  writes and continues from that TWRP like any other.

## Back to stock: the stock target

`firebreak stock <build>` returns an unlocked Echo to stock Fire
OS 6 or Fire OS 5, to test a root from a clean start. `stock` is a target
like the others, so every state has a route to it: a rooted Echo goes to
recovery, amonet v1.1.0's fastboot gets amonet v1.1.0's TWRP, Fire OS 5's
locked fastboot gets the fastbrick, and in any TWRP the restore runs.

- Only `stock` takes a `BUILD`, and without one it installs 8149. The run
  downloads the build before it touches the Echo.
- Each device has its own builds. biscuit's and radar's OTAs share build
  numbers but not firmware, so the run picks the build only after it knows
  the device. radar has thirteen, and 8149, Fire OS 6574.1, is the newest of
  them and what both of its targets install when no build is named.
- Before it writes anything, the restore checks that the OTA's
  `ro.product.device`, without `_puffin`, names the device. A wrong entry in
  the build table would otherwise write one device's bootloaders on another.

- A restore ends with `adb reboot bootloader`, so the next run needs no button
  held. `--end-in-fireos` starts the Fire OS instead. Only `stock` takes it.
- 5.5.0.3 cannot reach fastboot that way: its restore ends in the bootrom over
  a serial port, so no kernel is left to carry a reboot reason. The preloader's
  own USB handshake takes `FASTBOOT` and answers `TOOBTSAF`, but a stock LK
  boots the Fire OS anyway, and the only boot-mode inputs a stock LK overrides
  on, `misc`'s command field and IDME's `bootmode`, each select recovery alone.
  So the restore instead holds the Dot in the bootrom: the payload writes the
  preloader and stops without its reboot, and the next run probes the port,
  joins that payload where it waits and writes a chain through it: amonet
  v2.0.1's, unless that run is `unlock fireos5`.
  A power cycle starts stock 5.5.0.3
  instead, since boot0 now holds its preloader. `--end-in-fireos` sends the
  reboot and starts Fire OS 5.
- A held payload is joined, never rebooted. Sending the payload's reboot
  command to get a fresh bootrom works only where boot0 holds no preloader. A
  held Dot has one, so that reboot starts Fire OS 5 and loses the hold:
  measured on a Dot, 2026-10-26, where the restore's own run rebooted the
  payload it had just parked. So a run opens each MediaTek bootrom port,
  probes it with a frame's first byte, and joins the one that answers nothing.
  A Dot that was powered off lists no port at all, and the wait for one to
  appear belongs to the step that handshakes, which probes each port it opens
  before it does: a hold whose port shows up late is joined there rather than
  handshaked. `short` skips none of this: a hold means the bootrom is
  already there, so asking for the test point and then handshaking at a live
  payload only ended in advice to unplug, which starts the firmware and loses
  the hold.
- Fire OS 5.5.3.1 to 5.5.5.4 carry Fire OS 6's anti-rollback versions, so
  they restore as Fire OS 6 does.
- 5.5.0.3's PL is 3, below RPMB's 5, so its preloader would stop at
  `version mismatch!`. Its restore leaves boot0 clear and reboots into the
  bootrom. There amonet v2.0.0's payload zeroes RPMB, writes the preloader and
  reboots. A PL 5 preloader that started in between would raise RPMB to 5
  again.
- Stock Fire OS 5 shows nothing on USB once it starts, so a Fire OS 5 restore
  ends after the reboot.
- Measured on a Dot, 2026-10-13: each Fire OS 5 build restored in about
  2.5 min, then read locked with its own `lk_build_desc`, and unlocked again.
- Measured on a Dot, 2026-10-14: 5.5.0.3 restored from amonet v2.0.0 in
  3 min 50 s. The bootrom came up 5 s after the reboot, and its RPMB began
  `AMZN`. The Dot read locked with 5.5.0.3's `lk_build_desc`. Its LK does not
  report `antirback_pl_version`. The fastbrick then unlocked it, and the
  default target rooted it in 8 min 4 s.
- The restore ends at stock-booted: the run waits for stock to start, which
  shows as `adb` answering `unauthorized` about 1.5 minutes after the reboot.
  An Echo already stock-booted, or in stock fastboot, has nothing to restore.
  An amonet v2.0.0-unlocked Dot booted into Fire OS 6 without root reads the same.
  So the message says "appears", then names the + gesture, which starts v2.0.0's
  TWRP, for a Dot unlocked with amonet v2.0.0. The condition comes first, so the
  owner of a plain stock Echo can skip it.
- The restore clears boot0 first and writes it back last, and notes boot0 as
  erased in between, as the downgrade does. So a restore stopped in between,
  then rebooted, is resumed through the bootrom step and amonet v2.0.1's TWRP,
  and restored again. The resume reads the bootrom it finds, not a record of
  the run that left it.
- A resume clears the TWRP states from the run's acted-on set, so a run
  that started in TWRP acts on TWRP again after the bootrom step.
- A bootrom that answers is reason enough on its own: a run resumes through it
  either way, and seeing it says nothing about what boot0 holds. Every other
  state does, since reaching it proves boot0 starts something, and that is
  where a run forgets its own erase.
- Both ways of carrying out a plan group the actions that share a label into
  one step, so a plan reads the same whether a recovery or the bootrom runs it.
  Two writes with one label are one step on purpose: a boot slot takes a header
  and a payload at different offsets, a table takes its primary and its backup,
  and the bootloader goes to both of its slots.
- A resume shows `?` for its first step and the whole total from its second.
  How many steps the chain takes is not known until the plan resolves, and
  that needs the Echo's partition table, which needs the payload the first step
  is joining or starting. So the run tells the bootrom step what follows it,
  and the step sets the total once it has counted the plan: the bars already
  opened, the plan's own, the wait for amonet's fastboot, the stage that
  starts TWRP, and the rest of the route. The erase route adjusts the total
  it was given, because a stage cannot say what follows it.
- Measured on a Dot, 2026-10-04: a restore stopped during the system write,
  then `adb reboot` from TWRP, then a rerun about 20 s later. The bootrom's one
  window was open when the rerun's bootrom step started, and amonet then
  skipped ports already present. The window closed, and nothing showed on USB
  for 9.5 minutes, until the cable was unplugged and plugged back in. The
  bootrom step then found it, and the run continued through amonet v1.1.0's TWRP
  and the whole restore to stock 8146: `[1/19]` to `[19/19]`, 13 min 50 s with
  the wait. The resume now takes a bootrom port already present, and asks for
  the replug only if nothing happens within a minute.
- A restore stopped without a reboot leaves TWRP running, so a rerun restores
  from there.
- The wait for stock to start has the 10-minute limit of any other state.
- A booted Fire OS 5 Dot without root gets `adb reboot recovery`. For the
  other targets that state is a boot still in progress, and the run waits.
- v2.0.0's TWRP mounts by name, under `/dev/block/platform/.../by-name/`, so an
  unmount pattern anchored on `/dev/block/mmcblk0` matched nothing there and
  the writes went to mounted filesystems. What is left mounted is named
  back, because a refused `umount` is otherwise silent and the Echo has no
  screen to look at.
- That TWRP carries two `dd` implementations which do not take the same
  operands: the one on the path answers `conv option disabled`. So the script
  uses `toybox dd` where it exists. TWRP 3.7.0_9-bboe1's `toybox dd`
  truncates at its `seek` offset, and the block device answers `ftruncate:
  Invalid argument`. So the one write with `seek` passes `conv=notrunc` to
  `toybox dd`.
- Measured on a Dot: from amonet-fireos5-bboe-booted in 3 min 11 s, `[1/17]`
  to `[17/17]`, ending when stock started, and 4315 in 4 min 9 s, which rooted
  back in 9 min 8 s. Run again on the stock Dot, it reported nothing to restore
  and downloaded nothing.
- `sgdisk`, `mke2fs`, `blockdev` and `md5sum` are looked for before the
  countdown, because `sgdisk` and `mke2fs` are not reached until after 1.6 GB
  has gone in.
- 4315 ships a block OTA in place of a `payload.bin`: `system.new.dat`
  with a transfer list, and boot, LK, TZ and the preloader as files in the
  zip. `system.img` is built from the list, which must be version 3 or 4
  and use only `erase`, `zero` and `new`, since the rest patch blocks this
  does not have. Its ranges must cover the image from 0, and no block may
  be written twice: Fire OS 5's own list erases the whole image and then
  writes over it, where 4315's erases only what it does not write. Only
  the `new` ranges are written, because the file is truncated to size
  first, and `system.new.dat` must end where the last of them does. A block OTA
  carries no hash per image, so they rest on the OTA's pinned SHA-256.
- The built `system.img` stays in the build's own directory for the next
  run, which saves the 20 to 30 seconds it takes to build. It is built as
  `system.img.part` and then renamed, and its SHA-256 goes in
  `system.img.sha256`. A run reuses the image only when that hash matches,
  because an older run wrote the image in place, so a stopped run left one
  of full size with blocks missing.
- LK, TZ and boot are padded to a multiple of 4096 bytes. A write is
  checked over whole sectors, `n // 512` of them, and 4315's LK is 241,448
  bytes, so the check left the tail out and failed on a write that had
  gone in. A payload build's images are already whole blocks.
- Each OTA comes from Amazon's CDN, at the URL ftvdb lists for it, and is
  pinned by the SHA-256 of a copy that matched ftvdb's md5. The run does not
  ask ftvdb.
- Each `payload.bin` operation is read where it lies, so peak memory is one
  image plus one operation: about 1 GB, for the 768 MB system image.
- The manifest's own lengths are not trusted. A number cut short, a field cut
  short that returns fewer bytes than it declares, and a field of the wrong
  wire type each stop the run with the reason, rather than ending in a
  traceback or writing a short image.
- A passed check prints `ok` rather than the tick where the console cannot
  encode it, such as a legacy Windows code page, which would otherwise raise
  `UnicodeEncodeError`.

### The partition table

- amonet v1.1.0 renames the stock `boot_a` and `boot_b` to `boot_a_x` and
  `boot_b_x`, and adds its own `boot_a` and `boot_b` as partitions 17 and 18,
  cut from the end of userdata. The stock table is rebuilt from the Dot's own
  rather than from constants, so every offset and size is that Dot's.
- The backup table goes in before the primary: a run cut during the primary's
  write leaves it mixed, and the backup is what the next run reads instead.
- A table with no `_x` name is already stock and is kept: that is what makes a
  stopped run safe to repeat, and why v2.0.0's table needs no surgery.
- The kernel must reread the table before cache and userdata are formatted.
  Against the old one, `mke2fs` would size userdata to amonet's cut.
- The first run on an Echo saves that Echo's own table as
  `current-gpt-<serial>.bin`, and later runs keep it rather than saving the
  stock table over it.

### The writes

- boot0's header is cleared first. With no valid preloader the bootrom waits
  for a USB host instead of running anything, so a failure anywhere after it
  leaves an Echo that amonet's bootrom step can reach without opening the case.
  Forced on hardware: the bootrom appeared 4 seconds after the reboot and
  waited about 39 seconds, and amonet v2.0.0's bootrom step rewrote the whole
  chain in 22. The order of the bootchain writes is not what makes this
  survivable -- with the header gone, no slot is reachable anyway -- the
  bootrom is.
- `misc` gets zeros and, at 0x360, the boot control block amonet v1.1.0's
  bootrom step writes: `00 41 42 42 01 8f 00`. Slot a is then `prio 15 tries 0
  success 1`, and slot b is unused. Each slot byte packs `priority:4`,
  `tries:3` and `success:1`, low bits first.
- A zeroed `misc` is not safe. Stock's first boot starts slot a with a few
  tries and `success 0`, and each boot cut short spends one. On a Dot, a
  gesture during the first boot and the power-ons after it left slot a at
  `tries 0 success 0`. The preloader then reset about every 30 s with the ring
  dark, never starting LK, so neither the gesture nor `FACTFACT` reached
  fastboot. It did not fall back to slot b, whose tries stayed at 3. It took
  the eMMC short to get back. A slot marked good spends no tries.
- `tee1` and `tee2` are not slot-tied: every slot-tied partition takes a letter
  from `ro.boot.slot_suffix` and TEE takes digits, and amonet's bootrom step
  writes its LK to both slots unconditionally, but its TEE payload only to
  `tee1`. So they go backup first and
  primary last, rather than by slot.
- boot is padded with zeros to the size of `boot_a`, which both slots share, so
  no byte of amonet's boot image survives and the read-back covers the whole
  partition.
- The preloader is padded the same way, to boot0's size, which depends on the
  eMMC chip. [devices.md](devices.md#emmc-chips) has the sizes.
- TWRP answers `ro.product.device` only because amonet's TWRP sets it in its
  `default.prop`; a recovery ramdisk has no reason to carry it otherwise.
- A push and its read-back address different block devices, whose page caches
  are not coherent, so the cache drop between them is what makes the comparison
  mean anything.
- `adb push` to a node that does not exist does not fail: adbd creates a
  regular file in TWRP's RAM-backed `/dev` and reports success. A partition's
  read-back still catches that, because it reads the raw disk at the computed
  offset rather than the node -- but only after 768 MB has gone into a tmpfs on
  a 512 MB device. So the start sector is checked first, which also catches a
  number that means a different partition in the table the kernel still holds.
- boot0 is the one write whose read-back names the node it wrote, so there a
  regular file would match itself and pass. Hence the check that it is a block
  device. For the same reason the cleared header is counted twice, bytes read
  and bytes left non-zero: a read that returned nothing would otherwise look
  like a header that cleared.
- The skip compares a mebibyte of head first, which costs 0.07 s and is enough
  because a different build differs within a kibibyte or two. Only a partition
  that looks right pays for the full comparison, 13 s against the 80 s a write
  would take.
- A restore that follows amonet v2.0.1's chain skips more than one of those.
  Measured on a Dot, 2026-10-26, restoring 8149 from the chain the bootrom had
  just written: both table writes skipped, because that chain leaves the table
  stock where v1.1.0's leaves a boot-moved one for the restore to undo, and
  `tee2` skipped as well, because amonet v2.0.1's `bin/tz.img` holds Fire OS 6
  8149's TEE byte for byte over the image's length. Restoring 5.5.0.3 from the
  same chain writes `tee2`, whose TEE that image is not.
- A restored Echo has no Wi-Fi until it is set up in the Alexa app. To root it
  again, skip that setup: on Wi-Fi it can update to a build firebreak does not
  support, or away from the build under test.

## Each device

Every section above is the general process. This one holds what is true of one
device alone: the overrides its route takes, and what was measured on it.
Firmware values -- the builds, the bootloader strings, the eMMC chips and the
partition tables -- are in [devices.md](devices.md).

### Echo Dot (2nd Generation)

biscuit is where most of the process above was measured, and the only device
that declares a Fire OS 5 chain. The sections here are that chain: the three
TWRPs it decides between, the two routes into amonet v1.1.0, and the Fire OS 5
install it ends in. `unlock fireos5` is biscuit's alone.

#### Which TWRP each route needs

Three TWRPs run on a biscuit, and which one a Dot can run is decided by the
chain under it, not by choice. An LK starts the kernel in one execution state,
and a recovery image carries its own kernel, so the two must agree.

| TWRP | kernel | the LK that starts it | where it comes from |
| --- | --- | --- | --- |
| 3.2.3 | 3.18.19, arm64 `Image` | amonet v1.1.0's, which is Fire OS 5's `f379dba-20170906_000423` | `bin/twrp.img` in v1.1.0's zip |
| 3.7.0_9-bboe2 | 3.18.19-bboe, arm64 `Image` | the same | its own pinned download |
| v2's 3.7.0 | 32-bit `zImage` | amonet v2's, which is Fire OS 6's `63cb91b-20221007_072309` | `bin/twrp.img` in v2.0.1's zip |

- Amazon switched biscuit's kernel between the two: 5.5.0.3 and 5.5.5.4 carry
  an arm64 `Image`, and 8149 a 32-bit `zImage`. Each amonet release's TWRP
  matches the LK it ships with, so v2's cannot run on a v1.1.0 chain and
  neither v1.1.0 TWRP can run on a v2 one. Every LK here is itself 32-bit
  Thumb-2 code, amonet's two included, so the bitness that matters is the
  kernel's, not the bootloader's.
- bboe2 replaces 3.2.3 wherever firebreak can put it there: it moves 21.5
  MB/s against 5.1, and it returns `adb shell`'s exit status, which every
  device-side step of the Fire OS 5 install is judged by. 3.2.3 is left where
  it is for a restore, which needs neither.
- The stage tables in `route.py` decide which TWRP each route runs under and
  writes. They are the source, and a reading of them here would be a second
  thing to keep right, so this says only what they do not: bboe2 is on every
  `unlock fireos5` path, and on one other state, `amonet-fireos5-fastboot`,
  where the LK is v1.1.0's and the recovery there cannot be trusted, so any
  target writes a known arm64 TWRP to reach a TWRP at all.
- `amonet-twrp` and `amonet-twrp-boot-moved` are a pair, not a loop: a run
  takes one or the other, never both. `unlock fireos5` cuts amonet v1.1.0's
  partitions in, and `unlock fireos6` puts the stock table back on a Dot found
  part way through that. The chain under both is amonet v2's, so only the table
  differs.
- A booted Dot reaches a TWRP by one reboot: `amonet-booted` into v2's TWRP,
  `amonet-fireos5-bboe-booted` into bboe2's, and `rooted` into whatever
  `recovery` holds, which the route predicts as amonet's 3.2.3. `rooted` is the
  exception to the reboot: `unlock fireos5` writes bboe2 there through `su` and
  is then done.

#### From amonet v1.1.0 to amonet v2.0.0

- From amonet v1.1.0 the run carries out amonet v2.0.0's plan from either
  amonet v1.1.0 TWRP, in place of its zip, the XDA route from amonet v1.1.0.
  A rooted Dot first goes to recovery. The plan resolves against the Dot's
  table before anything is written, so a table that does not fit is refused
  with nothing changed.
- boot0's header is cleared first, and noted as erased, as the zip copy did
  and the restore does. From there to the preloader, any stop lands in the
  bootrom, and the resume writes amonet v1.1.0 and continues from its TWRP. A
  stock table under amonet v1.1.0's LK would not boot, so nothing is
  written before the clear.
- Then the table goes back to stock, as the zip's `restore_gpt` does, by
  the TWRP route below. Only `userdata` and the two appended partitions
  change, so every partition the plan writes keeps its node, and no reboot
  comes between.
- Then the TEE, both LKs, kaeru and the TEE payload are written and read
  back, and `misc` is zeroed, as the zip does. v2.0.0's TWRP comes after
  them, so they share one line, and the preloader is written last. The
  plan's RPMB zero, `FASTBOOT_PLEASE` and reboots are left out, as for
  v1.1.0's chain from v2.0.0's TWRP; the run reboots into recovery itself.
- amonet's own zip writes the preloader first. A stop after that leaves a
  valid preloader in front of a mixed LK and TEE: no bootrom, and maybe no
  LK, so only the eMMC short reaches it. The plan writes it last instead.
- Cut on a Dot after LK and before the preloader, by a reboot from the Dot
  itself: the bootrom appeared 4 s later, the same run's resume took it with
  no one touching the Dot, wrote amonet v1.1.0 and continued to amonet
  v2.0.0, 6 min 43 s in all. This TWRP has no `/proc/sysrq-trigger` and its
  `reboot` takes no `-f`, so the cut was a plain `reboot`.
- A resume without an erase or a short that sees the preloader,
  `0e8d:2000`, takes boot0 as intact: it stops the bootrom step, deletes the
  marker, and continues polling. On a Dot rebooted from Fire OS 6 with the
  marker set by hand, the run said so 2 s later and ended at
  amonet-booted, with nothing written.
- An amonet v1.1.0 Dot started in fastboot reads as stock-fireos5-fastboot,
  and the fastbrick leaves it in v2.0.0's TWRP on amonet v1.1.0's partition
  table. The probe reads that as amonet-twrp-boot-moved, and for
  `unlock fireos6` the run carries out the plan there first. The amonet v2 install
  itself stops if `boot_a_x` is still there, or if
  `sgdisk` prints no `userdata`.
- Fastboot cannot tell the two tables apart, and a stock Fire OS 5 Dot is the
  common case. So stock-fireos5-fastboot's stage plans for the stock table,
  as stock-fastboot's does. Where the probe then finds amonet v1.1.0's
  table, the step counter plans again from there.
- In v2.0.0's fastboot the run asks for the + button at power-on, which
  starts v2.0.0's TWRP, and waits for it without limit.

#### The TWRP route

Both installs from an amonet TWRP are one route: amonet v2.0.0's plan from
either amonet v1.1.0 TWRP, and amonet v1.1.0's from v2.0.0's TWRP.

- The plan resolves against the table on the disk, less the steps TWRP does
  another way: the RPMB, forcing fastboot, the reboots, and boot0's header,
  which the route clears itself. It writes zeros there, as the v2.0.0 install
  and the stock restore did; amonet v1.1.0's plan writes `EMMC_BOOT` and then
  zeros, and either leaves the bootrom no preloader. A table that does not fit
  is refused with nothing written.
- When the plan's table moves a partition it writes, the table goes in alone
  and the Dot restarts into recovery, because `BLKRRPART` is `EBUSY` while
  TWRP is up. The next run finds the table in place and writes the rest.
  Otherwise every partition the plan writes must be a block device of the size
  the table gives, or the Dot restarts into recovery with nothing written:
  a kernel holding another table would put a write by name in RAM.
- Then boot0's header is cleared, with boot0 noted as erased, then the table, the
  writes but TWRP, TWRP, and the preloader last. amonet v2.0.0's writes end
  with zeroing `misc`, as its zip does. amonet v1.1.0's route installs Fire
  OS 5.5.5.4 between TWRP and the preloader.
- The table is the layout's own bytes, both copies, written by `dd` and read
  back like the rest. The backup copy goes first, so a stop between the two
  leaves the old primary in front and the next run writes whichever copy
  differs.
- The backup copy lies at block 7651295 of `mmcblk0`; every other write goes
  to a partition's own node, near its start. bboe2's and v2.0.0's TWRPs carry
  a `dd` that answers `EINVAL` past block 4194304 beside `toybox dd`, which
  reaches it, and the writes take `toybox dd` where it exists. TWRP 3.2.3 has
  no toybox, and its `dd`, busybox's, reaches it. `losetup -o` reads 0 bytes
  there. So before anything is written, the route reads that block with the
  `dd` it writes with, and refuses a table it cannot reach.
- The layout also wipes `userdata`'s first blocks. This route leaves that out:
  amonet v1.1.0's step formats `userdata`, and amonet v2.0.0's installs wipe
  it.
- Measured on a Dot at TWRP 3.7.0_9-bboe2: `toybox dd` wrote the backup copy
  back over itself at block 7651295, 33 records out, and `sgdisk --verify`
  passed. `sgdisk --load-backup` of a layout's two copies, onto a loop device
  the size of the disk, gave both back byte for byte, but it adds a tool the
  route does not need. Its exit status proves nothing: on a file over 2 GiB it
  read the size wrong, did not write the backup copy, and exited 0.

#### Writing amonet v1.1.0 from v2.0.0's TWRP

- The run writes v1.1.0's chain and Fire OS 5.5.5.4 from v2.0.0's TWRP. The
  bootrom step stays for `short` and for amonet v2.0.0's fastboot, where no
  TWRP is up.
- The fastbrick appears to zero RPMB itself: its payload holds `Zeroing RPMB
  block 0...` and `RPMB block 0 cleared and verified`. If so, a Dot that has
  never seen amonet v1.1.0 needs no bootrom either. **This is read from the
  payload's strings, not measured.** Every Dot here already had a zeroed RPMB,
  and the bootrom step it replaces verified the zero where this route assumes
  it. RPMB is not readable from TWRP, so nothing checks it at run time. A wrong
  assumption here is the one failure on this page that costs the eMMC short.
- The table goes first, then a reboot, then the rest by the TWRP route above.
  Clearing boot0 before that reboot would land there.
- The chain is amonet v1.1.0's plugin plan (`docs/plugins.md`), less the steps
  this route does another way: the RPMB, forcing fastboot, and the reboots. A
  region that already holds its bytes is skipped, so a rerun resumes where the
  last one stopped. Measured from stock 8146: a run stopped during the first
  LK write, and the rerun skipped the four boot writes and `tee1`, wrote the
  rest, and the Dot booted rooted. It skipped the BCB too, which the stock
  install had already written. boot0's header is cleared again on every run
  that writes past the table.
- A run notes boot0 as erased only after the plan resolves and every node
  checks out, so a stop before that leaves the note unset and boot0 intact.
  The note lives in the run that makes it and dies with it, so a later run
  reads the Echo rather than inheriting either answer.
- Its writes use `toybox dd` with `conv=notrunc` where it exists, as the
  `stock` path does; the `dd` on the path refuses `conv`, and does not truncate
  at a `seek` without it.
- Each target is checked as a block device, at the length its table entry
  gives, before anything is written, boot0 included. A table that goes in alone
  is the exception: the run after its reboot checks them. `dd` to a name that
  is not one writes a file in RAM `/dev` that reads back and matches.
- The by-name bootloader nodes are decoys on both TWRPs, so the chain names
  `mmcblk0pN`. bboe2 repoints by-name `boot_a` at `boot_a_x` and v2.0.0's TWRP
  does not, so the boot image names `boot<slot>_x`.
- `lk_build_desc` does not say a Dot is unlocked. amonet v2.0.0 patches the
  stock LK and keeps its build string, so an amonet v2.0.0 Dot and a locked
  stock 8146 both read `63cb91b-20221007_072309`; `unlock_status` is in
  fastboot only. The `stock` target writes no `recovery`, so a restored Dot
  keeps the TWRP it had, and the probe would read that as amonet-twrp.
- A locked Dot cannot reach that state, so the reading above is a gap in the
  logic and not a route. Measured twice on a Dot restored to stock 8146 with an
  amonet TWRP left in `recovery`, v2.0.0's and 3.7.0_9-bboe2's:
  `fastboot reboot recovery` answers `OKAY` and then nothing appears on USB for
  90 s, in any mode. A locked LK refuses an unsigned recovery.
- The TWRP route and `stage_install_fireos6` still hash `lk_a` against amonet's
  `lk.bin`, amonet v2.0.0's then amonet v1.1.0's, and refuse the rest, so a
  chain write needs proof the Dot is amonet's rather than a build string it
  shares with stock. amonet v1.1.0's LK passes, so a part-written chain still
  resumes. When `lk_a` matches neither, `lk_b` is read too: the chain writes
  `lk_a` first, so a run stopped inside that write leaves `lk_a` torn and `lk_b`
  as it was. Both routes into the chain leave amonet v2.0.0's LK in both slots:
  its installer writes both, and so does the fastbrick, measured on a Dot read
  the moment its TWRP came up from stock. Every cached stock LK is 241664 or
  245760 bytes on Fire OS 6, and 360448 or 364544 on Fire OS 5, against amonet's
  359744 and 372368, so none can match. The check is defence in
  depth, not a fix for a reachable failure.
- The probe waits for `mtp` on every TWRP, not only amonet v1.1.0's. adb
  answers first, and the switch to `mtp,adb` re-enumerates USB, so a stage
  starting in that window reads truncated output with exit 255. So each
  device-side answer this route reads ends in a marker of its own, `sgdisk
  --print` included, because adb cuts the tail: a marker at the front leaves a
  cut line parsing as an empty, and therefore passing, result. A cut md5 is
  shorter than 32 characters, but a read that returned nothing hashes to a
  whole one, so the chain's reads and writes also require `dd`'s record count.
- v2.0.0's TWRP costs the install nothing. It returns `adb shell`'s exit status
  and has every tool the install needs, and `/system` took 81 s there, as under
  bboe2: `gunzip` and the eMMC are the limit, not adb.
- `misc`'s boot control block is written, as a read of block 1, 7 bytes patched
  at 0x160, and a write back, which is what v1.1.0's `reset_bcb` does. Leaving
  it inherits whatever ran before: after an `unlock fireos6` install a
  Dot read `00 41 42 42 01 af 3e`, slot b at prio 14 with 3 tries, a live
  fallback to the Fire OS 6 images an amonet v1.1.0 chain cannot boot. The boot
  image goes to slot a to match, not to `ro.boot.slot_suffix`, which here names
  the slot amonet v2.0.0 booted.
- Measured on a Dot: [measurements.md](measurements.md) has the figures.

#### Downgrade: amonet v2.0.0 to v1.1.0

- firebreak erases boot0, then opens the port whose USB product id is the
  bootrom's, so a port that was already there does not matter.
- The engine is the GCPU, `gcpu@10210000` in the device tree: a 4 KiB window
  that holds every register the exploit touches. Fire OS hands it to the TEE,
  which is encrypted, so the registers are read from the preloader instead.
- The preloader drives the engine with the same sequence, at `0x1d1bc` as
  Thumb-2. It names every `gcpu.Register` and gives `ACQUIRE_VALUES` and
  `SLOT_POINTER_VALUES`. `0x400`, `0xC48` and `0xC68` are computed, not
  literals, so a byte search misses them. The routines are identical in every
  cached preloader: biscuit's, crown's, and the radar one amonet-radar v1.0.0
  writes. `tests/test_preloader.py` checks them, and skips without a cache,
  so CI never runs it.
- The bootrom owns `0x102868` and `0x1028A8`, so the preloader does not hold
  them. Both agree with [mtkclient](https://github.com/bkerler/mtkclient)
  (GPL-3.0); nothing was copied. mtkclient also clears `0x1072DC`. One write
  to `0x102868` has been enough on every run, and why is not known.
- This route now runs from amonet v2.0.0's fastboot only where the bootloader
  is not the one the device declares as amonet's, and for `short`. From
  amonet v2.0.0's TWRP the targets write the chain in place instead; the
  section above has it. A resume through the bootrom takes v1.1.0's chain only
  where the target is `unlock fireos5`; the other targets write amonet
  v2.0.1's there instead, `short` included.
- The stage returns `False` where it takes the TWRP route, because it then
  reaches v2's TWRP rather than the v1.1.0 fastboot its table entry names, and
  a stage that returns that way counts none of the states it would otherwise
  pass. Marking them would leave the run waiting out ten minutes on the TWRP
  it had just started.
- The script stops if `lk_build_desc` is already v1.1.0's: a second erase
  gains nothing. It reads `getvar`, and refuses a Dot whose `unlock_status` is
  not `true`, or whose `product` is not `BISCUIT`. Every unlocked amonet LK
  answers this fastboot. Without the `product` check, an Echo (2nd
  Generation) on amonet-radar, whose LK says `RADAR`, would read as
  amonet-fastboot, and a run would erase its boot0 and write
  biscuit's preloader and LK to it. This is read from the code and the LK
  images, not seen on a radar.
- It runs `fastboot erase boot0` and `fastboot reboot`, and the Dot drops into
  its bootrom.
- The step ends with the plan's own reboot. Every write reports its own
  result, so no log is read.
- The bootrom is `0e8d:0003`. On macOS it is `/dev/cu.usbmodem*`. On Linux it
  is `/dev/ttyACM*`, owned by `dialout` unless the udev `tty` line gives it to
  `plugdev`, and ModemManager can grab it first. On Windows it is a COM port
  that needs MediaTek's VCOM driver (`cdc-acm.inf`, class Ports, 3.0.1504.0,
  "MediaTek USB Port" in the Microsoft Update Catalog), installed by hand
  with `pnputil /add-driver`; without it `0e8d:0003` is an unknown device.
- Stock and amonet fastboot (`0bb4:0c01`) need a driver too. The README
  installs "Android Bootloader Interface" from the Microsoft Update Catalog.
  It is Google's USB driver revision 8 under TP-LINK's name, and Microsoft
  signs its catalog. Its INF binds `0bb4:0c01` to Windows' own `WinUSB.sys`
  with the Android interface GUID. Google's USB driver r13 does not list
  `0bb4:0c01`.
- Without it, `fastboot devices` lists nothing and the run waits. So a run
  that waits for a Dot on Windows names the missing driver once, when Windows
  lists `0bb4:0c01` and `fastboot devices` does not, on two checks 10 s apart.
  Windows lists a new device before its driver binds, so one check is not
  enough. Each check starts PowerShell, so it runs at most every 10 s.
- Windows bound adb (`1949:0110` and Fire OS 6's `0e8d:201c`, by its interface
  class through its own `winusb.inf`) and v1.1.0's TWRP (`18d1:4ee2`) itself.
  TWRP 3.7.0_9-bboeN is untried on Windows. macOS and Linux need no driver.
- A port that will not open is named once and retried: udev or a modem
  manager can hold it for a moment. The wait is 60 seconds after the erase,
  and 600 when the run waits for a short.
- The run uploads v2.0.0's payload from the fastbrick's zip, reads the Dot's
  partition table over USB, resolves v1.1.0's plan against it, and reads every
  write back. On macOS and Windows the step takes 18 s.
- The bootrom's word commands are big-endian and the Dot's memory is
  little-endian, so the payload and the AES input go out byte-swapped per
  word. Unswapped bytes load in the wrong order and nothing on the wire shows
  it, which is why `write_words` takes words.
- It reads and writes 64 blocks per command, `0x1004` and `0x1003`. One block
  per command was 10 times slower: every region is read twice, and each round
  trip costs about 10 ms.
- The payload does not answer the area switch, `0x1002`, so block 0 is checked
  after each one: boot0 starts `EMMC_BOOT` or is zeros, and the user area ends
  `55 AA`. A read-back alone cannot catch a lost switch, because it reads
  through the same wrong area.
- A read-back proves the transfer, not that the eMMC kept the bytes: its
  256 KiB write cache answers reads. The cache is off at power-on and the
  payload never turns it on, so this step writes uncached.
- v2.0.0's payload ends a 512-byte block read and a 256-byte RPMB read on a
  full packet, and Windows' VCOM driver waits for a short packet. So each such
  read is followed by a 4-byte read, `0x5000`, whose bytes are dropped.
- v1.1.0's `fastboot-step.sh` ships a Linux-only fastboot. The script runs its
  three commands with the host's fastboot instead: `bin/tz.img` to `tee2`,
  TWRP 3.7.0_9-bboe2 to `recovery` in place of v1.1.0's `bin/twrp.img`, then
  `fastboot oem reboot-recovery`.

#### Install: TWRP 3.7.0_9-bboe2

- The image is the `biscuit` build of
  [bboe/twrp_device_amazon_echo-mt8163](https://github.com/bboe/twrp_device_amazon_echo-mt8163),
  on [bboe/android_kernel_amazon_biscuit](https://github.com/bboe/android_kernel_amazon_biscuit).
  GitHub Actions builds and attests both. The script pins the SHA-256.
- Its kernel is Amazon's 5.5.5.4 one with two back-ports for Android 9's
  `init`. Without SELinux ioctl permissions `init` fails with `avtab: invalid
  type or class`; without `mmap_rnd_bits`, with `Unable to set adequate mmap
  entropy value!`.
- bboe2 adds v1.1.0's TWRP 3.2.3 links: `/dev/block/other-boot` and
  `other-system` name the current slot's kernel and system, and `other-lk` is
  `/dev/null`. EchoMuse's installer finds the kernel through `other-boot` and
  stopped on bboe1 without it. Measured on a Dot: `other-boot` was
  `mmcblk0p10` and `other-system` `mmcblk0p13`, and both followed a slot
  change.
- It moves 21.5 to 22.2 MB/s with either governor, against 3.2.3's 5.1 MB/s,
  or 7.0 with cpu0 at `performance`. v2.0.0's TWRP cannot replace 3.2.3 at
  all: its kernel is 32-bit and v1.1.0's LK starts only a 64-bit one.
- amonet v1.1.0 keeps its image in `boot_a` and `boot_b` where Fire OS boots
  from `boot_a_x` and `boot_b_x`. This build points `/boot` at `_x`, and the
  script does not rely on that: it writes `boot<slot>_x` and `system<slot>` by
  name. `dd` to a by-name path that does not exist writes a file in TWRP's RAM
  `/dev` whose read-back matches, so each target must be a block device.
- A Dot in TWRP 3.2.3 gets this TWRP written to `recovery`, checked by md5,
  then `adb reboot recovery`. The script drops 3.2.3's
  `__bionic_open_tzdata...` lines from `adb shell` output.
- adb answers before MTP is on, as `18d1:d001` here. The switch to `mtp,adb`
  puts the Dot back on USB under a new ID, and in 3.2.3 it failed a push with
  `failed to read copy response: EOF`. So the run waits for `mtp` in
  `sys.usb.config`, and each push gets 3 tries. The same error later, while the
  eMMC writes, is a poor USB connection instead: see
  [Writing Fire OS](#writing-fire-os).
- This TWRP's `adb shell` returns the exit status, so each device-side step is
  a pushed script judged by its status. The scripts have `\n` line endings, and
  every push is read back by md5 on the device.
- The userdata script unmounts `/sdcard` and `/data`, formats userdata with
  `mke2fs -t ext4 -b 4096 <userdata> <blocks - 256>`, which leaves 1 MiB for
  the crypto footer, then mounts it with `mount -t ext4`. It sets the size,
  block size and type itself, so the result does not depend on the TWRP's
  fstab. `/data` is then checked as a mountpoint, or Magisk's database lands in
  TWRP's RAM and is gone after the reboot.
- This TWRP mounts system at `/system_root`, so the script patches Fire OS's
  system at `/tmp/fireos-system`. A failed patch leaves that mount, so the
  write unmounts both first. `/proc/mounts` keeps the name `mount` was given,
  so the check looks for the by-name link and the `mmcblk0p` node. Never
  `umount -a` in TWRP: it unmounts `/proc`.

#### Writing Fire OS

- The OTA zip's installer does 2 writes that matter: `system.new.dat` to
  `other-system` and `boot.img` to `other-boot`, which in TWRP 3.2.3 name the
  current slot's `system` and `boot_x`. Its LK write goes nowhere, because
  amonet's TWRP links `other-lk` to `/dev/null`. Its TEE and preloader are
  byte for byte the ones v1.1.0 already wrote to `tee1` and boot0. Its last
  write, `target.blocklist` to `/cache/recovery/last_blocklist`, is skipped: a
  file in `/cache`, not a partition the Echo boots from.
- So the zip never goes to the Echo. The host builds the partition image from
  `system.transfer.list` once, into the cache: 805 MB, 386 MB gzipped, in 22 s
  on macOS and 31 s on Windows 11, on a background thread while the Dot
  unlocks and downgrades. The built image matched `system_a` after a
  `twrp install` in every MiB that the root's own edits and ext4's mount
  metadata leave alone.
- It is built as 128 MiB slices, each its own gzip member, because a
  concatenation of members is one stream to any decompressor. So one cache
  serves both routes below.
- Where `adb shell` carries a stream, the slices go out back to back on its
  stdin, `gunzip -c` reads them and `dd` writes the partition, which overlaps
  the transfer with the write and needs no room on the Echo. Where it does not,
  each slice is pushed to `/tmp` and unpacked at its own offset: 35 MB at a
  time against a 240 MiB tmpfs, so nothing is staged on the eMMC.
- The route is chosen by sending 1 KiB holding 0x1a and hashing it on the Echo,
  not by naming an operating system. A probe that does not complete takes the
  pieces, which need no stream, and says so; a probe that arrives cut takes
  them without a word.
- A Windows adb cannot carry it. Measured on bryce in amonet v2.0.0's TWRP,
  from Windows 11 with adb 36.0.1: `gunzip` read 12 bytes and stopped with
  `gzclose: Illegal seek`, having written 12, while macOS carried 64 MiB
  through the same recovery minutes apart. `adb push` of the same bytes is
  intact from both, at 21.5 MB/s, so the sync protocol is the one that crosses
  hosts. [What adb shell carries](#what-adb-shell-carries) has the byte and
  the counts.
- The command's last line says `stream-ok`, `slice-ok` or `gunzip-failed`, and
  a write is accepted on that line alone, not on silence or on the word
  elsewhere in the output. The stream's deadline covers the transfer, not only
  the wait after it: one thread feeds the slices, another reads adb's output,
  and a stalled adb is killed when the 30 minutes run out.
- TWRP 3.2.3 used `adb exec-in`: 65 s on macOS, 76 s on Windows 11. It is
  binary-safe but returns before the Dot has finished, with no status of its
  own, so a read taken when it returns can differ from what lands.
- `gunzip` on the Dot is the limit: the gzip reaches `cat > /dev/null` in
  17.5 s and through `gunzip`, output discarded, 36.4 to 39.3 s. The whole
  stage, with the eMMC and the md5 read-back, took 80 s streamed and about
  77 s with TWRP 3.2.3, whose read-back alone took 12 s. Slicing costs 23.4 s
  against 15.9 s for 256 MiB, and the sliced route took 108 to 109 s across a
  whole install from Windows 11.
- The sliced route needs a sound USB connection. A poor one loses the
  high-speed link while the eMMC writes: the host sees the Echo disconnect with
  VBUS still present and enumerates it again, and the push or the shell fails
  with `failed to read copy response: EOF` or exit 255. Unplugging both ends of
  the cable and plugging them back in fixes it. `write-test` does not catch it,
  because its USB leg runs with the eMMC idle.
- So a `/system` write that fails all 3 tries says to plug the cable back in. A
  write that discarded a slice or the image does not, because the run treats
  its cache as the fault there. Other pushes do not either: some stage
  bootloader images, and the Echo loses power when it is unplugged.

#### The boot image

- The host builds it from the zip's `boot.img` and Magisk 17.3's zip, in about
  2 s. Nothing runs magiskboot or Magisk's installer. 17.3 is the last 17.x:
  up to v25.2 support Android 5.1, but from v18 the boot patch and `service.d`
  path change, and the host's build follows 17.3's.
- The ramdisk loses `verify` from every fstab, and `default.prop` gets
  `ro.secure=0`, `ro.debuggable=1` and `persist.sys.usb.config=adb`.
- adb alone, not stock's `mtp`, and not `mtp,adb`. On Ubuntu, GNOME's
  `gvfs-mtp-volume-monitor` reset a booted Dot on `mtp,adb` about every 7 s,
  so the last step's wait for Fire OS 5 timed out; 2 owners hit it. With adb
  alone the Dot has 1 interface, the ADB one, and nothing to probe. Nothing
  here uses MTP, and TWRP's `mtp,adb` is its own ramdisk's.
- The property holds: `init.fosflags.sh`, made to take its adb branch, only
  appends `,adb` where adb is missing, and a fresh root leaves no persisted
  value in `/data/property`. bryce and nether's Dot each read `adb` after a
  reboot, and bryce kept one USB device number for 2 minutes.
- The cmdline is the 512-byte header field at offset 64. Stock is
  `bootopt=64S3,32N2,64N2`; the script appends a space and
  `androidboot.selinux=permissive`. The field ends in a NUL, so the line must
  stay under 512 bytes with that addition. Padding the field pads but never
  cuts, so a longer line grew the header past its page, moved the kernel and
  the ramdisk off their offsets, and raised nothing. The script stops instead.
  Biscuit's stock line leaves room; this guards another device's.
- Then Magisk's patch, as its `boot_patch.sh` does it with `KEEPVERITY` and
  `KEEPFORCEENCRYPT` false. `init` becomes `magiskinit` and `verity_key` goes;
  both originals go into `.backup`, with `.magisk`. In the kernel,
  `skip_initramfs` becomes `want_initramfs`.
- Magisk's installer also kept a gzipped copy of the image as it found it,
  `/data/stock_boot_<sha1>.img.gz`, and named it in `.backup/.sha1`. Only
  Magisk Manager's image restore reads them, and `stock` is the way back here,
  so neither is written.
- The kernel is a 512-byte MTK header, a gzip stream and the dtb; only the
  stream and the header's size field change. The ramdisk's cpio is written as
  magiskboot writes one: sorted, inodes from 300000, every mtime 0. Reading a
  cpio ends at the trailer or at the end of the data, so a ramdisk cut short
  before its trailer read an empty magic past the end, and the run then blamed
  the format rather than the length.
- The stock image ends in a 2,048-byte signature. It is dropped, as magiskboot
  dropped it: the unlocked LK does not check it.
- Compared with the image that `twrp install` of Magisk wrote on a Dot, every
  header field, the kernel, the dtb and every ramdisk file are the same, except
  in 3 places. There is no `.backup/.sha1`. 3 symlinks keep their stock modes,
  where busybox's `cpio` had made them 0777. The MTK header keeps the stock
  0xff padding, where magiskboot wrote zeros.
- The image is padded to a 4096-byte multiple and written with `dd`. After
  `sync` the page cache is dropped, and the partition is read back by md5 over
  the image's length.
- The host's copies go in a directory under the cache, not in `%TEMP%`. On
  Windows 11, reading a newly written boot image from `%TEMP%` stalled for
  10.3 s in 10 of 15 trials, and in 0 of 23 trials elsewhere.

#### /system

- `/system/etc/init.fosflags.sh` strips adb from the USB configuration on
  every boot after the first. The script forces its `FOS_FLAGS_ADB_ON` branch
  true, neutralizes its `unset_adb_persistent_property` calls, and checks both
  edits. The 4 Amazon update hosts go into `/system/etc/hosts` as `127.0.0.1`.

#### Magisk

- The zip's installer is not run. Its writes go to the Dot as one cpio
  archive, which TWRP's `cpio` unpacks into `/data`, and the files are read
  back as one md5 over all of them in name order.
- `/data/adb/magisk` gets `arm/`, `common/` and `chromeos/` from the zip, mode
  755, and the installer's busybox: base64 of xz, in `update-binary` as
  `BB_ARM`.
- It also gets `magisk`, which `boot_patch.sh` wrote with
  `magiskinit -x magisk`, and which module installs and `--unlock-blocks` run.
  It is the xz stream in `magiskinit` that unpacks to an ELF. Unpacked on the
  host and by `magiskinit -x` on a Dot, its md5 is the same.
  `/sbin/magisk.bin` differs from it in 62 bytes, which magiskinit randomizes
  at boot.
- On a new userdata the installer wrote to `/data/magisk`, because `/data/adb`
  did not exist yet, and Magisk's daemon moved it at the first boot. The script
  writes to `/data/adb/magisk` directly. The rest of the installer changes
  nothing on this Dot: there is no `/system/addon.d`, no `su` in `/system`, and
  nothing in `/data` to migrate.
- Its database is seeded so the adb shell gets root without a prompt the Dot
  cannot show: `/data/adb/magisk.db`, mode 600, with
  `policies(uid INT, package_name TEXT, policy INT, until INT, logging INT,
  notification INT)` holding `(2000, 'com.android.shell', 2, 0, 1, 0)`.

#### The updater

- An update would replace the boot image and remove root, so on the first
  rooted run the script runs `pm hide com.amazon.device.software.ota`, then
  reads `hidden=true` back from `dumpsys package`.
- Right after the first boot, `dumpsys package` and `pm hide` can both exit 1
  in the same second that `sys.boot_completed` reads 1 and `su -c id` answers.
  Seen on 3 of 3 roots from Windows 11, each hidden by a rerun a minute later.
  So the step says so once, then waits 1, 2, 4, 8 and 16 seconds between
  tries, and stops 60 seconds after the first. Measured again on a Dot from
  Windows 11, writing 5.5.5.4 from bboe2: the first try failed and the second,
  1 second later, hid it.

#### What is measured on a Dot

Each section above keeps the measurement its own claim rests on.
[measurements.md](measurements.md) holds the rest: the ring through a root and
a restore, every whole-run timing, and where the time goes.

### Echo (2nd Generation)

radar declares no Fire OS 5 chain, so it has two targets: `unlock fireos6`,
which the process above covers whole, and `stock`. Its unlock is amonet-radar
v1.0.1, whose fastbrick payloads and preloader are its own.

#### In its bootrom

An empty boot0 reaches a radar's bootrom over the cable it is already on, with
no test point and no case opened, so the short is for the other failure, an
intact boot0 whose preloader never starts LK. The bootrom answers for about 40
seconds per power cycle before its own watchdog takes it, which is why
`load_payload` pets the watchdog while it waits for the operator, and why the
step starts before it asks for the power cycle. Every entry command runs on a
radar as it does on a Dot.
[measurements.md](measurements.md#an-echo-2nd-generation-in-its-bootrom) has the
readings.

That is the part that matters for `stock`: a radar restore clears boot0 at step
2 of 17 and writes the preloader back at step 16, and a failure in that window
leaves the Echo startable only from its bootrom, which is reachable over USB.
Recovery does not mean opening the Echo.

#### Its restore

- radar's stock table, boot0 and partitions are biscuit's, except where
  `userdata` ends, so it takes the same steps. The restore ends `userdata` at
  the table's last usable sector. One radar with an 8 GB eMMC had `userdata`
  end 3.7 GiB before that, so its restore would give `userdata` the rest of
  the disk.

### Echo Show 8 (1st Generation)

crown declares an unlock, amonet-crown v2.0.1, and no target, so no route here
reaches it. It still has three parts in the process above. The probe reads the
amonet states for it, as for radar, because it declares no Fire OS 5 chain.
amonet-crown's own `main.py` is where the boot0 header clear in front of every
chain comes from. And `tests/test_preloader.py` compares its cached preloader
against biscuit's and the radar one amonet-radar v1.0.0 writes.
