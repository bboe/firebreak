# Devices

The firmware each supported device's OTAs ship. radar has a `stock` target and
an unlock, both on 8349. donut declares an unlock and a `fireos6` target, and
is named by the hardware code its bootrom reports rather than by a bootloader;
the whole route has run on a donut, three times, including with
`--factory-reset`. crown declares
an unlock and no target, so no route reaches it, and that unlock has never run.
The other nineteen devices here declare nothing at all, and are here because
their OTAs are read the same way: crumpet, doebrite, pascal, sonar, lidar,
laser, brownie, ganache, cannoli, cheesecake, churro, checkers, croissant,
cupcake, octave, pablo, sapphire, kyanite and cronos.

`firebreak survey OTA` prints, from one OTA zip and nothing else, what its
row in a Builds table and its rows in a partition hash CSV say: the build
descriptions, the anti-rollback versions, the TEE's hashes and the partition
hashes: 5 of them on biscuit, radar, crown, sonar, checkers and cronos, 6
where an OTA names two TEE partitions as donut's, lidar's, laser's, cupcake's,
octave's, pablo's, sapphire's and kyanite's do, 9 on crumpet, doebrite, pascal
and croissant, which add four boot0 partitions, 12 on brownie and ganache, and
14 on cannoli, cheesecake and churro, which add `scp` and `mcupm`.
The TEE it reports is the first of those, and it says so where the two differ.
Only the fastbrick image comes from elsewhere, amonet's
`profile.sh`. It needs no Dot. Its CSV rows name the build as the CSVs do,
so each is a line of its CSV, word for word.

Every CSV row starts with the device's codename and model, so the CSVs can
be joined into one table. The model is `ro.product.model`, which every OTA of
a device gives the same. The codename is `ro.product.device` without
`_puffin`. Biscuit's and radar's Fire OS 6 OTAs add that suffix: they are
built from a second device tree, `device/amazon/biscuit_puffin`, where their
Fire OS 5 OTAs say `biscuit`. Crown shipped on Fire OS 6 and has no suffix.
Donut shipped on Fire OS 6 too, and its OTAs gain the suffix part way through:
1895 says `donut` and every later build says `donut_puffin`. So the suffix does
not mark a move from Fire OS 5, and what it does mark is unread. No OTA says.

## biscuit

The Echo Dot (2nd Generation). Read on 2026-11-06 from all 50 OTAs ftvdb
lists: 40 Fire OS 6 builds, 4310 to 8349, and Fire OS 5.4.2.7, two of
5.5.0.3, 5.5.3.1, 5.5.3.3, 5.5.3.6, 5.5.4.6, 5.5.4.9, 5.5.5.0 and 5.5.5.4.
8338 and 8344 were first read in October from the OTAs Amazon's own CDN
serves, which is where a Dot on 8338 led, before ftvdb listed them.

ftvdb lists two 5.5.0.3 builds, 564196920 and 564197320. Each OTA's
`target.build.prop` gives the first `ro.build.lab126.build` 1969 and a build
date of 2016-12-01, and the second 1973 and 2016-12-29. They share the LK, the
TEE and the preloader's description and version. 1973 adds the `COMPUTER`
wake word for en-US, en-GB and de-DE, two alert sounds and the locale code
that finds the new models. Its kernel is 1969's rebuilt: the two decompress to
the same length and differ in 140 bytes, its timestamps and build ID among
them. Everything else that differs is a signature, a version string or a file
built from one. 1969 keeps the name `5.5.0.3`, which 1.0 used, and 1973 is
`5.5.0.3-1973`. `survey` labels both `Fire OS 5.5.0.3`, so 1973's rows in the
table are named by hand.

