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
  release uses lives in that device's module, as a class the core calls.

## Devices and unlocks

`firebreak/devices/biscuit.py` gives biscuit's name and its features: A/B
slots, a boot0 and an RPMB. radar, the Echo (2nd Generation), has the same features.
crown, the Echo Show 8 (1st Generation), has a boot0 and an RPMB, but one slot.
An unlock lists the features it requires, and resolution refuses a pairing that
lacks one before anything is written.

A device has a title, the name a message calls it by, such as
`Echo Dot (2nd Generation)`, and the
USB product strings its builds report, its models: `AEOBC` and its TWRPs' model
names for biscuit, and `AEOCW` for crown. Crown's TWRP reports `Echo Show 8`,
which later Echo Show 8 generations can report too. So that name is one of
crown's TWRP models, which count only on TWRP's USB ID, `18d1:d001`, the one
crown's TWRP uses. `firebreak/identify.py` names the connected device from
them, or from the product in fastboot. A target names its device too, `stock`
included, and a run refuses a target for another device.

A device also gives its product, the name its LKs and its fastboot report:
`BISCUIT`, `RADAR` and `CROWN`. It is not always the codename in capitals:
amonet-crown v1.1.1's LK names `CHECKERS`.

A device gives the two gestures its owner is asked for in words of its own:
`fastboot_mode`, the button and the ring that follow it, and `short_gesture`,
where the test point is and what to open to reach it. A device whose test
point no one has found leaves `short_gesture` empty, and `--short` says so and
waits for its bootrom anyway, because it writes nothing while it waits. Only
the location differs: the bootrom behind it is the same part on every device
here.

A device firebreak can unlock lists the LK build descriptions it knows: the
rows of its Builds table in [devices.md](devices.md), and any an Echo has
reported that no OTA there ships. The fastbrick stage refuses a bootloader it
does not find in that list unless the bootloader is dated before the newest
the list carries, because a payload is built for the LKs it targets. A device
that lists none refuses every bootloader, which is where crown stands: it has
a Builds row of its own and lists nothing, because nothing unlocks it here. So
a device gets its LKs in the same change as its unlock.

An LK is named only where it means something other than itself. biscuit names
`AMONET_V1_1_0_LK`, the LK amonet v1.1.0 keeps, which is also the stock LK of
Fire OS 5.5.3.1 to 5.5.4.6, so it says which bootloader a Dot runs and never
whether amonet wrote it: `unlock_status` makes that call. The
downgrade reads it to tell a Dot already on v1.1.0, and the bootrom step to
tell that its unlock took. Everywhere else an LK is its own description: the payload
map is keyed by it, so the map's dates can be read against the image names.
A name for one build that ships an LK would be a second fact to keep right,
where one LK ships in as many as 34 builds.

A device's `FIREOS5_CHAIN` is the earlier amonet it can be on, and the one
place that LK is read. It is a `FireOs5Chain`: the LK, the TWRP version its
unlock installs, that TWRP's download, and the unlock that writes the chain.
Given an `lk_build_desc` and a `ro.twrp.version`, or a reader for `recovery`,
it answers with one of its states or with nothing, as a `Layout` answers for a
table. biscuit declares one and answers the four amonet-fireos5 states and Fire
OS 5's locked fastboot; radar and crown declare `None`, so those five states
cannot be reached on them. The chain is why no module outside
`firebreak/devices/` names an amonet version: `probe` keeps no LK, version or
hash, the downgrade takes its archive, bootloader and TWRP from the chain
rather than from biscuit, and the state names say `fireos5` where they said
`v1.1.0`. A version is only unique to one device, so it says nothing without
one: biscuit's chain is amonet v1.1.0, and radar has no v1.1.0 at all.

`probe` asks the chain of the target's device, or of every device that declares
one before a target names it. Two things stay outside a device: `boot_a_x`,
which is the boot moved layout's name and which `fireos.py` reads too, and the
Fire OS 5 and bootrom build sets, which are still biscuit's wherever they are
read.

