# The simulator

`simulator/` runs firebreak and dot_firmware.py against a simulated Dot. No
Dot, real `adb`, real `fastboot` or real serial port takes part.

## Running it

```sh
simulator/run.sh OUT firebreak amonet-biscuit-v1.1.0-bboe
START=no-light simulator/run.sh OUT firebreak amonet-biscuit-v1.1.0-bboe --short
START=no-light DOT_FIRMWARE=.../dot_firmware.py simulator/run.sh OUT dot_firmware v1-bboe --short
python3 simulator/trace.py OUT.jsonl             # one command per line, for diff
python3 simulator/trace.py --commands OUT.jsonl  # with the payload commands per range
```

- `run.sh` makes a new Dot, runs the tool, and leaves `OUT.log`, the trace
  (`OUT.jsonl` and `OUT.txt`), a disk snapshot (`OUT.snapshot`) and the raw
  partition table (`OUT.table`: LBA 0 to 33, then the last 33 sectors).
- `run.sh` destroys the Dot when it exits, also on Ctrl-C or `SIGTERM`. First
  it stops the tool and the loop that waits to plug the Dot in, and waits for
  both. A `plug` in progress runs to its end. A Dot made with
  `python3 simulator/dot.py create` stays until `python3 simulator/dot.py destroy`.
- `run.sh` passes its pid to `create`. `create` refuses while the `run.sh`
  that the state names still runs.
- It needs Docker, `timeout` (coreutils, on macOS too), and the downloads in
  `~/.cache/firebreak`. The image build downloads busybox, pigz and toybox
  source and checks each by SHA-256.
- The tools' cache is `~/.cache/firebreak-sim-cache`. `dot.py create` copies
  each download into its `firebreak` and `overdub-firmware` folders, as an
  APFS clone on macOS and with `--reflink=auto` elsewhere. Where a clone
  fails, as off APFS, it copies the file. So a tool that writes a file in
  place changes only the copy. A copy whose size or modification time is not
  its download's is copied again. What a tool builds there stays for the next
  run.
- State and the trace are in `~/.cache/firebreak-sim`. `FIREBREAK_SIM` and
  `FIREBREAK_SIM_CACHE` move the two, so several Dots can run at once. Each
  Dot needs its own pair: the tools keep their boot0-erased marker in the
  cache.
- `create` refuses a `FIREBREAK_SIM_CACHE`, or a `firebreak` or
  `overdub-firmware` folder in it, that is the same directory as `~/.cache`,
  `~/.cache/firebreak` or `~/.cache/overdub-firmware`, or as
  `$XDG_CACHE_HOME` or either tool folder in it. It compares device and
  inode, so another case, a link, a trailing slash or a relative path does not
  get past it. It also refuses when `HOME` is not set, and when either tool
  folder is a link. The tools would otherwise write the real caches.
- `START=fastboot`, the default, starts in stock fastboot. `START=no-light`
  erases boot0 and leaves the Dot unplugged. `run.sh` plugs it in when the
  tool prints "Short the Dot's test point".
- The tool's stdin is `/dev/null`. Its stdout must be unbuffered: without
  `PYTHONUNBUFFERED=1`, the prompt reached the log only at exit, and the Dot
  was never plugged in.
- `run.sh` stops if `adb` or `fastboot` on its PATH is not the simulator's, or
  if the virtualenv's port hook is not loaded.
- `simulator/bin/adb` and `simulator/bin/fastboot` run `dot.py` under the virtualenv's
  interpreter, and fail when there is none. Through pyenv's shim, `python3`
  took 270 ms to start against 14 ms, and a run makes up to about 260 calls.
- After the tool exits, `run.sh` runs `dot.py halt` before it copies the
  trace. `halt` sends the bootrom SIGTERM, which writes its open range, and
  waits up to 10 s for it to exit. It signals the pid only when that process
  runs this checkout's `bootrom.py` for this state folder. Otherwise it drops
  the pid. The bootrom clears its pid from the state on every exit.
- `create` destroys the Dot that the state names before it makes a new one.
  `destroy` halts too, then takes the state's lock. It stops a bootrom that
  started after the halt, sets each of the Dot's loop devices writable,
  detaches it, and removes the container. It skips a loop whose backing
  inode, offset or size is no longer the Dot's.
- A stopped container cannot run the detach, and its loops stay bound to the
  deleted disk files. So `destroy` starts a stopped container first. If the
  detach still fails, it copies the loop records out and runs the detach in a
  new privileged container of the same image, with the same checks. If that
  fails too, or the container is gone, it prints a warning with the records.

## What runs for real

