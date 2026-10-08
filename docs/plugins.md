# Plugins

An unlock is declared. A **device** says what the hardware has; an **unlock**
says what one release of one exploit writes, where, and in what order.
firebreak resolves that plan against the Dot's own partition table and carries
it out.

- A plugin lives in this repository and is reviewed. Nothing is loaded at
  runtime or from the network.
- Every file a plan writes comes from a download pinned by SHA-256.
- An unlock is one upstream release: `amonet-biscuit-v1.1.0` and its bboe
  variant are two unlocks, not one with a parameter.
- A field arrives with the code that reads it.
- A step every unlock can use lives in `firebreak/plugin.py`. A step only one
  release uses lives in that release's module, as a class the core calls.

## Devices and unlocks

`firebreak/devices.py` gives biscuit's name and its features: A/B
slots, a boot0 and an RPMB. An unlock lists the features it requires, and
resolution refuses a pairing that lacks one before anything is written.

`firebreak/unlocks/` holds amonet v1.1.0 and its bboe variant. The plan is
amonet's `modules/main.py` and then its `fastboot-step.sh`, step for step. The
bboe variant swaps the recovery image for TWRP 3.7.0_9-bboe2, a download of its
own, which is why an unlock carries `files` beside its archive.

## The steps

| step | writes |
| --- | --- |
| `ClearBoot0Header` | `EMMC_BOOT` and zeros over boot0's first 8 sectors |
| `ShuffleGpt` | amonet v1.1.0's own: both partition tables, and zeros over `userdata`'s first 10 sectors |
| `ZeroRpmb` | the RPMB, which only the bootrom reaches |
| `Write` | an image, at a sector offset into a partition or boot0 |
| `FastbootFlash` | an image at a partition's start |
| `ForceFastboot` | `FASTBOOT_PLEASE` over the first bytes of `expdb` |
| `ResetBcb` | the 7-byte BCB at 0x160 in `misc`'s second sector |
| `Reboot` | nothing |

An offset is in sectors, as amonet's are. `unrecoverable=True` marks a write
after which a stop needs the eMMC short: biscuit's preloader. The TWRP chain
moves those writes after every other, so a stop anywhere earlier still reaches
the bootrom. That is safe only while no recoverable write covers sectors an
earlier unrecoverable one also writes. No plan does, `tests/test_plan.py`
says so, and the chain does not support one yet.

## Resolution

`firebreak/plan.py` turns a plan into actions: a target, a byte offset on the
disk or in boot0, a length, and the bytes. It checks that every partition
exists and that every image fits its partition.

A step with a `resolved` method, a `TableStep`, rewrites the partition table:
resolution hands it the table and carries on with the one it returns, so the
writes after `ShuffleGpt` resolve against the new partitions.

## The shuffle

amonet v1.1.0 keeps the stock `boot_a` and `boot_b` and boots from two new
partitions at the end of `userdata`. The code is in
`firebreak/unlocks/amonet_biscuit_v1_1_0.py`, and the bboe variant gets it
through v1.1.0's plan:

- round `userdata`'s last sector down to `align`, then give up `sectors` for
  each target
- add one partition per target there, a copy of `userdata`'s entry with a new
  unique GUID
- rename each target to `<target>_x`, and each new partition to the target
- write both tables, then zero `userdata`'s first 10 sectors

A table that already has every `<target>_x` is left alone, so the step can run
again. Against amonet's own `modify_step1`, `modify_step2` and `generate_gpt`
with its GUIDs pinned, the tables are byte for byte the same on four stock
tables, except the protective MBR: amonet writes a size of `0xFFFFFFFF`, and
firebreak keeps the sector it read.

## The recovery executor

`firebreak/recovery.py` carries out a plan's actions with `dd` under TWRP.

- It refuses the whole plan before writing if a step has nothing it can write,
  such as `ZeroRpmb` or `Reboot`. The caller drops the steps its route does
  another way.
- A partition is written through its own `mmcblk0pN`, at an offset into it, and
  each node must be a block device of the size its table entry gives. boot0 is
  unlocked for its write and locked again. A target outside every partition,
  such as the backup table, goes to `mmcblk0` at its absolute offset. TWRP's
  toolbox `dd` cannot reach past 2 GiB there, and nothing refuses such a target
  up front: the run stops at its first read. The TWRP route has none.
- A region that already holds its bytes is skipped. A write smaller than a
  sector is read, patched, and written back whole.
- Every write is staged, pushed, written and read back. A read counts only
  with `dd`'s full record count.

Measured on a Dot at amonet v1.1.0-bboe, with the plan resolved from its own
table: every image region matched byte for byte, each was rewritten and read
back in about 7 s in all, and a run that cleared boot0's header, skipped the
rest and wrote the preloader back left a Dot that booted rooted. Its `misc`
was all zeros: the boot control block is state, not part of the chain, so a
comparison against an installed Dot leaves it out.

## The bootrom executor

`firebreak/bootrom.py` carries out a plan over USB, through any client that
offers `firebreak/emmc.py`'s operations.

- The bootrom checks where its own word writes land. The GCPU's writes skip
  that check, so one engine write clears it, and plain word writes then reach
  anywhere.
- Blocks are absolute and areas are numbered, 0 for the user area and 1 for
  boot0, so an action needs only its offset.
- It does the two steps recovery skips: the RPMB zero and the reboot. The plan
  stops at its first reboot, because a rebooted Dot answers no USB command.
- A region that already holds its bytes is skipped, so a stopped run resumes.
- The payloads speak different command sets, read from each binary's dispatch.
  All take `0x1000`-`0x1002`, `0x2000`, `0x2001` and `0x3000`. Biscuit's
  v2.0.0 adds `0x1003`, `0x1004`, `0x5000`, `0x5002` and `0x5003`. Crown's
  v2.0.1 adds `0x5000` and `0x7000`. So each client pins its binary's SHA-256.
- Offline, against a simulator, the bytes match the amonet code this replaced.
  The one exception is the defeat: the same 535 register writes, in 21 commands
  instead of 47.

## The guardrail

`tests/test_plan.py` resolves both unlocks against biscuit's geometry, from a
stock table and from a shuffled one. Every write must equal what amonet's
scripts issue: kind, target, byte offset and length.