An unlock's `little_kernel` is the one other place an LK is named: the
`lk_build_desc` the unlock's own `lk.bin` reports once it is written. It says
that the chain under a Dot is this unlock's, so the TWRP in the same archive
is the one that chain can start, and the stage that leaves amonet v2's
fastboot writes that TWRP only on that proof. An unlock that declares none
gets no write, which is what every device did before, so a wrong guess is a
missing capability and never a recovery that cannot start. Only biscuit's Fire
OS 6 unlock declares one.

An unlock's payload map says which image unlocks each bootloader, and its
`payloads` say which release that image comes from where it is not the
unlock's own. A release can rebuild a payload for the one bootloader its name
carries and lose another, which is what amonet v2.0.1 did to
`41fb3ce-20221007_151724`, so a bootloader can need the archive before the one
the unlock writes. Such an archive is fetched when that bootloader is the one
in front of the run, not with the rest of a target's downloads: no other Dot
needs it.

A device gives the words that ask for fastboot mode, because the gesture is the
device's own: biscuit's names an action button and a light ring, which radar
has too and inherits. crown gives none, so nothing claims a button it may not
have. A run asks through the target's device; the report, which waits for
whatever is plugged in, asks with biscuit's.

A device also lists the partition table layouts a Dot may carry: for biscuit,
boot moved, the table amonet v1.1.0 makes, and stock. radar lists the same
two. Its stock table is biscuit's except where `userdata` ends, and its amonet
has biscuit's `gpt.py`. An unlock that repartitions names the layout it
needs: boot moved for v1.1.0 and its bboe variant, stock for v2.0.0. crown
lists no layout, because no crown table has been read here, and its unlock
does not repartition.

`firebreak/devices/` holds one module per device, named for it, and everything
about that device is in it: the device, its LK build descriptions, its layouts,
the words that ask for fastboot mode, its stock builds and the OTA each one
downloads, its unlocks and its targets. `firebreak/updates.py` keeps only what
every device shares: Amazon's CDN, the pin an OTA is built from, and the
caching a build's download goes through, which takes the builds to look in
rather than reading one device's. Every caller passes the device's own, which
is what makes a second device's pins reachable at all. `biscuit.py` carries
amonet v1.1.0's
chain and amonet v2.0.1, with `crown.py` and `radar.py` carrying one each. A
device's own module is where its next amonet release goes, so a release has no
file of its own and a constant that two releases would share, such as a zip or
a TWRP version, says in its name which release it belongs to.
`firebreak/devices/registry.py` gathers what the core asks for across devices,
and the package re-exports it, so `DEVICES`, `TARGETS`, `DEPRECATED` and
`DEFAULTS` are assembled from each module rather than listed twice. A device
module declares its own `TARGETS`, `WAS_CALLED`, `DEFAULT_TARGET`, `LK_VALUES`,
`FIREOS5_BUILDS`, which of its builds are Fire OS 5 and so show nothing on USB
once they start, `FASTBRICK`, the unlock whose archive holds its fastbrick
payloads, `FIREOS5_CHAIN`, the earlier amonet it can be on, and
`BOOTROM_UNLOCK`, the chain to write to an Echo held in its bootrom; a
device with no target or LK yet declares them empty, and names neither a
fastbrick nor a bootrom chain, because every device a run can take anywhere is
reachable from stock fastboot and so needs the first. A module that leaves
`BOOTROM_UNLOCK` or `FIREOS5_CHAIN` out does not import, and one that declares
either `None` has no such route: a run that finds a device with an erased boot0
and no bootrom chain says so and writes nothing. Each plan is amonet's
`modules/main.py` and then its `fastboot-step.sh`, step for step. The Fire
OS 5 unlock writes TWRP 3.7.0_9-bboe2, a download of its own, which is why
an unlock carries `files` beside its archive. The bootrom route writes the
same chain, but stops at the reboot, before any fastboot step. So each chain it
writes has an unlock of its own, built from the target's with one step changed.
The Fire OS 5 one takes amonet's own TWRP out of the zip, so it downloads
nothing. The Fire OS 6 one gains `ClearBoot0Header` in front, which only the
bootrom route needs: the fastbrick carries out that plan from the LK, where
boot0 is not the way back.