- The eMMC is files in a privileged container: the user area, boot0, boot1
  and the RPMB. `sim-boot` makes a loop device for each table entry at each
  boot.
- The container has no network (`--network none`). The tools themselves run
  on the host and keep its network.
- The container is privileged. So it sees the Docker VM's devices under
  Docker Desktop, and the host's devices on a Linux host. At each boot
  `sim-boot` removes every block node from the container's `/dev` and then
  makes nodes for its own loops only. `/dev` is the container's tmpfs, so
  this removes nothing on the host. It takes loop numbers from
  `/dev/loop-control`, so any number of Dots can run.
- At each boot `sim-boot` kills every process that the previous boot's
  commands left running, a leftover `sleep infinity` too. A Dot does not keep
  writing across a reboot. It spares pid 1, its oldest child (the container's
  command) and `sim-boot`, by pid. It spares the loop holder only while that
  pid runs `sim-hold` for this run folder.
- Every `adb shell` and `exec-out` command runs in the container as the uid
  and gid that the Dot's adbd gives it, under that environment's `sh`. Its
  `PATH` holds only that environment's commands. No GNU tool is on it, except
  bash where TWRP ships bash.

| environment | `sh` | commands | uid |
| --- | --- | --- | --- |
| TWRP 3.2.3 | busybox | busybox; `gunzip`, `gzip` and `unpigz` are pigz | 0 |
| TWRP 3.7.0_9-0, 3.7.0_9-bboe2 | mksh | toybox; `dd`, `grep`, `awk`, `unzip`, `bash` and `unpigz` are their own | 0 |
| Fire OS 5 | mksh | toolbox's names, `busybox`, `gzip`; no `md5sum` or `wc` by name; `su` under Magisk only | 2000 |
| Fire OS 6, root adb | mksh | toybox; `dd`, `ps`, `top` are toolbox's; `grep` and `gzip` are their own; no `gunzip` | 0 |

- Each list is read from the image. TWRP's is each ramdisk's `/sbin`. Fire OS
  5's is `/system/bin` of the image that the Fire OS 5 routes write
  (`system-6ababc517529`). Fire OS 6's is `/system/bin` of stock 8146.
- Every `/sbin` name that a TWRP list leaves out is in
  `/sim/flavours/*.missing`, as is every name that a Fire OS list maps to
  toolbox or toybox and the simulator does not have. Other Fire OS programs
  that no tool calls, such as `am`, `logcat` and `svc`, are not listed.
- Fire OS 5 has no toybox. Its `/system/bin/busybox` is BusyBox v1.22.1,
  static, with 354 applets, and no name links to it. So `md5sum`, `wc`,
  `gunzip` and `zcat` work only as `busybox md5sum` and so on.
- The builds are the closest that run in the container, not the Dot's
  binaries:

