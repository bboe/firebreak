# The simulator

`sim/` runs firebreak and dot_firmware.py against a simulated Dot. No Dot, real
`adb`, real `fastboot` or real serial port takes part.

## Running it

```sh
sim/run.sh OUT firebreak amonet-biscuit-v1.1.0-bboe
START=no-light sim/run.sh OUT firebreak amonet-biscuit-v1.1.0-bboe --short
START=no-light DOT_FIRMWARE=.../dot_firmware.py sim/run.sh OUT dot_firmware v1-bboe --short
python3 sim/trace.py OUT.jsonl             # one command per line, for diff
python3 sim/trace.py --commands OUT.jsonl  # with the payload commands per range
python3 sim/dot.py destroy
```

- `run.sh` makes a new Dot, runs the tool, and leaves `OUT.log`, the trace
  (`OUT.jsonl` and `OUT.txt`), a disk snapshot (`OUT.snapshot`) and the raw
  partition table (`OUT.table`: LBA 0 to 33, then the last 33 sectors).
- It needs Docker, the downloads in `~/.cache/firebreak`, and the cache of
  links in `~/.cache/firebreak-sim-cache`. State and the trace are in
  `~/.cache/firebreak-sim`.
- `START=fastboot`, the default, starts in stock fastboot. `START=no-light`
  erases boot0 and leaves the Dot unplugged. `run.sh` plugs it in when the
  tool prints "Short the Dot's test point".
- The tool's stdin is `/dev/null`. Its stdout must be unbuffered: without
  `PYTHONUNBUFFERED=1`, the prompt reached the log only at exit, and the Dot
  was never plugged in.
- `run.sh` stops if `adb` or `fastboot` on its PATH is not the simulator's.
- `sim/dot.py destroy` detaches the loop devices and removes the container.

## What runs for real

- The eMMC is files in a privileged container: the user area, boot0, boot1
  and the RPMB. `sim-boot` makes a loop device for each table entry at each
  boot.
- Every `adb shell` command runs in the container, under busybox `sh`, against
  those loop devices. `dd`, `sgdisk`, `mke2fs`, `blockdev` and `md5sum` are
  real.
- amonet v2.0.0's `update-binary` runs unchanged when a tool installs its zip
  in TWRP.
- Each boot is decided from the disk: the LK in `lk_a`, the TWRP in
  `recovery`, the markers in `expdb` and `misc`, the build in `system_X`, and
  Magisk in `userdata`. A boot0 of zeros boots into the bootrom.

## What is modelled

- `adb`, `fastboot`, `getprop`, `setprop`, `su`, `id`, `bcbtool`, `pm`,
  `dumpsys` and `reboot` are stubs. `twrp install` writes a Fire OS 6 build
  for an OTA zip and marks root adb for any other zip but amonet's.
- The fastbrick writes amonet v2.0.0's chain directly. It runs no exploit.
- amonet v1.1.0's LK clears `FASTBOOT_PLEASE` in `expdb` when it acts on it.
  This is inferred: `fastboot-step.sh` reaches TWRP with the marker still
  written, so the marker cannot hold the Dot in fastboot.
- The bootrom is `sim/bootrom.py`, on a pseudo-terminal, started at the boot
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
- The payload speaks its own command set: v1.1.0's six commands, or v2.0.0's
  ten. Block commands go to the disk files through `sim-emmc` in the
  container. The RPMB is the first 256 bytes of its file. A new Dot's RPMB
  starts `AMZN`.
- The `0x3000` reboot hands the Dot back to the boot rules, 3 s later.
- The port is not modelled: the short, the watchdog, the preloader's
  `0e8d:2000` port and USB packet sizes do not exist here.

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

## The trace

- Every `adb` and `fastboot` call, boot and reboot goes to `trace.jsonl`.
- The bootrom logs each command with its address and words. An upload of more
  than 16 words logs its count and md5.
- The payload logs reads and writes as an area, a first block, a count and
  the md5 of the bytes. Contiguous reads, or contiguous writes, join into one
  range. `--commands` shows the commands each range took.
- `trace.py` puts `$CACHE` and `$TMP` in place of cache and temporary paths.
  It drops the state polls, and prints a line repeated in sequence once.
  `--keep-polls` keeps the polls.

## Traps

- `dd if=/dev/zero` onto a regular file with no `count` does not stop at the
  file's end. One filled Docker's disk. The container was gone, but its loop
  devices still held the deleted file, so the space came back only after a
  Docker restart.
- The ext4 file systems differ on every run. The snapshot compares their file
  trees, not their bytes.

## `--short`, both tools, from no light

Measured on 2026-10-10, both tools from the same no-light Dot.

- Both rooted every target: v1-bboe, v1 and v2.
- The adb and fastboot commands are identical for v1-bboe and v1.
- The bootrom traffic writes the same registers. amonet writes the crypto
  engine one word per command; firebreak writes each block of registers in one
  command.
- Every payload write carries the same bytes in the same order, except the
  partition table. firebreak also reads each region before it writes it, and
  reads it back after. It uses `0x1004` and `0x1003` throughout. amonet reads
  single blocks and zeroes `userdata`'s first 10 blocks with `0x1001`.
- v1-bboe and v1 tables differ in 3 ways. amonet writes its own protective
  MBR, with `0xffffffff` sectors; firebreak keeps LBA 0. amonet gives
  `boot_a` and `boot_b` random GUIDs; firebreak derives them from the disk
  GUID. The headers' two CRCs follow from the GUIDs.
- For v2, dot_firmware installs amonet's zip in TWRP and firebreak writes the
  chain itself. The tables are identical.
- For v2, `lk_a`, `lk_b` and `tee1` hold v1.1.0's old bytes past v2.0.0's
  shorter images, after both tools. firebreak writes whole sectors, so it
  zeroes the rest of each image's last sector: 192 bytes of the LK and 504 of
  the TEE. amonet's `dd` leaves those bytes as they were.