amonet-radar v1.0.0 runs biscuit v2.0.0's scripts and payload byte for byte,
and its `main.py` differs only in file names and one log line. So its plan is
v2.0.0's, with `radar-kaeru.bin` in `expdb`, and its module builds it from
v2.0.0's. Its targets take biscuit's routes and gesture, and the amonet states,
because it declares no Fire OS 5 chain. Its archive also holds the bootrom
payload, byte for byte biscuit's, so a radar run unpacks its own rather than
fetching biscuit's zip for one file.

amonet-crown v2.0.1's `main.py`, from the bootrom, writes what biscuit's
v2.0.0 writes, in the same order, with crown's names: one `lk`, `MISC` in
capitals, and `crown-kaeru.bin` in `expdb`. It also clears boot0's header
first, as v1.1.0 does, and it does not repartition. As in v2.0.0, a run from
the preloader leaves boot0 alone, and the plan leaves that branch out. Its
`fastboot-step.sh` writes TWRP to both `recovery` and `swdl`. Its LK and TEE
are Fire OS 6 8149's, byte for byte. Its zip is also a TWRP install, which the
plan leaves out. No target uses it yet, as for radar.

amonet-crown v1.1.1 is not needed: it does nothing that v2.0.1 does not.

A **target** is what a run ends on: its goal state, the OS it installs, and its
unlock, which stock has none of. A Fire OS 6 target names a build from Amazon's
updates, which TWRP installs as it is; stock's build is the one named on the
command line, or the device's own default, which its module holds. A Fire OS 5
target names its update package, from which firebreak builds a system image to
write with dd, with Magisk beside it.
Each device module holds its own targets, biscuit's three and radar's two, and
its default. Every device firebreak can take anywhere has a `stock` target;
only one it can unlock has an unlock target, so crown names no target at all
and is not a `--device` choice. Their goal states are in
`firebreak/states.py`, a module outside the devices package, so a device module
can name a state without the registry's imports forming a cycle. A target's
summary is its line in `--help`, which lists each device's commands, and the
unlock targets under `unlock` with the default first.

v2.0.0's `main.py` has two branches its plan leaves out: `fixgpt`, a manual
mode that writes its own table, and a run from the preloader, which leaves
boot0 alone. firebreak reaches the bootrom, so the plan writes the preloader.

From an amonet v1.1.0 TWRP, firebreak carries out v2.0.0's plan in place of
its zip: docs/unlocking.md has the route. From stock, the fastbrick unlocks
the Dot instead. In the plan, as in `main.py`, `FASTBOOT_PLEASE` lands after
the preloader, so a bootrom route that stops between the two is past a
resume and has no fastboot marker. The TWRP route leaves that step out.

## The steps

| step | writes |
| --- | --- |
| `ClearBoot0Header` | `EMMC_BOOT` and zeros over boot0's first 8 sectors |
| `Repartition` | whatever moves the table from the layout it is in to the unlock's: see [Layouts](#layouts) |
| `ZeroRpmb` | the RPMB, which only the bootrom reaches |
| `Write` | an image, at a sector offset into a partition or boot0 |
| `FastbootFlash` | an image at a partition's start |
| `ForceFastboot` | `FASTBOOT_PLEASE` over the first bytes of a partition: `expdb` for v1.1.0, `misc` for v2.0.0 |
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

At `Repartition`, resolution asks the device's layouts, in its order, which
one describes the table, and refuses a table none describes before anything is
written. If that one is not the unlock's layout, it reverts it and applies the
unlock's, and carries on with the table that gives, so the writes after it
resolve against the new partitions. A table already in the unlock's layout
gives no action. The step sits where amonet's own scripts change the table,
because the order matters: v1.1.0 clears boot0's header first, so a stop after
it reaches the bootrom.

## Layouts