| on the Dot | in the simulator |
| --- | --- |
| busybox 1.22.1, bionic | busybox 1.22.1, glibc, `defconfig` |
| pigz 2.2.5 | pigz 2.2.5 |
| toybox 0.7.6, Android's config | toybox 0.7.6, `defconfig` with `dd`, `gzip`, `gunzip`, `zcat`, `tr` and `expr`, on zlib |
| mksh, Android's | mksh R59c |
| toolbox's `dd`, and 3.7.0's own | `toolbox-dd`: refuses `conv=` with `dd: conv option disabled`, else runs toybox `dd` |
| 3.7.0's and Fire OS 6's own `grep` | toybox `grep` |
| 3.7.0's own `awk` | original-awk 2023-11-27 |
| 3.7.0's own `unzip` | Info-ZIP unzip 6.0 |
| Fire OS 5's busybox 1.22.1, static | the busybox above: the 354 applet names match |
| Fire OS 5's and 6's `gzip` (zlib's `minigzip`) | `minigzip` from zlib 1.2.8 |
| Fire OS 5's toolbox, Fire OS 6's `ps` and `top` | toybox 0.7.6 under toolbox's names |
| toolbox `md5` and `hd` | `simulator/device/toolbox`: AOSP 5.1's `md5.c` and `hd.c` in Python |
| toolbox `start`, `stop` and `log` | no-ops that exit 0 |
| toolbox `getevent` | waits for ever: there is no input device |
| `sgdisk`, `mke2fs`, `e2fsck`, `resize2fs`, `tune2fs` | gdisk 1.0.10, e2fsprogs 1.47.0 |

- The base image is `ubuntu:24.04` pinned by digest. The image build gets
  these packages, not pinned: cpio 2.15+dfsg-1ubuntu2.1, e2fsprogs
  1.47.0-2.4~exp1ubuntu4.1, gdisk 1.0.10-1build1, mksh 59c-37, original-awk
  2023-11-27-1, python3 3.12.3-0ubuntu2.1, python3-fusepy 3.0.1-5, unzip
  6.0-28ubuntu4.1 and util-linux 2.39.3-9ubuntu6.6, as built on 2026-10-11.
- `minigzip -d` passes input with no gzip magic through, as zlib's `gzread`
  does, and exits 0.

- Names that a ramdisk links but the simulator's build lacks are left out.
  The image lists them in `/sim/flavours/*.missing`: mostly SELinux commands,
  `test` and `[` outside the shell, `tar`, `diff`, `stty` and the SHA-2 sums.
- toybox 0.7.6's `gunzip` passes input with no gzip magic through, as `cat`
  does, and exits 0. A stream cut short exits 1 with `gzclose: Illegal
  seek`. pigz 2.2.5 refuses input with no magic, `not compressed --
  skipping`, and exits 2.
- toybox `dd` truncates its output at `seek`, and a block device answers
  `ftruncate: Invalid argument`. toolbox's `dd` writes a block device whole,
  as overdub's rooting.md measured. So `toolbox-dd` adds `conv=notrunc` when
  the output is a block device. Without it, dot_firmware's `boot.payload`
  write failed.
- glibc's `realpath` fails on a missing last component, so busybox
  `readlink -f` prints nothing for it. Bionic's prints the path, which
  `fix-symlinks.sh` relies on. The simulator models that script's result
  rather than running it.
- `/data/local/tmp` is `root:shell` `0771` under Fire OS 5, as overdub's
  pitfalls measured. A push there lands `0666`. Elsewhere a push lands as
  the container's `umask` leaves it.
- Device nodes are `root` `0600`, so uid 2000 can neither read nor write
  them. `/proc/sys/vm/drop_caches` and `force_ro` refuse uid 2000 too. These
  modes are Linux's and Android's defaults, not read from a Dot.
- amonet v2.0.0's `update-binary` runs unchanged, under the TWRP's `sh`, when
  a tool installs its zip in TWRP.
- Each boot is decided from the disk: the preloader in boot0, the LK in
  `lk_a`, the TWRP in `recovery`, the markers in `expdb` and `misc`, the build
  in `system_X`, and Magisk in `userdata`.

## What is modelled

- `adb`, `fastboot`, `getprop`, `setprop`, `su`, `id` under Fire OS, `bcbtool`,
  `pm`, `dumpsys`, `getenforce` and `reboot` are stubs. `twrp install` writes a
  Fire OS 6 build for an OTA zip and marks root adb for any other zip but
  amonet's.
- `su` is a setuid binary. It gives root only while Magisk's database is in
  `userdata`, and Fire OS 5 has it on `PATH` only then. Magisk's busybox is not
  put first on `PATH` under `su`.
- `su` reads its words with `getopt_long`, the options and the option string
  of Magisk 17.3's `native/jni/su/su.c` (tag `v17.3`). As there, getopt moves
  the words that are not options to the end. `-c` takes the command from the
  word before `optind`, so `su 0 -c id x` runs `id x` and `su -cid` runs
  `-cid`. The first word left after the options, and after a `-`, is the
  user. So `su 0 -c` and `su root -c` set the uid. `-cn` and `-mm` are
  rewritten to `-z` and `-M`, and `-u` prints the usage and exits 2.
- Not as Magisk: glibc's `getopt_long`, where Magisk has bionic's; names
  other than `root`, `system` and `shell` read as a number, where bionic
  knows every Android id; and `-s`, `-l`, `-p` and `-M` change nothing. Its
  own PTY, which Magisk opens when stdin is a terminal, is not modelled. It
  exits with the command's status.
- Under uid 2000, `setprop` sets only `debug.*`, `log.*`,
  `service.adb.root`, `service.adb.tcp.port` and `sys.powerctl`, which AOSP
  5.1 lets the shell set. Any other name is ignored and `setprop` exits 0. A
  set `ro.` name does not change. `sys.powerctl` set to `reboot,X` reboots
  into X.
- `reboot` sets `sys.powerctl`, as 5.1's `reboot` does, so the shell can
  reboot. It returns at once, where 5.1's waits for the reboot.
- `/sdcard` and `/data/local/tmp` are container folders. They have no size
  limit, and a format of `userdata` does not empty them. `/sdcard` is `0777`:
  its FUSE modes are not modelled.
- boot0 holds a preloader when it starts `EMMC_BOOT` and holds `BRLYT` at
  0x200. Otherwise the Dot boots into the bootrom. So amonet v1.1.0's
  `EMMC_BOOT` and zeros, and firebreak's zeros, both reach it. Nothing else in
  boot0 is checked: not the preloader's own header or its signature, and not
  boot1.
- `lk_b`, `tee1` and `tee2` take no part in a boot. Only `lk_a` decides the
  LK.
- The fastbrick writes amonet v2.0.0's chain directly. It runs no exploit.
- amonet v1.1.0's LK clears `FASTBOOT_PLEASE` in `expdb` when it acts on it.
  This is inferred: `fastboot-step.sh` reaches TWRP with the marker still
  written, so the marker cannot hold the Dot in fastboot.

### boot0 and boot1

- Their loop devices are read-only from the start of each boot, and again
  after each `fastboot flash` or `erase` of them.
- `/sys/block/mmcblk0bootN` is a FUSE file system with `force_ro` and `size`,
  over a tmpfs. A boot fails unless the FUSE file system is the top mount
  there. So a write cannot reach a Linux host's own `/sys/block`.
- A write to `force_ro` sets the loop device read-only or writable before it
  returns. So `echo 0` and `echo 1` hold for any writer: `dd`, `toybox dd`, or
  a shell redirect.
- The value is read as the Dot's kernel, Linux 3.18.19, reads it: with
  `simple_strtoul` in base 0. A number other than 0 sets read-only, and text
  with no number first is `EINVAL`. So `1_0` sets read-only, and `-1` and a
  space before `1` are `EINVAL`. Later kernels use `kstrtoul`, which refuses
  `1_0`.
- A read gives the loop device's flag. So after a direct `blockdev --setrw`
  it reads 0.
- Only root can write `force_ro`.

### TWRP

- Each TWRP replaces its by-name bootloader nodes at boot, as the script in
  its ramdisk does. A write through one does not reach the disk.
- 3.2.3 (`/sbin/fix-symlinks.sh`): `lk_a`, `lk_b`, `tee1` and `tee2` are
  `/dev/null`, and `X_real` names the partition. `boot_a` and `boot_b` name
  `boot_a_x` and `boot_b_x`, and `boot_X_amonet` names amonet's. With no
  `boot_X_x`, `boot_X` is a link to the missing `by-name/boot_X_x`.
- 3.7.0_9-0 and 3.7.0_9-bboe2 (`/sbin/slot-symlinks.sh`): `lk_a`, `lk_b`,
  `tee1`, `tee2`, `tee` and `preloader` are files in `/tmp/ota-decoy`, at
  1, 1, 5, 5, 5 and 4 MiB. `X_real` names each one that was a partition.
  `[ -b ]` is false for a decoy, so `update-binary` writes `X_real`.
- `/tmp/ota-decoy` is a 64 MiB tmpfs, so a `dd` with no `count` there stops.
- bboe2 also points `boot_a` and `boot_b` at `boot_a_x` and `boot_b_x` when
  they exist, and keeps amonet's as `boot_X_amonet`.
- Not modelled: `/dev/block/other-lk`, `other-system` and `other-boot`,
  `/dev/block/current-boot` and `current-system`, `/dev/block/bootdevice`,
  `/dev/block/by-name` and `/dev/block/platform/bootdevice`. A command that
  names one finds nothing.
- adb answers 5 s before MTP is on. Until then `sys.usb.config` is `adb` and
  `ro.twrp.version` is not set. The 5 s is from the ring's timing in
  rooting.md.
- The switch to `mtp,adb` drops USB for 1 s. A call made then fails with
  adb's error text, and `adb devices` lists nothing. A shell call running
  across the switch runs to its end, prints the first half of its output
  and exits 255, or 0 without the shell protocol. A push fails with `failed
  to read copy response: EOF`.
  The trace marks each one `# cut by the USB switch`. None of this is
  measured: not the 1 s, the command running on, the half, the status or the
  text.

### adb

- The `adbd` of TWRP 3.2.3 (5.1.1, `LMY49M`) and of Fire OS 5.5.5.4 (from
  its OTA's `boot.img`) list no `shell_v2` feature and hold
  `create_subproc_pty`. The `adbd` of both 3.7.0 TWRPs and of Fire OS 6 list
  `shell_v2`. Each was read from its image.
- So under 3.2.3 and Fire OS 5, adb has no shell protocol. adb 37's client
  (`client/commandline.cpp`) then:
  - exits 0 from `adb shell` whatever the command did, and 1 only when it
    cannot connect;
  - never tells the Dot that stdin ended, so a command that reads stdin to
    its end never ends;
  - refuses a service string over 4096 bytes with `error: shell command too
    long`, and `-T` with `error: device only supports allocating a pty`.
- 5.1's `adbd` (`adb/services.c`) runs a `shell:` command on a PTY, which it
  leaves in the kernel's default mode, and an `exec:` command on a socket
  pair. So the output has CR LF, and the line discipline acts on stdin: it
  echoes it, edits lines, and sends `SIGINT`, `SIGQUIT` and `SIGTSTP` for
  0x03, 0x1c and 0x1a. `sim-pty` runs the command so, on a PTY in the
  container with the container kernel's default mode.
- That PTY is the container's kernel, Linux 6.x, not the Dot's 3.18.19. It
  passes all output that the command wrote before the PTY closes. The Dot's
  3.18 kernel and Lollipop's `adbd` can lose the tail of the output. The
  simulator never loses it, and models no such loss.
- When the host's `adb` exits, `sim-pty` hangs the PTY up, as `adbd` does
  when it closes the PTY. That `adbd` closes it then is inferred.
- `exec-out` exits 0 in every environment: the client never reads a status.
  The command's stdin never ends there either.
- With the shell protocol, under 3.7.0_9-0, bboe2 and Fire OS 6, `adb shell`
  passes the status, as overdub's rooting.md measured for 3.7.0. `-n` ends
  the command's stdin at once. Otherwise the shim passes stdin and then ends
  it.
- adb's own options are read only before the command, as adb's `getopt`
  with `+` does: `adb shell ls -t` runs `ls -t`.
- 3.2.3's `__bionic_open_tzdata` lines are not modelled. Nor is what `-x`
  makes a protocol `adbd` do.

### fastboot

- A locked LK refuses `flash` and `erase` with `the command you input is
  restricted on locked hw`, which a locked v1.1.0 LK printed.
- `flash` of an image larger than its partition fails with `size too large`.
  `flash` or `erase` of a name that is not in the table, nor boot0 or boot1,
  fails with `unknown partition`. Neither text is measured.
- `-S` sets the size above which `flash` reports `Sending sparse`, with the
  count of pieces. The write is the same either way. Without `-S` an image is
  sent whole.
- `oem reboot-recovery` reboots into recovery on any LK, locked or not. That
  a locked LK accepts it is not measured.

### The bootrom

- The bootrom is `simulator/bootrom.py`, on a pseudo-terminal, started at the boot
  into the bootrom. It runs no code. It answers the handshake, `0xd1`,
  `0xd4` and `0xc8`.
- The crypto engine at `0x10210000` answers function 126 only after the
  acquire words, with length 1 and slot pointers 18, 26, 26. It then writes
  the input words XOR the zero decryption to the destination.
- Before `0x102868` holds the range-check pattern, word access below
  `0x10000000` is refused. So a payload upload or a jump without the defeat
  fails.
- A write to `0x1028A8` jumps. The bootrom compares the memory at `0x201000`
  with the `payload.bin` of each amonet zip. It answers as the payload that
  matches, and stays silent for any other code.

### The payload

- The payload speaks its own command set: v1.1.0's six commands, or the
  twelve that v2.0.0's client sends.
- `0x5002` sends v2.0.0's 512-byte test pattern, so its client's fast-send
  check passes. `0x5003` answers the acknowledgement.
- Block commands go to the disk files through `sim-emmc` in the container.
  The RPMB is the first 256 bytes of its file. A new Dot's RPMB starts
  `AMZN`.
- `0x1003` and `0x1004` take 1 to 64 blocks, as amonet's client allows. A
  count outside that, a read or write past the end of its area, or any
  access to an area other than 0, 1 and 2 halts the payload: it logs
  `halted` and answers nothing more. What the real payload does there is not
  known.
- `0x5000` reads any address at any length. Whether the real payload bounds
  either is not known.
- The `0x3000` reboot hands the Dot back to the boot rules, 3 s later.
- The port is not modelled: the short, the watchdog, the preloader's
  `0e8d:2000` port and USB packet sizes do not exist here.

### Leniencies

The simulator accepts these, where a real Dot may not:

- a jump without the cache-disable command (`0xC8 0xB1`)
- a crypto engine that ignores SOURCE and does not need the key and IV slots
  cleared
- root on Fire OS 5 decided by `magisk.db` alone
- amonet v2.0.0's LK reading unlocked whatever the TEE holds
- any LK but stock booting any known TWRP
- the fastbrick on an unlocked LK
- the fastbrick leaving boot0 as it was; the real one writes the preloader
- `-s` and `ANDROID_SERIAL`, which it records and ignores
- `dd` past 2 GiB of `mmcblk0` under bboe2 and 3.7.0_9-0, where the Dot's
  `dd` answers `EINVAL`

## The port

- `dot.py create` makes a virtualenv in `~/.cache/firebreak-sim/venv`. A
  `.pth` file there imports `ports.py` at every start, so the children that a
  tool starts with `sys.executable` see the port too, whatever their
  `PYTHONPATH`.
- `ports.py` replaces `serial.tools.list_ports.comports` when pyserial loads.
  It lists only the simulated bootrom, `0e8d:0003`, and only while the Dot is
  in its bootrom. It never lists a real port.
- Under Python 3.9, pyserial from the wheel loads through `zipimporter`, which
  has no `exec_module`. So the hook runs the module's code from `get_code`.
- dot_firmware.py ignores a bootrom port that is there before amonet logs
  "Waiting for bootrom". So a no-light Dot stays unplugged until the prompt.
- The bootrom keeps the pseudo-terminal's other end open, so a tool can close
  and reopen the port.

## The clock

- `FIREBREAK_SIM_SPEED` sets the speed, K. `run.sh` sets 20 when it is not
  set. At 1 or less the hook changes nothing.
- The hook replaces `time.monotonic`, `time.perf_counter`, `time.time`, their
  `_ns` forms, `time.sleep`, `select.select` and the `select` method of each
  `selectors` class. It does this in every process the virtualenv's
  interpreter starts: the tool, its children, `dot.py` and `bootrom.py`.
  `run.sh` runs `plug`, `halt`, `snapshot` and `table` under that interpreter
  too.
- The clock runs K times faster than real time, except while a process holds
  it. Then it runs at real time in every process. A `dot.py` call holds it
  from its start to its exit, except while it sleeps. `bootrom.py` holds it
  for each eMMC access. So work in the container takes real time, and so
  does a tool timeout that waits for it.
- `clock.json`, in the state folder, holds the anchor in real and in clock
  time, the offset to wall time, and the pids that hold the clock. A change
  replaces the file whole, under `clock.lock`. Each change drops the pids that
  are gone, so a call that a tool kills holds the clock only until the next
  change. `create` deletes the file.
- Each trace line's `time` is the clock's, not real time, except the lines
  that `create` writes: `run.sh` runs it without the hook.
- A sleep or a wait for a descriptor sleeps at most 50 ms of real time at
  once, so a change of speed takes effect within 50 ms.
- pyserial keeps `time.monotonic` as a class attribute and calls it through
  `self`. A plain function there gets `self` as an argument, so the clock's
  functions are bound methods.

These stay in real time:

- `Event.wait`, `Lock.acquire` and `Condition.wait` with a timeout. Each tool
  uses them only for its progress line, every 0.1 s, and for its cache lock,
  in a loop with no deadline.
- Socket timeouts. Only downloads use them, and the cache holds every
  download.
- `datetime.now()` in amonet's log, and `time.strftime` in each tool's log.
  They only print.
- `run.sh`: `timeout 1500`, and the 0.5 s poll for the short prompt.

Work outside a hold counts K times: the interpreter's start before the hook,
each tool's own work, and the pseudo-terminal. With 6 Dots at once a call to
`adb` or `fastboot` spends about 100 ms there, 2 s at K=20. These timeouts
bound K:

- firebreak kills `fastboot flash brick` after 8 s, as a Dot needs. At K=20,
  with 6 Dots at once, the call took 1.6 to 2.8 s to start and the chain 0.8
  to 1.3 s more. At K=100, 1 of the 3 runs from stock fastboot was killed
  before the reboot, and at K=200 all 3 were. Each then stopped with "the Dot
  has been stock-fastboot for 10 minutes".
- firebreak waits 5 s for a 64-block payload read. At K=100 and at K=200, 1
  of the 3 runs from no light stopped there, with 25,550 and 26,572 of
  32,772 bytes.
- At K=20 all 18 runs rooted, 6 at a time. At K=100, 2 of 6 stopped, and at
  K=200, 4 of 6.

### Measured

Measured on 2026-10-12, firebreak to each target from no light with `--short`
and from stock fastboot, 6 Dots at once. Each Dot had its own `FIREBREAK_SIM`
and `FIREBREAK_SIM_CACHE`. A time is from the start of `run.sh` to its
summary line, and includes `create` and `snapshot`.

| run | K=1 | calls | K=20 | calls | K=20 | calls |
| --- | --- | --- | --- | --- | --- | --- |
| v1-bboe, no light | 73 s | 181 | 60 s | 165 | 58 s | 165 |
| v1, no light | 75 s | 191 | 58 s | 175 | 60 s | 175 |
| v2, no light | 103 s | 275 | 60 s | 249 | 60 s | 248 |
| v1-bboe, fastboot | 87 s | 186 | 64 s | 164 | 64 s | 164 |
| v1, fastboot | 87 s | 186 | 64 s | 164 | 64 s | 164 |
| v2, fastboot | 63 s | 65 | 30 s | 51 | 28 s | 51 |

- The 6 runs took 103 s at K=1 and 64 s at K=20, both times.
- A run makes fewer calls at a higher K. A call's start counts K times, so
  fewer polls fit in a wait.
- At K=20 and K=100, each run's trace, snapshot and raw table matched the run
  at K=1, but for the number of polls.

## The trace

- Every `adb` and `fastboot` call, boot and reboot goes to `trace.jsonl`, one
  locked write per line, with the whole command line, global flags included.
  Each call goes in when it starts, so a call that a tool kills still shows.
  A push and a `fastboot flash` carry the file's md5.
- A shell call that passes stdin adds a second line when it ends, `# stdin
  sent BYTES:MD5 received BYTES:MD5: COMMAND` in `trace.py`'s output.
- `sent` counts the bytes that the host's shim wrote into `docker exec`.
  `received` counts the bytes that arrived in the container. `sim-stdin`
  counts them there, between `docker exec` and the command's `sh` or
  `sim-pty`, and passes them on through a pipe. Neither counts what the
  command read. `received unknown` means `sim-stdin` did not report, as when
  a reboot killed it.
- When the command exits before it reads all of its stdin, `received` can be
  less than `sent`: the rest is still in Docker. When the command reads to
  its end, a `received` less than `sent` is bytes that Docker lost.
- The bootrom logs each command with its address and words, and a refused
  `read32` or `write32` as `refused` with its count. An upload of more than 16
  words logs its count and md5.
- The payload logs reads and writes as an area, a first block, a count and
  the md5 of the bytes. Contiguous reads, or contiguous writes, join into one
  range. `--commands` shows the commands each range took. It also shows the
  watchdog kicks and cache reads sent between ranges, as `between ranges`.
- `trace.py` puts `$CACHE` for the simulator's cache folders and
  `~/.cache/firebreak`, and `$TMP` for temporary names. It drops `adb
  devices`, `adb get-state` and `fastboot devices`; `--keep-polls` keeps
  them.
- `adb shell -n getprop NAME`, `fastboot getvar NAME` or `adb wait-for-X`,
  the whole line and nothing more, is not printed again when it is the same
  as the last line printed. A dropped poll between them does not count, so
  the number of polls before TWRP is up does not show. Every other line is
  printed each time, compound commands included, so a command sent twice
  shows twice.

## Traps

- `dd if=/dev/zero` onto a regular file with no `count` does not stop at the
  file's end. One filled Docker's disk. The container was gone, but its loop
  devices still held the deleted file, so the space came back only after a
  Docker restart.
- A loop that `losetup` attached and that then fails its backing check, or
  its `blockdev`, is detached before the boot fails. A loop whose backing
  inode is not the Dot's is left alone.
- A loop device's read-only flag outlives `losetup -d`. A loop that was
  boot1 at one boot came back as `boot_b` at the next and refused every write
  with `Operation not permitted`. Loop numbers are shared by every container
  on the host, too. So `sim-boot` sets each loop writable when it attaches
  it and before it detaches it, and `destroy` does the same.
- A container removed without `destroy` leaves its loop devices attached in
  the Docker VM. `losetup -a` in any privileged container lists them.
- busybox and toybox `umount` free the loop device under what they unmount,
  where on a Dot `LOOP_CLR_FD` fails on an eMMC partition. Freed, the loop
  number went to another Dot's partition: one Dot's `sgdisk` then read a
  768 MiB disk with no table, or a disk of 0 sectors, and one snapshot read
  `system_a` through `rpmb`. So `sim-hold` keeps every loop open for the boot,
  and the kernel only marks a busy loop to clear when it closes.
- `sim-hold` writes to `/sim/run/holder.log`. A boot fails unless it holds
  every loop. `facts` and `snapshot` fail unless it still runs.
- FUSE 2 refuses a mount point that is not empty, so `/sys/block` is mounted
  with `nonempty`.
- `docker exec -u 2000` runs with gid 0, so a `root:shell` `0771` folder
  refuses it. The simulator passes `2000:2000`.
- The ext4 file systems differ on every run. The snapshot compares their file
  trees, not their bytes.

## Both tools, measured

Measured on 2026-10-11: each target from no light with `--short`, and from
stock fastboot, all 12 Dots at once and then three at a time.

- All 24 runs rooted their target: v1-bboe, v1 and v2, with each tool. All 12
  at once took 112 s, each run 68 to 111 s. Three at a time took 294 s, each
  run 57 to 99 s. Docker Desktop had 10 CPUs and 8 GB, and no run lacked a
  loop device or disk space.
- Against the set before the shell model changed, every run sent the same
  commands, and every snapshot and table is the same, but for random bytes:
  the stdin probe's, and the GUIDs that amonet and dot_firmware give
  `boot_a` and `boot_b`. Under Fire OS 5 both tools send only `-n` calls and
  drop CR, so its PTY changed no result.
- Once in the 24, a dot_firmware v1 run from no light rejected its first
  `/system` stream 0.16 s after the stream ended, and the second passed and
  read back. The trace holds no output, so why is not known. 18 more runs of
  that target, 6 and 12 at once, did not repeat it.
- No route of either tool works in TWRP 3.2.3. From a Dot rooted to v1 and in
  3.2.3, each writes bboe2 to `recovery`, checks it by the md5 it prints, and
  reboots into it.
- Each tool's stdin probe, run by itself under 3.2.3, read as not carried in
  0.3 s and exit 0: the PTY's line discipline acted on control bytes in the
  random part and ended `cat`. The tool then sends the image in pieces and
  says nothing. Text with no such byte made `cat` wait until adb was killed.
  So a probe without one would wait for its 60 s timeout. firebreak catches
  that;
  dot_firmware's `stdin_carries` does not, so it would stop with
  `TimeoutExpired`.
- From no light, the adb and fastboot commands are identical for v1-bboe and
  v1, except the stdin probe's bytes: each tool sends 16 bytes of 0x1a and
  1008 random ones. For v2, dot_firmware installs amonet's zip in TWRP and
  firebreak writes the chain itself.
- From stock fastboot, the commands for v2 are identical, and so is the disk.
- From stock fastboot, for v1-bboe and v1, both tools write the same images
  in TWRP, md5 for md5, in another order. dot_firmware makes room with
  `sgdisk`; firebreak writes both table copies with `dd`. firebreak also
  reads each region before it writes it.
- Every Fire OS 5 route streamed the same 385,732,934 bytes to `system_a`,
  by md5, from both tools.
- The bootrom traffic writes the same registers. amonet writes the crypto
  engine one word per command; firebreak writes each block of registers in one
  command. Both read `0x10210800` twice in a row. No access was refused.
- Every payload write carries the same bytes in the same order, except the
  partition table. firebreak also reads each region before it writes it, and
  reads it back after. It uses `0x1004` and `0x1003` throughout. amonet reads
  single blocks and zeroes `userdata`'s first 10 blocks with `0x1001`.
- Neither tool sends `0x5002` or `0x5003`. No payload halted.
- v1-bboe and v1 tables differ in 3 ways from no light. amonet writes its own
  protective MBR, with `0xffffffff` sectors; firebreak keeps LBA 0. amonet
  gives `boot_a` and `boot_b` random GUIDs; firebreak derives them from the
  disk GUID. The headers' two CRCs follow from the GUIDs. From stock
  fastboot, `sgdisk` keeps LBA 0, so only the GUIDs and CRCs differ.
- For v2 the tables are identical.
- For v2 from no light, `lk_a`, `lk_b` and `tee1` hold v1.1.0's old bytes
  past v2.0.0's shorter images, after both tools. firebreak writes whole
  sectors, so it zeroes the rest of each image's last sector: 192 bytes of the
  LK and 504 of the TEE. amonet's `dd` leaves those bytes as they were.
- No write went through a decoy, and each boot0 write came after `echo 0`,
  now for any writer.
- Under uid 2000 on Fire OS 5, both tools did every privileged step through
  `su`, and pushed only to `/data/local/tmp`.
- No call crossed the USB switch in this set. In 2 earlier sets it cut a
  firebreak `getprop` in 2 of 12 runs and in 2 of 6, and firebreak read it as
  not yet started and polled again. No dot_firmware call crossed it.
- Neither tool's gzip check or `gunzip-failed` path ran: every stream was a
  whole gzip. Both are reachable. With input that is not gzip, TWRP 3.2.3's
  pigz exits 2 and the stream prints `gunzip-failed`, while 3.7.0's toybox
  passes it through and prints `stream-ok`. A gzip cut short prints
  `gunzip-failed` in both. Fire OS 6 has no `gunzip`, so every stream there
  prints `gunzip-failed`.