`ro.build.lab126.build` is the number in every Fire OS 6 build's name, read on
2026-11-06 from the OTAs of 1895, 4305, 4310, 4315, 4655, 5041, 6302, 8149
and 8349. Fire OS 5 counts its own: 1969 to 7676, from 2016 to 2022, the
middle four digits of `ro.build.version.number`. The two counters overlap in
range though no build here shares a number, so only a version can name a
Fire OS 5 build safely.
[unlocking.md](unlocking.md#echo-dot-2nd-generation) has the routes this
device alone takes.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 8338 to 8349 | `2c3569d-20260617_045829` | `bd7ae89-20221003_215949` | [6](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20260617.img` |
| Fire OS 6 4929 to 8149, except 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [5](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4405 to 4781, and 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [4](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4310, 4313, 4315 | `41fb3ce-20221007_151724` | `919cae9-20221006_203733` | [3](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img`, v2.0.0's |
| Fire OS 5.5.5.4 | `beb022a-20211202_231918` | `ed021f9-20211202_231918` | [2](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.4.9, 5.5.5.0 | `a828f29-20210822_210511` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.4.2.7, and 5.5.3.1 to 5.5.4.6 | `f379dba-20170906_000423` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.0.3, 5.5.0.3-1973 | `0e1d0d9-20161018_220224` | `292ae9d-20160915_232723` | [1](#tee-images) | 0x0003, 0x0102, 0x0001 | `fastbrick.img` |

- Only the LK chooses the fastbrick image.
  [unlocking.md](unlocking.md#unlock-amonet-v2)
  says how, and why one row takes that image from amonet v2.0.0 where the
  others take v2.0.1's.
- The preloaders of one row differ between builds only in boot0's GPT, whose
  partition GUIDs are random.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 6 | 1781760 | `9a9360025342b3a55d943e64ccc8617f` | `d64116ded3e255468d9a995fe91fe5dc257d4de4a991cfe4d3fa6ce544996757` |
| 5 | 1781760 | `196a1873db19a1e862a4f07057e57482` | `d363175c9f2a4f1dad5fb317303d12758f0c5617848dc3564b6f574581a86a71` |
| 4 | 2813952 | `52e8575f206c927239fafc995533a30e` | `8f2f5ca4862088a849d8cae90e6647d1f022214f4b4e5cce80cc8faa52cab526` |
| 3 | 2812928 | `78f671ba4540a70e760459ce54a1a5fa` | `f4ec7c909c610f1b915c5bc3e9e995b97d554b9ac99018818a0055a19cdd326e` |
| 2 | 2641920 | `8ef5717ad9b232403bb2447918e0cdcd` | `fe1de9f18aa0f82a308f0c08da3be1f7c7ac2fd65832e26a3a6bdeb0e6e10136` |
| 1 | 2625536 | `dbb59ab6087405f9a26dd827ef54fda8` | `855f06bf48bacd1e96424307b3a5e343c7865d917de88b4fd839123c9f419797` |

- Each hash covers the image only. To match a Dot's `tee1` or `tee2`, hash
  its first N bytes, where N is the bytes column.
- The ATF and TEE inside each image are encrypted. The preloader unwraps
  their key with the SoC's hidden key, so no OTA shows a TEE build string.

### Anti-rollback

The preloader compares three versions with the ones in RPMB, and fastboot
reports them as `antirback_pl_version`, `antirback_tee_version` and
`antirback_lk_version`.

- PL: a constant in the preloader's code. After the check loads the string
  `[ANTI-ROLLBACK] Updating PL version`, its second `bl` calls a Thumb-2
  function that is `movs r0, #N` and `bx lr`. N is the version.
  `firebreak survey` reads it without a disassembler: it finds the `ldr` from
  a literal and the `add rN, pc` that make the string's address, and decodes
  the `bl`s after them. Every address it uses is relative to the code, so it
  needs no load address.
- TEE: the 16 bits at offsets 0xf and 0x10 of the TEE's plaintext
  `EET KTM` header, high byte first.
- LK: the 16 bits after `LK` in the LK's signature trailer, high byte first.
- A stock 8146 Dot read `0x0005`, `0x0102` and `0x0001`.
- PL rose from 3 to 5 after 5.5.0.3. TEE and LK are the same in every OTA.
- A version in RPMB that is higher than the preloader's stops the boot at
  `version mismatch!`, in a loop that only the eMMC short gets out of. The
  short reaches the bootrom, not a boot: the Dot boots again only once its
  RPMB is zeroed or a preloader at least as high is written. A lower version
  is raised to the preloader's. This is read from the 8146 preloader's code.
- Seen on a Dot that had run Fire OS 6, 2026-10-14: after the bootrom zeroed
  RPMB, 5.5.0.3's preloader, PL 3, booted. The mismatch loop and the raise
  have not been seen.

### Partition hashes

[biscuit-partitions.csv](../firebreak/devices/biscuit-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for every build above:
boot, `/system`, lk, tee and the preloader. `firebreak backup` reads the same
file to name an OTA image in place of a copy.

- A hash covers the image's own length, in `bytes`, and the partition is
  larger. Hash that many bytes from the partition's start, on the active slot
  (`ro.boot.slot_suffix`). The preloader is the first 1 MiB of boot0.
- An A/B OTA's hashes are the ones in its `payload.bin` manifest. Every
  payload is a full image. `/system` rebuilt from 8146's payload matched its
  manifest.
- A block OTA's hashes are of the files in its zip, and of `/system` rebuilt
  from `system.new.dat` with the blocks it does not write as zeros. That is
  Fire OS 5, and Fire OS 6 4310 to 4315.
- Those `/system` hashes match a Dot that firebreak restored, because it
  writes the zeros too. Amazon's updater erases those blocks and does not
  write them: 20,458 of them on 5.5.5.4 and 79,822 on 4315. An erased block
  reads as whatever the eMMC chip returns, so a Dot that Amazon's updater
  installed matches only if its chip returns zeros.
- Every build has its own boot, `/system` and preloader hash. The preloaders
  differ only in boot0's GPT.
- A rooted Dot matches no row. Fire OS 6 keeps its root filesystem in
  `/system`, and amonet v2.0.0's `boot-root.zip` changes 6 files there:
  `default.prop`, `fstab.mt8163`, `init.fosflags.sh`, `sbin/adbd`, `sepolicy`
  and `system/build.prop`, whose `ro.build.version.number` becomes
  `4503599628407428`. A v2 Dot on 8146's `/system` filesystem differed from
  8146's in those files only.
- `boot-root.zip` also writes outside those files, on both slots. It writes
  `VOFF` over the verity metadata's magic, `01b001b0`, after `system_X`'s hash
  tree. It sets `buildvariant=userdebug` on `boot_X`'s command line. So a
  rooted Dot's boot and `/system` hashes both differ from every row.
- `boot-root.zip` patches what it finds and does not carry biscuit's files. It
  finds adbd's autoroot by a byte pattern. It patches the sepolicy with
  `magiskpolicy32`, and falls back to a policy it bundles, chosen by the
  stock policy's md5.

### eMMC chips

Read as root from `/sys/block/mmcblk0/device/` (`name`, `manfid`, `date`)
and from each boot area's `size`, in 512-byte sectors.

| chip | maker | date | boot0, boot1 | Dots |
| --- | --- | --- | --- | --- |
| `P1J94M` | Micron (`0xfe`) | 08/2016 | 1 MiB each | 2 |
| `FJ25AB` | Samsung (`0x15`) | 03/2017 | 4 MiB each | 1 |

- Every stock `preloader.img` is 1 MiB, so boot0 can be larger than it. The
  stock restore pads the preloader with zeros to boot0's size.
- The same `/system` write took 79 s on `P1J94M` and 41 s on `FJ25AB`.

## radar

The Echo (2nd Generation), model XC56PY. Read on 2026-11-06 from all 21 OTAs
ftvdb lists: Fire OS 5.5.5.4 and Fire OS 6 4305, 4315, 4929, 4936, 5555, 5571,
6009, 6071, 6199, 6208, 6220, 6302, 6425, 6436, 6813, 7577, 8149, 8338, 8344
and 8349. ftvdb has no other radar OTA.
[unlocking.md](unlocking.md#echo-2nd-generation) has what this device alone
does.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 8338 to 8349 | `2c3569d-20260617_051433` | `bd7ae89-20221003_221237` | [3](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick-20260617.img` |
| Fire OS 6 4929 to 8149 | `63cb91b-20221007_073612` | `bd7ae89-20221003_221237` | [2](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4305, 4315 | `41fb3ce-20221007_153017` | `919cae9-20221006_205014` | [4](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.5.4 | `59779ca-20220524_183401` | `642551b-20211203_021230` | [1](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick-20220524.img` |

- amonet-radar v1.0.1's `profile.sh` chooses the fastbrick image by the LK, as
  biscuit's does. 5.5.5.4's LK, `63cb91b` and `2c3569d` each get an image of
  their own, and `41fb3ce` gets the default, `fastbrick.img`. v1.0.0 mapped
  only 5.5.5.4's and gave both Fire OS 6 LKs the default, and had no image at
  all for `2c3569d`, so `stock` offered none of 8338, 8344 or 8349 and
  `unlock` refused them.
- `fastbrick-20260617.img` is radar's own, not the biscuit image of the same
  name: 114431594 bytes against 114432500, and of the 33883 distinct 16-byte
  windows in its last 137684 bytes, at a 4-byte stride, 33735 are in 8349's
  `lk.img`, against 30663 in 8149's and 26498 in biscuit's 8344's. Read as
  [unlocking.md](unlocking.md#unlock-amonet-v2) reads a payload's tail.
- v1.0.1 rebuilt three files v1.0.0 shipped, beside the two it adds:
  `radar-kaeru.bin`, which the chain writes to `expdb`, is 264304 bytes
  against 264544; the default `fastbrick.img` and `fastbrick-20220524.img` are
  each within a few hundred bytes of their old size with different bytes.
  Everything else the chain writes is byte for byte v1.0.0's, the bootrom
  payload and `modules/main.py` included, so the plan is unchanged.
- `fastbrick-20260617.img` unlocked a radar on `2c3569d-20260617_051433`
  three times on 2026-11-01, each on the first flash of its run: from a locked
  8338 in 13 s, and from a locked 8344 and a locked 8349 in 8 s each, rooting
  each build in place in 2 min 42 s, 1 min 10 s and 1 min 10 s. So the mapping
  that payload's tail predicted holds on an Echo, as biscuit's
  `fastbrick-20260617.img` did on a Dot, and it covers all three builds that
  share the LK.
- Radars also ship builds that ftvdb lacks. One bought second-hand held Fire OS
  6.5.7.0 (NS6570/6071) in slot b, read on 2026-11-04. Its stock fastboot gave
  `63cb91b-20221007_073612` and anti-rollback 0x0005, 0x0102, 0x0001, the 4929
  to 8149 row, and `fastbrick-20221007.img` unlocked it. Its stock preloader
  was not read before the unlock replaced it. firebreak has no OTA for 6071,
  so `unlock` refuses to root it in place, and `--factory-reset` took it to
  rooted 8149 in 4 min 12 s.
- Another radar's stock fastboot gave `ae269a7b-20170719_072038`, reported
  on 2026-11-17: a 2017 LK in no OTA here, with an 8-digit commit and no
  anti-rollback versions at all. Git lengthens an abbreviated commit past 7
  digits when 7 are not unique, so firebreak reads 7 or 8, the longest seen.
  No fastbrick image is mapped to that LK. The default `fastbrick.img` was
  tried on it the same day, from Windows: all 10 flashes returned, so the
  exploit did not start and the Echo was not modified.
- `fastbrick-20221007.img` unlocked a radar on `63cb91b-20221007_073612`,
  2026-11-01, on the first flash: a locked 8149 reached TWRP 32 s after a 13 s
  fastbrick and rooted in place in 1 min 16 s. v1.0.0 gave that LK the default
  image, so this is the mapping v1.0.1 changed for every radar on 4929 to
  8149.
- `fastbrick-20220524.img` unlocked a radar on `59779ca-20220524_183401`,
  2026-11-01, on the first flash: a locked 5.5.5.4 reached TWRP 29 s after a
  13 s fastbrick, and the run installed 8149 over both slots and rooted it in
  3 min 54 s. That was the last of v1.0.1's five mappings to run on hardware,
  so **every image v1.0.1 rebuilt or added is now measured on an Echo**.
- amonet-radar's `bin/lk.bin` is radar's stock 5.5.5.4 LK, unmodified:
  356856 bytes equal to the first 356856 of that OTA's `lk.img`, whose last
  3592 bytes are zeros. v1.0.0 and v1.0.1 ship the same file. So radar's
  unlocked bootloader is a stock Fire OS 5 one, where biscuit's is a patched
  Fire OS 6 one, and `stock 5.5.5.4` skips both LK writes on a radar that
  amonet's chain has written.
- The rebuilt `radar-kaeru.bin` is on an Echo. A `bootrom` run on 2026-11-01
  reported the kaeru write as already right, so `expdb` held bytes equal to
  v1.0.1's image, and the only runs that could have put them there are that
  day's fastbrick unlocks, which run the same plan. Every unlocked boot of
  2026-11-01 came off it.
- The default `fastbrick.img` unlocks a radar on 4305, measured on 2026-10-29
  from stock fastboot: the fastbrick took 13 s, TWRP started 28 s later, and
  the run rooted 4305 in place in 1 min 11 s with no restart by hand. v1.0.1's
  rebuilt image did the same on 2026-11-01, in 13 s on its first flash and
  1 min 10 s to a rooted 4305. Their LK
  is `41fb3ce`, the same commit as biscuit's 4310 to 4315 LK. On biscuit, that
  LK is unlocked by the image its `63cb91b` LK gets, which amonet's own map
  does not give it. On radar, amonet's map does give it that image. 4315 shares
  the LK and the preloader, and is not measured on its own.
- The preloaders of one row differ between builds only in boot0's GPT, as on
  biscuit.
- No OTA raises an anti-rollback version, and none is higher than biscuit's.
  Each is read as biscuit's are, in [Anti-rollback](#anti-rollback).

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 4 | 2812928 | `78f671ba4540a70e760459ce54a1a5fa` | `f4ec7c909c610f1b915c5bc3e9e995b97d554b9ac99018818a0055a19cdd326e` |
| 3 | 1781760 | `669a952109fd134b4588afb719603fcf` | `76774007979064e329eb1fd6e87053b8ab72853680e9b370b51805bc13634bc0` |
| 2 | 1781760 | `13a2f357ddf719afccfb707a7f1668d2` | `15cd40caafa6cd8bb8c4e4ed173c973569a8a2b026235d81776ec888f1522c72` |
| 1 | 2641920 | `2ce20a3462ab227aa750c0f9c026d6d3` | `80e54029f5defc087ff14e5da27dd9739cbf9f684b2ed8bdc3803fd1b77db856` |

- 4 is the same image as biscuit's [3](#tee-images). Each radar TEE is
  numbered here, so a number in the table above is always radar's own.

### Partition hashes

[radar-partitions.csv](../firebreak/devices/radar-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for every build above,
read as biscuit's are.

- 5.5.5.4, 4305 and 4315 are block OTAs. As on biscuit, a radar that Amazon's
  updater installed matches their `/system` only if its eMMC reads erased
  blocks as zeros.
- The three readings below need what is inside `/system`, not its hash, and
  cover only the ten OTAs read before 2026-10-28. 4315, 4936 and 8149 are
  unread too and do not need the reading: `boot-root.zip` rooted each of them
  in place on a radar on 2026-10-29, in 1 min 11 s to 1 min 13 s, which is the
  stronger test.
- 8338, 8344 and 8349 need no reading either: `boot-root.zip` rooted each in
  place on a radar on 2026-11-01, in 9 s, 8 s and 9 s, which is the stronger
  test. So every radar build the zip can reach has now run it.
- Each of the nine Fire OS 6 builds among them has what biscuit's
  `boot-root.zip` changes: each file, one autoroot site in `sbin/adbd`, a
  `veritykeyid` boot command line, and verity metadata at the offset the zip
  computes.
- `boot-root.zip` patches the sepolicy with `magiskpolicy32`. If that fails,
  it falls back to a bundled policy, and only radar 6302's and 6813's stock
  policy, `8f6dd232a590337314bb372e84b84e77`, has one. Nothing here has run
  it on a radar.
- The stock sepolicy md5 of each of those nine: 4305 `d88b3344`, 4929
  `88d5111f`, 6199 to 6220 `59fb0d21`, 6302 and 6813 `8f6dd232`, 6425 and
  6436 `ac9825e8`. Build numbers do not follow release order: 6302 is Fire
  OS 6.4.6.6, and 6813 is 6.5.6.6.

### eMMC chips

Read as biscuit's are, and from `report` on 2026-10-28.

| chip | maker | date | boot0, boot1 | sectors | Echoes |
| --- | --- | --- | --- | --- | --- |
| `P1J94M` | Micron (`0xfe`) | 09/2017 | 1 MiB each | 7651328 | 1 |
| `FJ25AB` | Samsung (`0x15`) | 09/2017 | 4 MiB each | 7634944 | 1 |

- Both chips also turn up in biscuit, on other dates.
- **The two differ in capacity**, by 16384 sectors, so the last usable sector
  and the place of the backup table differ between them: 7634910 and 7634943
  on the `FJ25AB` one. A restore builds the table from the Echo's own rather
  than from a fixed one, which is what makes that safe.
- boot0 is 1 MiB on the `P1J94M` one and 4 MiB on the `FJ25AB` one, as on
  biscuit, and every stock `preloader.img` is 1 MiB, so the restore pads it
  with zeros to boot0's size.
- `report` also reads `prv`, `pre_eol_info` and `life_time`. The `FJ25AB` one
  read `0x2`, `01` and `0x01 0x01`, and the `P1J94M` one `00` and
  `0x00 0x00`. These say how worn the card is; neither is near its limit.
- An Echo with an 8 GB eMMC has been seen, and nothing about its chip or its
  table was written down. Running `report` once on one would fill this in.

## crown

The Echo Show 8 (1st Generation), whose OTAs give `ro.product.model` as
`AEOCW`. Read in October 2026 from the 19 OTAs on ftvdb: Fire OS 6 6074 to
8149. Their `ro.build.version.name` runs from Fire OS 6.5.7.0 to Fire OS
6574.1, as biscuit's 8146 also names itself. ftvdb has no other crown OTA.
Crown's build numbers are its own: its 6208, 6436, 8146 and 8149 are not
biscuit's or radar's builds of those numbers.
[unlocking.md](unlocking.md#echo-show-8-1st-generation) says why no route
reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 6074 to 8149 | `44072a3-20240709_164449` | `79a3b50-20231019_080950` | [1](#tee-images-2) | 0x0001, 0x0102, 0x0001 | `fastbrick.img` |

- Every OTA ships the same LK and TEE. The preloaders differ between builds
  only in boot0's GPT, as on biscuit.
- Crown has one slot: one `boot` and one `lk`. Each OTA writes its TEE to both
  `tee1` and `tee2`. Its updater script also extracts `images/MBR` to the
  disk, but no OTA holds that file. The extract fails, the script does not
  check it, and nothing is written there.
- The PL version is 1, where biscuit's and radar's are 5. No OTA raises an
  anti-rollback version. Each is read as biscuit's are, in
  [Anti-rollback](#anti-rollback). After the string, crown's preloader runs
  the same code as radar's: the log call, the call that returns N, a store
  of N into the same field, and the same compare.
- amonet-crown v2.0.1's `profile.sh` gives every LK the default image,
  `fastbrick.img`. Its map of LK-specific images is empty.
- amonet-crown v2.0.1 writes this LK and this TEE, byte for byte, and a
  preloader from 2019, `1fce15f-20190917_183143`, at PL version 1.
- amonet-crown v1.1.1 writes an LK from 2019, `4c6677c-20190328_014231`, at
  LK version 0, below the OTAs' 1. Its TEE is at 0x0103, above the OTAs'
  0x0102. Its preloader is `79a3b50-20231019_082513`, at PL version 1: the
  OTAs' commit, built 15 minutes later.
- Both amonet-crown releases zero RPMB before they write, so the versions RPMB
  held cannot stop the boot. This is read from their `main.py`, not seen on a
  crown.
- Once v1.1.1's TEE boots, RPMB can hold TEE version 0x0103. A later write of
  any OTA's TEE, at 0x0102, would then stop the boot unless RPMB is zeroed
  first. This is read from the anti-rollback check, not seen on a crown.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2533376 | `a5bf748b2351a424f5016cd45fbc0c26` | `fb8f7ee4de59aab1fea4b3fc99e76aa575bf46b1aef165ea367a1e44c6713c50` |

### Partition hashes

[crown-partitions.csv](../firebreak/devices/crown-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every crown OTA is a block OTA. As on biscuit, a crown that Amazon's updater
  installed matches its `/system` hash only if its eMMC reads erased blocks as
  zeros. Amazon's updater erases and does not write 119,598 to 132,373 of the
  794,368 blocks, depending on the build.
- Every build has its own boot, `/system` and preloader hash. `/system` is
  3,253,731,328 bytes in every build.
- Crown has no slot suffix. Hash `boot`, `system`, `lk` and `tee1` by name,
  where biscuit's steps say to use the active slot.

## donut

The Echo Dot (3rd Generation) of 2018, model `AEODN`. Read on 2026-11-06 from
all 26 OTAs ftvdb lists: Fire OS 6 1895, 4655, 4769, 4774, 4936, 5531, 6009,
6071, 6077, 6086, 6176, 6193, 6199, 6208, 6220, 6425, 6554, 6562, 6813, 8138,
8142, 8146, 8149, 8338, 8344 and 8349. ftvdb has no other donut OTA, and none
is Fire OS 5. Its build numbers are its own, as crown's
are, and they do not follow release order: 6813 is Fire OS 6.5.6.6, where 6425
is 6.5.7.2.

The Echo Dot (3rd Generation) Refresh of 2019 is a different device, model
`AEOCP` and codename crumpet. [crumpet](#crumpet) covers it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6176 to 8349, except 6813 | `6f7225e-20230407_013816` | `20231103_081354` | [3](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 6009 to 6086, and 6813 | `6f7225e-20230407_013816` | `20231103_081354` | [2](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 5531 | `6f7225e-20230407_013816` | `20231103_081354` | [4](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 4936 | `6f7225e-20230407_013816` | `20230726_074325` | [4](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 4769 and 4774 | `6f7225e-20230407_013816` | `20230607_222935` | [4](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 4655 | `0db8914-20221005_072344` | `20220323_070214` | [4](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 1895 | `0d18cf4-20181206_233555` | `20181206_233555` | [1](#tee-images-3) | 0x0001, 0x0001, 0x0001 |

- The table has no fastbrick column. kamakiri-donut v1.0.0 ships no fastbrick
  image and no `profile.sh`, where every amonet release here ships both, so no
  LK of donut's chooses one.
- No donut preloader carries its commit as text, so `pl_build_desc` is the
  `Build Time` string alone, as crumpet's is. A donut in fastboot reports the
  commit as well, and
  [measurements.md](measurements.md#a-stock-echo-dot-3rd-generation-in-fastboot)
  says where the two readings meet. Five preloaders ship across the 26: 1895's,
  of 147456 bytes, and four of 151552 bytes. 4655 has one, 4769 and 4774 share
  one, 4936 has one, and 5531 and the twenty builds after it ship the same one
  byte for byte. 1895's preloader and its LK carry one timestamp between them.
  Where biscuit's and radar's preloaders of one row differ only in boot0's GPT,
  donut's five are five builds, so the rows above split where one row held
  several of them.
- Three LKs ship: 1895's, 4655's, and one in every build from 4769. Each is
  read as biscuit's are, in [Anti-rollback](#anti-rollback).
- Every version is 1. The PL version is 1 as crown's is, where biscuit's and
  radar's are 5, and the TEE version 0x0001 is the lowest here, which crumpet,
  doebrite, pascal and lidar carry too and biscuit, radar, crown and sonar do
  not. No OTA raises one.
- kamakiri-donut v1.0.0 writes the LK of 4769 and later byte for byte, and
  the TEE of 6176 and later byte for byte. Its preloader is in no OTA.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 4 | 2367488 | `e3cf83a0d0b5479147013427112a4a83` | `c6fad5635a8760bfb741b3cf2339abf582a4b509263aacc9445dca081bdf2eb6` |
| 3 | 2363392 | `3838fb54db104f8fe9799484afdd77e2` | `07cff71c598b7665f17c769b0504c8b7ad91647414c280b10a26be4ea5761194` |
| 2 | 2367488 | `5f0569a8c128a3288f962937a0a0fc10` | `01e61100d278854620561dd1a8b3d2a1d1b91999c83a6d6e0ffb60cdf9cb7d95` |
| 1 | 2301952 | `7db11fb38d534b993d80d10f5b9b7d64` | `d52ffd7e030898cb87a83db8ca572bd14b23e84a0c7e957edf5806499c975a14` |

- Each donut TEE is numbered here, so a number in the table above is always
  donut's own. TEE 3 is smaller than TEE 2 and newer. TEE 4 is the size of
  TEE 2 and older: it ships in 4655 to 5531, from 2023 and 2024.

### Partition hashes

[donut-partitions.csv](../firebreak/devices/donut-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for every build above,
read as biscuit's are.

- donut's payload names `tee1` and `tee2` as two partitions and writes the
  same TEE image to both, in all 26 builds. biscuit, radar, crown, sonar,
  checkers and cronos each name one `tee` and have 5 rows a build, so donut
  has 6. The other sixteen devices here name two, and their row counts are in
  the list above. The Builds table above keeps one TEE column because the two
  images are equal.
- Every donut OTA is an A/B payload OTA, 1895 included. So every hash is the
  one in its `payload.bin` manifest, and none carries the erased-block caveat
  the block OTAs of the six devices here that ship them do: a donut that
  Amazon's updater installed matches these `/system` hashes whatever its eMMC
  returns for an erased block.
- `/system` is 1073741824 bytes in every build. Every build has its own boot
  and `/system` hash.
- Nothing here has looked inside a donut `/system`. `boot-root.zip` does root
  a donut in place, as it does a biscuit and a radar, read on three runs to
  8349, and the step after it needs a power cycle on two of the three.

### eMMC chips

No donut has been seen here, so nothing is read: no chip, no capacity and no
wear. Running `report` once on one would fill this in, as it did for radar.

- kamakiri-donut v1.0.0 carries a `gpt-donut.bin` of its own, whose table has
  16 partitions and a last usable sector of 7634910, which is the last usable
  sector of radar's `FJ25AB` Echo, on an eMMC of 7634944 sectors. It is the
  kit's table rather than one read off a donut, so it says
  what the kit would write and not what a donut carries.

## crumpet

The Echo Dot (3rd Generation) Refresh of 2019, model `AEOCP`. Read on
2026-11-23 from all 18 OTAs ftvdb lists: Fire OS 6 3252, 4307, 4660, 4955,
6009, 6071, 6077, 6086, 6176, 6193, 6199, 6208, 6562, 6813, 8149, 8338, 8344
and 8349. ftvdb has no other crumpet OTA, and none is Fire OS 5. Its build
numbers are its own, and they do not follow release order: 6813 is Fire OS
6.5.6.6, where 6562 is 6.5.7.3. No kit here unlocks it, and no route reaches
it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6176 to 8349, except 6813 | `6f7225e-20230407_002912` | `20231103_072325` | [4](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 6009 to 6086, and 6813 | `6f7225e-20230407_002912` | `20231103_072325` | [3](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 4955 | `6f7225e-20230407_002912` | `20230726_065225` | [2](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 4660 | `0db8914-20221005_064411` | `20220323_062523` | [2](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 4307 | `24eb7bc-20220827_065252` | `20220323_062523` | [2](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 3252 | `8f885ae-20210414_064357` | `20210326_040236` | [1](#tee-images-4) | `<not found>`, 0x0001, 0x0001 |

- The table has no fastbrick column, as donut's has none: no kit here ships a
  crumpet image.
- crumpet names no `preloader` partition. It names four, `brhgptpl_0` to
  `brhgptpl_3`, of 184320 bytes each, and each holds the whole boot0 area: a
  BRLYT header, then boot0's GPT, then the preloader at 0x8000, of 151552
  bytes. `pl_build_desc` and the PL version are read from that preloader, as
  the other devices' are read from their `preloader` partition.
- The four are one image written four times. They differ in 4 bytes, at
  0x100d, 0x1011, 0x101d and 0x1021, which hold 0 and 1, 4 and 5, 8 and 9, and
  12 and 13: the block each copy is written to. The GPT names them at LBA 0,
  1024, 2048 and 3072. So a hash of `brhgptpl_1` never equals a hash of
  `brhgptpl_0`, and comparing one against the other's is a false difference.
- Four preloaders ship across the 18, each 151552 bytes: 3252's, 4307's, which
  4660 shares, 4955's, and one in every build from 6009. None carries a
  commit, so `pl_build_desc` is a build timestamp alone, as donut's is. Where
  biscuit's and radar's preloaders of one row differ only in boot0's GPT,
  crumpet's four are four builds.
- The PL version is not read. The `[ANTI-ROLLBACK] Updating PL version`
  string that biscuit's, radar's and crown's PL versions are found through, in
  [Anti-rollback](#anti-rollback), is in no crumpet preloader, so the column
  says `<not found>` rather than a number. The TEE and LK versions are read as
  biscuit's are, and both are 0x0001 in every build, as donut's are. No OTA
  raises one.
- Four LKs ship: 3252's, 4307's, 4660's, and one in every build from 4955,
  which is fifteen of the eighteen. 3252's is 233472 bytes and the other
  three are 237568.
- crumpet's LK of 4955 and later and donut's of 4769 and later are built from
  one commit, `6f7225e`, 69 minutes apart. The images differ. Their preloaders
  pair up the same way: crumpet's `20230726_065225` against donut's
  `20230726_074325`, and crumpet's `20231103_072325` against donut's
  `20231103_081354`.
- No crumpet image is shared with any device here.
  [doebrite](#doebrite), [pascal](#pascal) and [croissant](#croissant) are
  built as crumpet is, down to one BRLYT header and one 18-partition GPT table
  across the four, and none shares a signed image with it.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 4 | 2363392 | `5c15c876381d399683555f04451be064` | `fa0ec8b8310f806ac99507848fa0ea3b0eb1574f96bb638f2464e6ff187a2ed6` |
| 3 | 2367488 | `dca5344caf741699adfe6da3a434a4ad` | `8b0dfbc020ec108d1e3eab043c95198994cd01c1f25b04d4ec8716bd4dcde85d` |
| 2 | 2367488 | `ace011b7e719b152e802429967231ccc` | `a1500f362bec395a8a95eadfcf6e22e85d92e589ecf11cb06abd231ef77476ac` |
| 1 | 2367488 | `485f3ba638fcb337c19f437aef5f01e8` | `68f9cbefa012b7aa955098c024cbb2ef8f0dee83a5e635d7e1d66a4c0439bff6` |

- Each crumpet TEE is numbered here, so a number in the table above is always
  crumpet's own. TEE 4 is the smallest and the newest, as donut's TEE 3 is.
  Every OTA writes its TEE to both `tee1` and `tee2`, and the two are equal in
  all 18 builds.

### Partition hashes

[crumpet-partitions.csv](../firebreak/devices/crumpet-partitions.csv)
has the sha256 of the 9 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every crumpet OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat the block
  OTAs do, as donut's do not.
- `/system` is 136626176 bytes in every build, the size doebrite, pascal and
  croissant ship. Every build has its own boot and `/system` hash.
- Every build has its own `brhgptpl` hashes, all four of them, because boot0's
  GPT carries a fresh disk GUID and 18 fresh partition GUIDs each time. The
  preloader inside is one of four images, so a changed `brhgptpl` hash is not
  a changed preloader.
- The GPT's own table is the same in all 18 builds: 18 partitions, with the
  same names, start and end LBAs and attributes, and the same type GUIDs. No
  crumpet OTA moves a partition. The table holds `lk_a`, `lk_b`, `boot_a` and
  `boot_b`, and no `system`, though the payload writes one.
- Nothing here has looked inside a crumpet, and no crumpet has been seen here.

## doebrite

The Echo Dot with Clock (3rd Generation) of 2019, model `AEODB`. Read on
2026-11-23 from all 5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and
8349. ftvdb has no other doebrite OTA, and none is Fire OS 5. No kit here
unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6562 to 8349 | `6f7225e-20230406_233331` | `20231103_063546` | [1](#tee-images-5) | `<not found>`, 0x0001, 0x0001 |

- One row covers all 5 builds. One LK, one preloader and one TEE ship across
  them, so only `boot`, `/system` and boot0's GPT change from build to build.
  Whether that is the device's whole history or only what ftvdb lists is not
  known. ftvdb recorded all 5 in 2026, where its crumpet records reach back to
  2021, and doebrite's five build numbers are exactly crumpet's five newest. So
  the catalog holds no doebrite OTA older than 6562, and what shipped on one
  before that is unread. Those are record dates, not build dates.
- doebrite is built as crumpet is, and read the same way: no `preloader`
  partition, four `brhgptpl` copies of 184320 bytes, the preloader at 0x8000,
  the same 4 bytes separating the copies, and the PL version not read.
  [crumpet](#crumpet) says what each part of that image is.
- **doebrite's BRLYT header and boot0's GPT table are crumpet's and
  pascal's, exactly.** The header is one sha256 across all three devices' 32
  OTAs, and the GPT holds the same 18 partitions, with the same names, start
  and end LBAs, attributes and type GUIDs. Only the disk and partition GUIDs
  differ, which are fresh in every build of any of them.
- Every signed image differs. No doebrite image is shared with any device
  here, in any build.
- doebrite's LK opens the `6f7225e` batch, the eleven LKs built from one
  commit in one sitting. [The 6f7225e batch](#the-6f7225e-batch) has them all.
- `/system` is 136626176 bytes in every build, as crumpet's is. `boot` is
  9912320 bytes in 6562 and 8149, and 9916416 in 8338 and later.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2363392 | `39ea6ae863482014706786ad7477451a` | `f68b5f3d1e20ef373f25544c01ed003bf36f215b5e1d2aff54987e8c26029bae` |

- Every OTA writes this TEE to both `tee1` and `tee2`, and the two are equal in
  all 5 builds. It is the size of crumpet's TEE 4 and a different image.

### Partition hashes

[doebrite-partitions.csv](../firebreak/devices/doebrite-partitions.csv)
has the sha256 of the 9 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every doebrite OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat the block
  OTAs do.
- The 5 builds hold 32 distinct images between them: one LK and one TEE, and a
  boot, a `/system` and four `brhgptpl` of their own each. The preloader is not
  a row of its own: it is inside each `brhgptpl` already counted.
- Nothing here has looked inside a doebrite, and none has been seen here.

## pascal

The Echo (3rd Generation) of 2019, model `AEOPC`. Read on 2026-11-23 from all
9 OTAs ftvdb lists: Fire OS 6 2784, 3376, 5291, 6451, 6562, 8149, 8338, 8344
and 8349. ftvdb has no other pascal OTA, and none is Fire OS 5. No kit here
unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6451 to 8349 | `6f7225e-20230407_015438` | `20231103_083025` | [4](#tee-images-6) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 5291 | `6f7225e-20230407_015438` | `20231103_083025` | [3](#tee-images-6) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 3376 | `8f885ae-20210414_073038` | `20210326_053500` | [2](#tee-images-6) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 2784 | `929e557-20190821_070043` | `20190821_070043` | [1](#tee-images-6) | `<not found>`, 0x0001, 0x0001 |

- pascal is built as crumpet is, and read the same way: no `preloader`
  partition, four `brhgptpl` copies of 184320 bytes, the preloader at 0x8000,
  and the PL version not read. [crumpet](#crumpet) says what each part of that
  image is.
- **pascal's BRLYT header and boot0's GPT table are crumpet's and doebrite's,
  exactly.** One sha256 for the header and one 18-partition table across all
  three devices, down to the type GUIDs. So the Echo (3rd Generation), the Echo
  Dot (3rd Generation) Refresh and the Echo Dot with Clock (3rd Generation)
  share one flash map and no signed image.
- Three LKs and three preloaders ship across the 9 builds, and they change
  together: 2784's, 3376's, and one in every build from 5291, which is seven of
  the nine.
- 2784's and 3376's LKs are 233472 bytes and the one from 5291 is 237568.
  2784's preloader and its LK carry one timestamp between them,
  `20190821_070043`, as donut's 1895 do.
- `/system` is 136626176 bytes in every build, the size crumpet's and
  doebrite's are. Every build has its own boot and `/system` hash, and `boot`
  takes five sizes across the nine.
- No pascal image is shared with any device here.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 4 | 2363392 | `e04ab413422696514d563bc917bd41a7` | `d71b7a3ea4173735f19bbf1a60de2687144fee86acd998a6be8e527426224cc6` |
| 3 | 2367488 | `cbd18aca908cf0b091869a511c3a9eb1` | `b31017d84104d0e49012b759429c5dc4466314d9c801da9328af37965bb99c67` |
| 2 | 2367488 | `cc5787edea44790d2ddec3c79bcf06b6` | `1049be52bb609b2357f4927db5ba0e806b4ee2a32a734df54f576dd9f26c0957` |
| 1 | 2367488 | `de084eb7df469d08e23c9a2dc3bb93c1` | `70bcdf6f5a5ed94a51245be3a2ffd3e5eed848d65a466da5f069ad4bf2160e6d` |

- Each pascal TEE is numbered here, so a number in the table above is always
  pascal's own. Every OTA writes its TEE to both `tee1` and `tee2`, and the two
  are equal in all 9 builds.

### Partition hashes

[pascal-partitions.csv](../firebreak/devices/pascal-partitions.csv)
has the sha256 of the 9 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every pascal OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat the block
  OTAs do.
- Every build has its own `brhgptpl` hashes, all four of them, because boot0's
  GPT carries a fresh disk GUID and 18 fresh partition GUIDs each time, as on
  crumpet and doebrite. A changed `brhgptpl` hash is not a changed preloader.
- Nothing here has looked inside a pascal, and none has been seen here.

## sonar

The Echo Plus (1st Generation) of 2017, model `AEOSN`. Read on 2026-11-23 from
both OTAs ftvdb lists, Fire OS 5.5.6.9 of August and October 2026. ftvdb has no
other sonar OTA, and neither is Fire OS 6: sonar is the only device here still
shipping Fire OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 5.5.6.9, 5.5.6.9-9181 | `bfc30ee-20220824_171617` | `76efe0c-20221121_173834` | [1](#tee-images-7) | 0x0005, 0x0102, 0x0001 |

- Both builds ship one LK and one TEE. Their preloaders differ in 87 bytes, all
  of them in boot0's GPT at the end of the image, so the preloader code is one
  build: `76efe0c-20221121_173834`. This is biscuit's and radar's pattern, not
  crumpet's.
- sonar's anti-rollback versions are biscuit's and radar's too, 0x0005, 0x0102
  and 0x0001. crown carries that same TEE version at a PL version of 1, and
  donut, crumpet, doebrite, pascal and lidar carry 0x0001 for the TEE. Each is
  read as biscuit's are, in [Anti-rollback](#anti-rollback).
- ftvdb lists two builds of Fire OS 5.5.6.9, 690918020 and 690918120. Their
  `ro.build.lab126.build` are 9180 and 9181, so the CSV names the second
  `Fire OS 5.5.6.9-9181`, as biscuit's two 5.5.0.3 builds are named.
- No sonar image is shared with any device here.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2641920 | `5bee3491efcacedc862567311ebbc3f0` | `b42d0726058471c9d1dc8e0cac09270709264de004cb7585115435ce92e68eaa` |

### Partition hashes

[sonar-partitions.csv](../firebreak/devices/sonar-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for both builds above,
read as biscuit's are.

- Both sonar OTAs are block OTAs, as biscuit's, radar's, crown's, checkers'
  and cronos' are. So a sonar that Amazon's updater installed matches its
  `/system` hash only if its flash reads erased blocks as zeros, as on
  biscuit.
- `/system` is 1073676288 bytes in both builds, and `boot` 7534592. Each build
  has its own boot, `/system` and preloader hash.
- sonar names one `tee`, so it has 5 rows a build.
- Nothing here has looked inside a sonar, and none has been seen here.

## lidar

The Echo Plus (2nd Generation) of 2018, model `AEOLR`. Read on 2026-11-23 from
both OTAs ftvdb lists: Fire OS 6 8149 and 8338. ftvdb has no other lidar OTA,
and neither is Fire OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 8149 and 8338 | `6f7225e-20230407_030004` | `20231103_093456` | [1](#tee-images-8) | 0x0001, 0x0001, 0x0001 |

- lidar names a `preloader` partition, as biscuit, radar, crown, donut and
  sonar do, and `tee1` and `tee2`, as donut does. So it has 6 rows a build and
  needs none of crumpet's boot0 reading.
- Its preloader is 151552 bytes, the size crumpet's and doebrite's are and the
  size donut's four later ones are, and carries no commit, so `pl_build_desc`
  is the `Build Time` string alone, as every donut row's is.
- **Its PL version reads 0x0001.** crumpet's, doebrite's, pascal's,
  croissant's and cronos' cannot be read at all, because the string their
  versions would be found through is absent; lidar's is there, so the row
  carries a number where theirs carry `<not found>`.
- Both builds ship one LK, one preloader and one TEE, so only `boot` and
  `/system` change between them. `/system` is 1283457024 bytes in both, and
  `boot` 10350592.
- No lidar image is shared with any device here.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2248704 | `9ca9d409ea36a3a5aa31681fd522556a` | `28eec7cfb167a6fcd120b4bf76510cccbf144bcab0e80c76b2fca5f61d026d42` |

- Every OTA writes this TEE to both `tee1` and `tee2`, and the two are equal in
  both builds. At 2248704 bytes it is the size cupcake's TEE 3, octave's and
  pablo's take.

### Partition hashes

[lidar-partitions.csv](../firebreak/devices/lidar-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for both builds above,
read as biscuit's are.

- Both lidar OTAs are A/B payload OTAs, so every hash is the one in its
  `payload.bin` manifest, and neither carries the erased-block caveat.
- Nothing here has looked inside a lidar, and none has been seen here.

## The u-boot devices

laser, brownie, ganache, cannoli, cheesecake and churro ship no `preloader`
partition and no build description of the kind the sections above read. They
wrap `uboot`, the TEE and, on cannoli, cheesecake and churro, `scp` and
`mcupm` in FIT images, each of which carries a `timestamp` property rather
than a `commit-timestamp` string. `survey` reports the timestamp on each FIT image's
root node, as a `uboot_build_time` line and the rest, and those are the columns
their Builds tables carry.

- cannoli's, cheesecake's and churro's FIT images are signed, and a signature
  node carries a `timestamp` of its own: the signing time, 3 seconds to 18
  hours after the build in the images read here. Only the root node's is read,
  so a column here is always a build time.
- **They have no anti-rollback line.** The `[ANTI-ROLLBACK] Updating PL
  version` string the PL version is read through is in none of these images,
  and neither is an LK version trailer. `survey` does find `EET KTM` inside the
  TEE's FIT and would read a version from it, but the values that come back are
  not the 0x0001 to 0x0104 every other device here reports, so the header is
  being matched inside wrapped data and no TEE version is published for these
  six.
- The LK is not a partition of its own except on laser, where `lk` holds an
  `EMMC_BOOT` image. On the other five, boot0 wraps it: four `brhgptlk` copies,
  byte-identical to each other in every build, holding their GPT at 0x800.
  brownie's and ganache's open `BOOTLOADER!`, as crumpet's `brhgptpl` does, and
  cannoli's, cheesecake's and churro's open `NANDCFG!`.
- `reserve_0` to `reserve_2`, on the five with `brhgptlk`, are 4096 bytes of
  zeros. One hash covers every one of them, on every build of every device, so
  it is the only image two devices here share besides biscuit's and radar's
  TEE.
- **Six u-boots were built on one day**, 2024-07-25, between 07:01 and 09:27:
  brownie's, cannoli's, churro's, laser's, cheesecake's and ganache's, in that
  order. laser's, brownie's and ganache's TEEs are one batch too, on
  2025-08-14 between 06:58 and 08:11, and the TEE cannoli ships in 6562 and
  7577, churro's and cheesecake's are another, on 2024-03-08 between 08:01 and
  08:40. cannoli is the only one of the six whose `uboot` changes across its
  builds.

## laser

The Echo (4th Generation) of 2020, model `AEOLS`. Read on 2026-11-23 from all
5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and 8349. ftvdb has no
other laser OTA, and none is Fire OS 5. No kit here unlocks it, and no route
reaches it. Its OTAs name themselves `laser_mt8512`, so the SoC is an MT8512.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` |
| --- | --- | --- |
| Fire OS 6 6562 to 8349 | `20240725_084626` | `20250814_073131` |

- laser is the first device here with a `uboot` partition, and it is read as
  the [u-boot devices](#the-u-boot-devices) are.
- It names no `preloader` and no boot0 copies. Its `lk` partition holds an
  `EMMC_BOOT` image of 192512 bytes, which carries no build description and no
  LK version trailer, so nothing above describes it. Its hash in the CSV is all
  that identifies it.
- One LK, one `uboot` and one TEE ship across all 5 builds, so only `boot` and
  `/system` change. `/system` is 1048576000 bytes in every build, and `boot`
  takes two sizes.
- 13 distinct images cover the 5 builds.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 512000 | `782fc3d36d1a5bd8dbf0698b3a4591b6` | `0b065a5defc2e14c71711cdfd7d9dfcf461c2de5d2c11e1710f64c0141907cd9` |

### Partition hashes

[laser-partitions.csv](../firebreak/devices/laser-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every laser OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat the block
  OTAs do.
- Nothing here has looked inside a laser, and none has been seen here.

## brownie

The Echo Dot (4th Generation) of 2020, model `AEOBN`. Read on 2026-11-23 from
all 5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and 8349. ftvdb has no
other brownie OTA, and none is Fire OS 5. No kit here unlocks it, and no route
reaches it. Its OTAs name themselves `brownie_mt8512_nand`, so the SoC is an
MT8512 and the flash is NAND.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` |
| --- | --- | --- |
| Fire OS 6 6562 to 8349 | `20240725_070147` | `20250814_065849` |

- brownie is read as the [u-boot devices](#the-u-boot-devices) are. It names
  four `brhgptlk` copies of 237568 bytes, a `uboot`, and no `preloader` and no
  `lk`: boot0 wraps the LK here, where crumpet's `brhgptpl` wraps the
  preloader. The image opens `BOOTLOADER!` as crumpet's does, and holds its GPT
  at 0x800 rather than 0x3000.
- **The four copies are byte-identical in every build**, where crumpet's differ
  in the 4 bytes that hold the destination block. So one hash covers all four.
- One `uboot` and one TEE ship across all 5 builds, and one set of `brhgptlk`
  copies, so only `boot` and `/system` change. `/system` is 124944384 bytes in
  every build.
- `reserve_0`, `reserve_1` and `reserve_2` are 4096 bytes of zeros, one hash
  across every build of every device here that names them. They are padding,
  not data.
- 14 distinct images cover the 5 builds.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 512000 | `6ac7acd850c75572309cb141ad68e0c5` | `4c02dc7230510933b346df2dda972fc9eb36739aa76cc315aeefdea743cf31f1` |

### Partition hashes

[brownie-partitions.csv](../firebreak/devices/brownie-partitions.csv)
has the sha256 of the 12 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every brownie OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a brownie, and none has been seen here.

## ganache

The Echo Dot with Clock (4th Generation) of 2020, model `AEOGN`. Read on
2026-11-23 from all 5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and
8349. ftvdb has no other ganache OTA, and none is Fire OS 5. No kit here
unlocks it, and no route reaches it. Its OTAs name themselves
`ganache_mt8512_nand`, as brownie's do.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` |
| --- | --- | --- |
| Fire OS 6 6562 to 8349 | `20240725_092739` | `20250814_081115` |

- ganache is brownie's clock variant and is built the same way: four
  `brhgptlk` copies of 237568 bytes, byte-identical to each other, a `uboot`,
  three zeroed `reserve` partitions, and no `preloader` and no `lk`. It is read
  as the [u-boot devices](#the-u-boot-devices) are.
- **Its images are not brownie's.** Every signed image differs, though every
  partition but `boot` is the size brownie's is, `/system` included at
  124944384 bytes. ganache's `boot` is the smaller of the two. The pairing is
  doebrite's and crumpet's again, one generation on.
- One `uboot` and one TEE ship across all 5 builds, so only `boot` and
  `/system` change. 14 distinct images cover the 5 builds.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 512000 | `4dd0d1c2934f5c58d90afcec1428f845` | `b35ebce3e721c2e2ef37d3429291f1b8098a6f36186b483de4c958947da9cb5b` |

### Partition hashes

[ganache-partitions.csv](../firebreak/devices/ganache-partitions.csv)
has the sha256 of the 12 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every ganache OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a ganache, and none has been seen here.

## cannoli

The Echo Dot (5th Generation) of 2022, model `AEOCA`. Read on 2026-11-23 from
all 7 OTAs ftvdb lists: Fire OS 6 4936, 6562, 7577, 8149, 8338, 8344 and 8349.
ftvdb has no other cannoli OTA, and none is Fire OS 5. No kit here unlocks it,
and no route reaches it.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` | `scp_build_time` | `mcupm_build_time` |
| --- | --- | --- | --- | --- |
| Fire OS 6 8149 to 8349 | `20260407_032735` | `20260407_032753` | `20250924_152946` | `20220314_214943` |
| Fire OS 6 7577 | `20260529_044925` | `20240308_080103` | `20250924_152946` | `20220314_214943` |
| Fire OS 6 6562 | `20240725_072359` | `20240308_080103` | `20250924_152946` | `20220314_214943` |
| Fire OS 6 4936 | `20230921_191115` | `20230810_072707` | `20230818_152703` | `20220314_214943` |

- cannoli is the first device here with `scp` and `mcupm` partitions, both FIT
  images like `uboot` and the TEE. It is read as the
  [u-boot devices](#the-u-boot-devices) are.
- Its boot0 copies open `NANDCFG!`, not `BOOTLOADER!` as brownie's and
  crumpet's do, and the four are byte-identical in every build. They take two
  sizes: 245760 in 4936 and 6562, and 249856 from 7577.
- **7577's `uboot` is newer than 8149's and later**, `20260529_044925` against
  `20260407_032735`, though 7577 is the lower build number and the older Fire
  OS version. So a build number does not order the bootloaders.
- `mcupm` is one image in all 7 builds, from 2022. `scp` is two: 4936's and one
  in every build from 6562.
- 4 `uboot` images, 3 TEEs and 4 sets of `brhgptlk` copies cover the 7 builds,
  29 distinct images in all. `/system` is 131088384 bytes in every build.
- `reserve_0` to `reserve_2` are 4096 bytes of zeros, as brownie's are.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 3 | 647168 | `ea466f7bd6d9b2c73260d5d01c659384` | `b3be918bb0e3dd74e5e7b436809bfd83b9667e9ce58c0081e29aa8d78e7199d6` |
| 2 | 647168 | `8cec63a6dc474030ccb0d19a321d8059` | `6cc5adc7c4afee908de2cfd5bfb4c0496aad264c5d85f8435ea5eaa56f937d39` |
| 1 | 634880 | `1c8fd123f7e823474178ae5eb9fb708a` | `fa265dce25b50661da6d2af86fbcfe33b27933ea45cba4632221b7d35cbd10e6` |

- Each cannoli TEE is numbered here, so a number is always cannoli's own. TEE 1
  ships in 4936, TEE 2 in 6562 and 7577, and TEE 3 from 8149. Every OTA writes
  its TEE to both `tee1` and `tee2`, and the two are equal in all 7 builds.

### Partition hashes

[cannoli-partitions.csv](../firebreak/devices/cannoli-partitions.csv)
has the sha256 of the 14 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every cannoli OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a cannoli, and none has been seen here.

## cheesecake

The Echo Dot with Clock (5th Generation) of 2022, model `AEOCZ`. Read on
2026-11-23 from all 5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and
8349. ftvdb has no other cheesecake OTA, and none is Fire OS 5. No kit here
unlocks it, and no route reaches it.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` | `scp_build_time` | `mcupm_build_time` |
| --- | --- | --- | --- | --- |
| Fire OS 6 6562 to 8349 | `20240725_090705` | `20240308_084051` | `20250924_152946` | `20220314_215607` |

- cheesecake is cannoli's clock variant and carries the same partitions,
  `scp` and `mcupm` included, with boot0 copies that open `NANDCFG!` and are
  byte-identical to each other. It is read as the
  [u-boot devices](#the-u-boot-devices) are.
- **Its images are not cannoli's**, and the build stamps sit beside cannoli's:
  its `scp` carries cannoli's stamp to the second, 2025-09-24 15:29:46, though
  the image is not cannoli's, and its `mcupm` is stamped 6 minutes 24 seconds
  after cannoli's. ganache pairs with brownie the same way.
- One of everything but `boot` and `/system` ships across all 5 builds, so 16
  distinct images cover them. `/system` is 131088384 bytes in every build, and
  `boot` takes three sizes.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 647168 | `eec080091894dafc600bba39b1803345` | `bbf5c171464eed2f8ed2639f4c562a3c6bf9151a70bf4cc83240baddb7e114a5` |

### Partition hashes

[cheesecake-partitions.csv](../firebreak/devices/cheesecake-partitions.csv)
has the sha256 of the 14 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every cheesecake OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a cheesecake, and none has been seen here.

## churro

The Echo Pop (1st Generation) of 2023, model `AEOCO`. Read on 2026-11-23 from
all 5 OTAs ftvdb lists: Fire OS 6 6562, 8149, 8338, 8344 and 8349. ftvdb has no
other churro OTA, and none is Fire OS 5. No kit here unlocks it, and no route
reaches it.

### Builds

| ships in | `uboot_build_time` | `tee_build_time` | `scp_build_time` | `mcupm_build_time` |
| --- | --- | --- | --- | --- |
| Fire OS 6 6562 to 8349 | `20240725_082159` | `20240308_082058` | `20250924_152946` | `20220814_214919` |

- churro carries cannoli's partitions, `scp` and `mcupm` included, with four
  `brhgptlk` copies that open `NANDCFG!`, are byte-identical to each other and
  hold their GPT at 0x800. It is read as the
  [u-boot devices](#the-u-boot-devices) are.
- **Its images are its own.** No image here is cannoli's or cheesecake's,
  though its `brhgptlk` copies are 249856 bytes, the size cannoli's take from
  7577 on, where cheesecake's are 245760.
- **Three devices stamp one second.** Its `scp` carries 2025-09-24 15:29:46,
  the stamp cannoli's and cheesecake's carry, and the three images differ. Its
  `mcupm` is its own, from 2022-08-14, five months after theirs.
- One of everything but `boot` and `/system` ships across all 5 builds, so 16
  distinct images cover them. `/system` is 131088384 bytes in every build, and
  `boot` takes two sizes.
- `reserve_0` to `reserve_2` are 4096 bytes of zeros, as brownie's are.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 647168 | `30e3eaa01407932ccb924123e1de321a` | `064d2aa419f807e3b242e97be63cdd76fb0beeca4f104aa9c19db8e6777047f4` |

### Partition hashes

[churro-partitions.csv](../firebreak/devices/churro-partitions.csv)
has the sha256 of the 14 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every churro OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a churro, and none has been seen here.

## checkers

The Echo Show 5 (1st Generation) of 2019, model `AEOCH`. Read on 2026-11-23
from all 23 OTAs ftvdb lists: Fire OS 6 2264, 6086, 6190, 6200, 6206, 6208,
6225, 6436, 6451, 6558, 6567, 7575, 7577, 7595, 7630, 7632, 7636, 8146, 8149,
8150, 8151, 8848 and 8851. ftvdb has no other checkers OTA, and none is Fire
OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 8848 | `fbacd25-20260415_104418` | `8d92e82-20260415_104418` | [3](#tee-images-15) | 0x0001, 0x0103, 0x0001 |
| Fire OS 6 6086 to 8851, except 8848 | `44072a3-20240709_170103` | `79a3b50-20231019_082513` | [2](#tee-images-15) | 0x0001, 0x0103, 0x0001 |
| Fire OS 6 2264 | `cd178e6-20190703_190118` | `d14f08f-20190512_232119` | [1](#tee-images-15) | 0x0001, 0x0102, 0x0001 |

- checkers is the second screen here, after crown. Its OTAs are block
  OTAs, read exactly as biscuit's are: `boot.img`, `images/lk.bin`,
  `images/preloader.img`, `images/tz.img` and `system.new.dat`, so 5 rows a
  build.
- **8848 carries a newer bootloader than 8851.** Both are Fire OS 6575.1, and
  8848's LK and preloader are built on 2026-04-15 where 8851 ships the LK of
  2024-07-09. So a build number does not order the bootloaders, as it does not
  on cannoli.
- 8848's LK and preloader carry one timestamp, `20260415_104418`, under two
  commits, as cronos' 8848 row and biscuit's 5.5.5.4 row do. No other row here
  pairs its two that way.
- The TEE version rises from 0x0102 to 0x0103 between 2264 and 6086. The PL
  and LK versions are 0x0001 in every build.
- The preloaders of one row differ between builds only in boot0's GPT, as on
  biscuit, so each of the 23 builds has a preloader hash of its own.
- 3 LKs, 3 TEEs and 23 preloaders cover the 23 builds, 75 distinct images in
  all. `/system` is 3253731328 bytes in every build, the size crown's is.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 3 | 2516992 | `e81f25b4efb1559f0acc4b8c9d0bf533` | `53958b83cf1b924c2f60e3555ec4f4663e3545b15c16991eaa98b740b2a691c7` |
| 2 | 2533376 | `df1a7fd1936fab4b06cf73cd06089813` | `731799f3a23aca6e8660171d0ccb5f8802f0130a7a6f18d5e65b98f1560de12b` |
| 1 | 2937856 | `5ca23a1ad4ec2dcfa3764a1ca3d4463c` | `5cb056cb345495314e831aeb455c47d0ef027c956301b5f586886e1b8029098f` |

- Each checkers TEE is numbered here, so a number in the table above is always
  checkers' own. TEE 1, of 2264, is the largest TEE any device here ships.

### Partition hashes

[checkers-partitions.csv](../firebreak/devices/checkers-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every checkers OTA is a block OTA, so its `/system` hash is the image the
  OTA builds and carries the erased-block caveat biscuit's do.
- Nothing here has looked inside a checkers, and none has been seen here.

## croissant

The Echo Flex of 2019, model `AEOCR`. Read on 2026-11-23 from all 26 OTAs
ftvdb lists: Fire OS 6 3471, 4390, 4660, 5413, 5555, 6009, 6071, 6176, 6193,
6199, 6208, 6220, 6425, 6436, 6448, 6554, 6562, 7575, 7577, 7595, 8142, 8146,
8149, 8338, 8344 and 8349. ftvdb has no other croissant OTA, and none is Fire
OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6176 to 8349 | `6f7225e-20230407_010559` | `20231103_074138` | [4](#tee-images-16) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 6009, 6071 | `6f7225e-20230407_010559` | `20231103_074138` | [3](#tee-images-16) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 5413, 5555 | `6f7225e-20230407_010559` | `20231103_074138` | [2](#tee-images-16) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 4390, 4660 | `0db8914-20221005_065716` | `20220323_063735` | [2](#tee-images-16) | `<not found>`, 0x0001, 0x0001 |
| Fire OS 6 3471 | `8f885ae-20210414_065622` | `20210326_035108` | [1](#tee-images-16) | `<not found>`, 0x0001, 0x0001 |

- croissant is built as crumpet is: no `preloader` partition, four `brhgptpl`
  copies of 184320 bytes holding the preloader at 0x8000, and 9 rows a build.
  It is read as [crumpet](#crumpet) is, down to the four copies differing only
  in the block each is written to, so no hash of one copy equals another's.
- Its PL version is not read, for the reason crumpet's is not, so the column
  says `<not found>`. The TEE and LK versions are 0x0001 in every build.
- Three preloader descriptions cover the 26 builds: `20210326_035108` in 3471,
  `20220323_063735` in 4390 and 4660, and `20231103_074138` from 5413 on. None
  carries a commit, as crumpet's and donut's do not.
- Three LKs ship: 3471's of 233472 bytes, 4390's, which 4660 shares, and one
  in every build from 5413, both 237568 bytes. 23 of the 26 builds take the
  last.
- croissant's LK of 5413 and later is one of the `6f7225e` batch
  [below](#the-6f7225e-batch).
- 163 distinct images cover the 26 builds. `/system` is 136626176 bytes in
  every build, the size crumpet's is, and `boot` takes six sizes.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 4 | 2363392 | `4f014407840bb4a1b22d9b8e9c765999` | `ad5bd0f1c3a31afa6c43e3b9ed47fbc51aeceab5261e94301c68e133944c7190` |
| 3 | 2367488 | `040d03d0406b4942145e4ba31e1b12e5` | `301400a0ff9b6c46def815a2963fe7ea847957fc4486eb6fb349537888135c12` |
| 2 | 2367488 | `d65a4a552539e78fb1b12d669291747b` | `105fc61731765112e9a4d23294d6ef641a94d20240eacb83fdb624773ea0eda9` |
| 1 | 2367488 | `676ab4d44c076501e9998514d33492f1` | `ca268044743f60c1dfc5093d400d5096cb174aafdca62a90d90030c74633610e` |

- Each croissant TEE is numbered here, so a number in the table above is
  always croissant's own. TEE 4 is the smallest and the newest, as crumpet's
  TEE 4 is. Every OTA writes its TEE to both `tee1` and `tee2`, and the two
  are equal in all 26 builds.

### Partition hashes

[croissant-partitions.csv](../firebreak/devices/croissant-partitions.csv)
has the sha256 of the 9 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every croissant OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a croissant, and none has been seen here.

## cupcake

The Echo Input of 2018, model `AEOCK`. Read on 2026-11-23 from all 22 OTAs
ftvdb lists: Fire OS 6 5411, 5999, 6066, 6077, 6086, 6173, 6193, 6199, 6208,
6220, 6416, 6425, 6436, 6448, 6553, 7575, 7576, 7595, 7632, 8146, 8149 and
8338. ftvdb has no other cupcake OTA, and none is Fire OS 5. No kit here
unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6173 to 8338 | `6f7225e-20230407_012241` | `20231103_075849` | [3](#tee-images-17) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 5999 to 6086 | `6f7225e-20230407_012241` | `20231103_075849` | [2](#tee-images-17) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 5411 | `6f7225e-20230407_012241` | `20231103_075849` | [1](#tee-images-17) | 0x0001, 0x0001, 0x0001 |

- cupcake is read as [donut](#donut) is: a `preloader` partition, an `lk`, and
  one TEE written to both `tee1` and `tee2`, so 6 rows a build.
- **One LK and one preloader ship in all 22 builds**, so only `boot`,
  `/system` and the TEE ever change. Its preloader is 151552 bytes and carries
  a build timestamp with no commit, as donut's later ones do.
- Three TEEs cover the 22 builds. Only the TEE separates the three rows above:
  the bootloader row is one row for every build cupcake has.
- 49 distinct images cover the 22 builds. `/system` is 1073741824 bytes in
  every build, and `boot` takes two sizes.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 3 | 2248704 | `eae8fc9250b5371e045a2bf5eb6251c3` | `123352761da6491d167332e06718d3d6c9e68739f4c7acbc1969026bc877818b` |
| 2 | 2252800 | `4857494faa4af07b538c07fe4d7f082f` | `7b80698578684be311660626bda94f39ce7fec9d2fa1635d0555c30529b54745` |
| 1 | 2252800 | `789a4a1777be3b5c3fae634e1658a77d` | `2bc1ebfb7d9081391268992b8ba7bb14159ad81785dc389951066ff45487f86a` |

- Each cupcake TEE is numbered here, so a number in the table above is always
  cupcake's own. Every OTA writes its TEE to both `tee1` and `tee2`, and the
  two are equal in all 22 builds.

### Partition hashes

[cupcake-partitions.csv](../firebreak/devices/cupcake-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every cupcake OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a cupcake, and none has been seen here.

## octave

The Echo Studio (1st Generation) of 2019, model `AEOOT`. Read on 2026-11-23
from all 3 OTAs ftvdb lists: Fire OS 6 8149, 8338 and 8363. ftvdb has no other
octave OTA, and none is Fire OS 5. No kit here unlocks it, and no route
reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 8149 to 8363 | `6f7225e-20230407_021107` | `20231103_084705` | [1](#tee-images-18) | 0x0001, 0x0001, 0x0001 |

- octave is read as [donut](#donut) is, so 6 rows a build.
- One LK, one preloader and one TEE ship across the 3 builds, so only `boot`
  and `/system` change, and 9 distinct images cover them.
- `/system` is 1711276032 bytes in every build, the largest of any speaker
  here. `boot` is 10350592 bytes in every build and differs in content.
- 8363 ships on octave and [pablo](#pablo), and on no other device here.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2248704 | `2dff05032948c5f3dec38c6c49910733` | `c122d47990dbef978ae2ee9d1118667bcca4e0cb2d69d049c7836c3285c821ae` |

### Partition hashes

[octave-partitions.csv](../firebreak/devices/octave-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every octave OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside an octave, and none has been seen here.

## pablo

The Echo Sub of 2018, model `AEOPB`. Read on 2026-11-23 from all 3 OTAs ftvdb
lists: Fire OS 6 8149, 8338 and 8363. ftvdb has no other pablo OTA, and none
is Fire OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 8149 to 8363 | `6f7225e-20230407_022624` | `20231103_090209` | [1](#tee-images-19) | 0x0001, 0x0001, 0x0001 |

- pablo is read as [donut](#donut) is, so 6 rows a build.
- One LK, one preloader and one TEE ship across the 3 builds, so only `boot`
  and `/system` change, and 9 distinct images cover them.
- `/system` is 1073741824 bytes in every build and `boot` is 10334208, the
  sizes [sapphire](#sapphire) and [kyanite](#kyanite) carry. No image is
  shared with either.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2248704 | `8cabf9e0d117e9510ebf6e066c4b74cb` | `0a8db67ca0bb97cd0b13444a62b0050328096533d12670a251fbdce725b6d0c0` |

### Partition hashes

[pablo-partitions.csv](../firebreak/devices/pablo-partitions.csv)
has the sha256 of the 6 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every pablo OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a pablo, and none has been seen here.

## sapphire

The Echo Link of 2018, model `AEOSP`. Read on 2026-11-23 from the one OTA
ftvdb lists: Fire OS 6 5411. ftvdb has no other sapphire OTA, and none is Fire
OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 5411 | `6f7225e-20230407_000633` | `20231103_070703` | [1](#tee-images-20) | 0x0001, 0x0001, 0x0001 |

- sapphire is read as [donut](#donut) is, so 6 rows a build, and one build is
  all ftvdb has. 5 distinct images cover it.
- `/system` is 1073741824 bytes and `boot` is 10334208.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2252800 | `c3eef144f6dd123282e12f9e8b77ec98` | `97215757241aa3839b63d21f8157ddf1d78f043b8416e45fb0bc736bdc6b9381` |

### Partition hashes

[sapphire-partitions.csv](../firebreak/devices/sapphire-partitions.csv)
has the sha256 of the 6 partitions the OTA writes, read as biscuit's are.

- The sapphire OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a sapphire, and none has been seen here.

## kyanite

The Echo Link Amp of 2019, model `AEOKY`. Read on 2026-11-23 from the one OTA
ftvdb lists: Fire OS 6 5411. ftvdb has no other kyanite OTA, and none is Fire
OS 5. No kit here unlocks it, and no route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 5411 | `6f7225e-20230406_235021` | `20231103_065214` | [1](#tee-images-21) | 0x0001, 0x0001, 0x0001 |

- kyanite is sapphire's amplified variant and is read as [donut](#donut) is,
  so 6 rows a build, and one build is all ftvdb has. 5 distinct images cover
  it.
- **Every partition is the size sapphire's is**, `/system` at 1073741824 and
  `boot` at 10334208 included, and no image is shared with sapphire. The
  pairing is brownie's and ganache's, two generations earlier.
- Its LK is the second of the `6f7225e` batch [below](#the-6f7225e-batch), 16
  minutes before sapphire's.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 1 | 2252800 | `7b49b5577ee5f996b348df37b0f0400a` | `d14b3434ac5ec9817dfcdf49c59d7e2aa2b85731acebf763f10471fc9e295c23` |

### Partition hashes

[kyanite-partitions.csv](../firebreak/devices/kyanite-partitions.csv)
has the sha256 of the 6 partitions the OTA writes, read as biscuit's are.

- The kyanite OTA is an A/B payload OTA, so every hash is the one in its
  `payload.bin` manifest, and none carries the erased-block caveat.
- Nothing here has looked inside a kyanite, and none has been seen here.

## cronos

The Echo Show 5 (2nd Generation) of 2021, model `AEOCN`. Read on 2026-11-23
from all 17 OTAs ftvdb lists: Fire OS 6 5411, 6208, 6225, 6426, 6436, 6451,
6567, 7577, 7595, 7632, 7636, 8146, 8149, 8150, 8151, 8848 and 8851. ftvdb has
no other cronos OTA, and none is Fire OS 5. No kit here unlocks it, and no
route reaches it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 8848 | `fbacd25-20260415_111709` | `8d92e82-20260415_111709` | [2](#tee-images-22) | `<not found>`, 0x0104, 0x0103 |
| Fire OS 6 6208 to 8851, except 8848 | `44072a3-20240709_162755` | `79a3b50-20231019_075356` | [1](#tee-images-22) | `<not found>`, 0x0104, 0x0103 |
| Fire OS 6 5411 | `3c87b1c-20220128_013456` | `79a3b50-20231019_075356` | [1](#tee-images-22) | `<not found>`, 0x0104, 0x0103 |

- cronos is checkers' successor and ships the same block OTAs, read as
  biscuit's are, so 5 rows a build.
- **Its anti-rollback versions are the highest here.** The TEE reports 0x0104
  where no other device passes 0x0103, and the LK reports 0x0103 where every
  other device that publishes an LK version reports 0x0001. Both hold in all
  17 builds.
- Its PL version is not read: the `[ANTI-ROLLBACK] Updating PL version` string
  is in no cronos preloader, so the column says `<not found>` though the OTA
  is a block OTA and carries `images/preloader.img` whole.
- **8848 again carries the newer bootloader**, as on checkers: an LK and a
  preloader of 2026-04-15 against the 2024-07-09 LK that 8851 ships, with one
  timestamp under two commits. checkers builds its pair 32 minutes earlier
  than cronos builds its own.
- checkers, cronos and crown share the preloader commit `79a3b50` and the LK
  commit `44072a3`, and no image. All three build that LK in one sitting on
  2024-07-09: cronos at 16:27:55, crown at 16:44:49, checkers at 17:01:03.
  checkers and cronos also share `fbacd25`.
- 3 LKs, 2 TEEs and 17 preloaders cover the 17 builds, 56 distinct images in
  all. `/system` is 3253731328 bytes in every build, the size crown's and
  checkers' are, and `boot` takes two sizes.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 2 | 2533376 | `d2d8a8cfc9a6df9cb85dfe8ec0a8ca02` | `fae5e34f31f2193284e6b939a9b8ef8ba930f580a751d4122586de202b1154d6` |
| 1 | 2533376 | `34aa34b163bf7e16b971b73ad74897dc` | `948da48fe99de97542840760e8008c024b8a1a5a2f20b7311ad97b5f80694ed4` |

- Each cronos TEE is numbered here, so a number in the table above is always
  cronos' own. The two are the same size, and that size is checkers' TEE 2.

### Partition hashes

[cronos-partitions.csv](../firebreak/devices/cronos-partitions.csv)
has the sha256 of the 5 partitions each OTA writes, for every build above,
read as biscuit's are.

- Every cronos OTA is a block OTA, so its `/system` hash is the image the OTA
  builds and carries the erased-block caveat biscuit's do.
- Nothing here has looked inside a cronos, and none has been seen here.

## The 6f7225e batch

Eleven LKs here carry commit `6f7225e`, built one after another over 3 hours
26 minutes on 2023-04-06 and 2023-04-07:

| built | device |
| --- | --- |
| `20230406_233331` | [doebrite](#doebrite) |
| `20230406_235021` | [kyanite](#kyanite) |
| `20230407_000633` | [sapphire](#sapphire) |
| `20230407_002912` | [crumpet](#crumpet) |
| `20230407_010559` | [croissant](#croissant) |
| `20230407_012241` | [cupcake](#cupcake) |
| `20230407_013816` | [donut](#donut) |
| `20230407_015438` | [pascal](#pascal) |
| `20230407_021107` | [octave](#octave) |
| `20230407_022624` | [pablo](#pablo) |
| `20230407_030004` | [lidar](#lidar) |

- Every one of the eleven images differs, and no two devices share an LK.
  The commit is one source tree built eleven times, once per device.
- Each of the eleven ships that LK in its newest build, and in most of its
  earlier ones: the batch is the last LK Amazon built for these devices.
- Their preloaders follow seven months later, all eleven stamped 2023-11-03
  between 06:35:46 and 09:34:56, and in the same device order as the LKs.