`firebreak/layouts.py` holds each layout and both ways across it, so the
shuffle and its undo sit together. A layout's numbers are the device's:
biscuit's are in `firebreak/devices/biscuit.py`.

Stock is the table the factory wrote, whatever Fire OS runs on it. Its layout
describes any table with the device's stock partition count, 16 on biscuit,
which is a check on the count alone. biscuit lists it after boot moved, so a
half-moved table is refused before the count is read. No OTA
writes the partition table: Fire OS 5.5.5.4's and Fire OS 6 4315's write
system, boot, LK, TEE and the preloader, and the `payload.bin` of 4405,
5041, 6302, 8142, 8146 and 8149 carries just those five. Every table read here
came from one Dot, so a change between production runs is not ruled out.

### Boot moved

`BootMovedLayout` is the table amonet's `gpt.py` calls patched. amonet
v1.1.0 keeps the stock `boot_a` and `boot_b` and boots from two new
partitions at the end of `userdata`. The same code is in every amonet release
read here, for biscuit, radar and crown, with the same alignment and sizes;
only the targets differ, `boot` and `recovery` on crown. Of those releases,
only biscuit's v1.1.0 applies it. biscuit's v2.0.0 and radar's v1.0.0 undo
it, and radar's says an older release applied it. Applying it:

- round `userdata`'s last sector down to `align`, then give up `sectors` for
  each target
- add one partition per target there, a copy of `userdata`'s entry with a
  unique GUID derived from the disk GUID and the target's name
- rename each target to `<target>_x`, and each new partition to the target
- write both tables, then zero `userdata`'s first 10 sectors

A table with some `<target>_x` but not all is refused. Against amonet's own
`modify_step1`, `modify_step2` and `generate_gpt` with its GUIDs pinned, the
tables are byte for byte the same on four stock tables, except the protective
MBR: amonet writes a size of `0xFFFFFFFF`, and firebreak keeps the sector it
read.

Reverting it, which amonet v2.0.0's `main.py` does before it writes:

- drop the partitions after `userdata`, one per target, and end `userdata` at
  the table's last usable sector
- rename each `<target>_x` back to the target

Where amonet's `unpatch` blanks the last two entries whatever they are, this
refuses a table that does not end in `userdata` and the targets, or that lacks
a `<target>_x`.

Against amonet's own `unpatch` and `generate_gpt`, both tables are byte for
byte the same on seven tables from one Dot: three shuffled on the Dot, and
four stock ones shuffled first. The protective MBR differs as it does for the
shuffle.

## The recovery executor

`firebreak/recovery.py` carries out a plan's actions with `dd` under TWRP.
Its `carry_out` is the TWRP route in `docs/unlocking.md`. The caller passes what
is not the plan's: the check that the Dot is amonet's, the step before the
preloader, the partitions to zero, and the reboot after.

- It refuses the whole plan before writing if a step has nothing it can write,
  such as `ZeroRpmb` or `Reboot`. The caller drops the steps its route does
  another way.
- A partition is written through its own `mmcblk0pN`, at an offset into it, and
  each node must be a block device of the size its table entry gives. boot0 is
  unlocked for its write and locked again. A target outside every partition,
  such as the backup table, goes to `mmcblk0` at its absolute offset.
  `toybox dd` reaches it. A TWRP with only toolbox `dd` cannot reach past
  2 GiB, and nothing refuses such a target up front: the run stops at its
  first read.
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

`tests/test_plan.py` resolves every biscuit unlock against biscuit's geometry,
from a stock table and from a shuffled one. It resolves amonet-radar v1.0.0
from a radar stock table and one with boot moved too, and amonet-crown v2.0.1
from a made-up crown table. Every write must equal what amonet's scripts issue:
kind, target, byte offset and length. Reverting the boot-moved layout after
applying it, and v2.0.0's repartition of a v1.1.0 table, must each give back
the stock table byte for byte.

The tests use made-up images and a radar table copied by hand. Once, by hand
and outside the tests, the plan was resolved against amonet-radar's own
`gpt-radar.bin` and images, from that table and from it with boot moved. It
fit every partition and gave back the stock table.
