# Devices

The firmware each supported device's OTAs ship. radar has a `stock` target and
an unlock, both on 8149, and crown and donut have neither yet.

`firebreak survey OTA` prints, from one OTA zip and nothing else, what its
row in a Builds table and its rows in a partition hash CSV say: the build
descriptions, the anti-rollback versions, the TEE's hashes and the partition
hashes, 5 of them, or 6 where an OTA names two TEE partitions as donut's do.
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

The Echo Dot (2nd Generation). Read in October 2026 from 37 Fire OS 6 OTAs on
ftvdb, 4310 to 8149, and from the Fire OS 5.5.0.3, 5.5.3.1, 5.5.4.6, 5.5.4.9,
5.5.5.0 and 5.5.5.4 OTAs. 8338 and 8344 are read from the OTAs Amazon's own
CDN serves, which is where a Dot on 8338 led: ftvdb lists neither.
[unlocking.md](unlocking.md#echo-dot-2nd-generation) has the routes this
device alone takes.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 8338, 8344 | `2c3569d-20260617_045829` | `bd7ae89-20221003_215949` | [6](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20260617.img` |
| Fire OS 6 4929 to 8149, except 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [5](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4405 to 4781, and 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [4](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4310, 4313, 4315 | `41fb3ce-20221007_151724` | `919cae9-20221006_203733` | [3](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img`, v2.0.0's |
| Fire OS 5.5.5.4 | `beb022a-20211202_231918` | `ed021f9-20211202_231918` | [2](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.4.9, 5.5.5.0 | `a828f29-20210822_210511` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.3.1 to 5.5.4.6 | `f379dba-20170906_000423` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.0.3 | `0e1d0d9-20161018_220224` | `292ae9d-20160915_232723` | [1](#tee-images) | 0x0003, 0x0102, 0x0001 | `fastbrick.img` |

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

[biscuit-partitions.csv](biscuit-partitions.csv) has the sha256 of the 5
partitions each OTA writes, for every build above: boot, `/system`, lk, tee
and the preloader.

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

The Echo (2nd Generation), model XC56PY. Read in October 2026 from the 16 OTAs
on ftvdb: Fire OS 5.5.5.4 and Fire OS 6 4305, 4315, 4929, 4936, 6199, 6208,
6220, 6302, 6425, 6436, 6813, 8149, 8338, 8344 and 8349. ftvdb has no other
radar OTA.
[unlocking.md](unlocking.md#echo-2nd-generation) has what this device alone
does.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 8338 to 8349 | `2c3569d-20260617_051433` | `bd7ae89-20221003_221237` | [3](#tee-images-1) | 0x0005, 0x0102, 0x0001 | none |
| Fire OS 6 4929 to 8149 | `63cb91b-20221007_073612` | `bd7ae89-20221003_221237` | [2](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 6 4305, 4315 | `41fb3ce-20221007_153017` | `919cae9-20221006_205014` | [4](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.5.4 | `59779ca-20220524_183401` | `642551b-20211203_021230` | [1](#tee-images-1) | 0x0005, 0x0102, 0x0001 | `fastbrick-20220524.img` |

- amonet-radar v1.0.0's `profile.sh` chooses the fastbrick image by the LK,
  as biscuit's does. Only 5.5.5.4's LK gets its own image. The `63cb91b` and
  `41fb3ce` LKs get the default, `fastbrick.img`. The `2c3569d` LK of 8338 and
  later is newer than anything amonet-radar was built for, so no image unlocks
  it.
- `stock` offers 8338, 8344 and 8349 only behind `--no-way-back`. Each one's
  OTA carries `no_way_back=True`, and a run that names such a build without the
  flag is refused before anything is written.
  `unlock.newer_than_known` refuses a bootloader no older than the newest
  firebreak has a payload for, so a restore to one of those builds leaves an
  Echo that firebreak cannot unlock again. Its bootrom would still take the
  chain, because radar declares a `BOOTROM_UNLOCK`; what is missing is a way to
  get a locked one there, since no test point has been found. biscuit
  has no such gap: amonet v2.0.1 ships `fastbrick-20260617.img` for the same
  commit's LK, which is why biscuit offers 8338 and 8344 with no flag.
- The default `fastbrick.img` unlocks a radar on 4305, measured on 2026-10-29
  from stock fastboot: the fastbrick took 13 s, TWRP started 28 s later, and
  the run rooted 4305 in place in 1 min 11 s with no restart by hand. Their LK
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

[radar-partitions.csv](radar-partitions.csv) has the sha256 of the 5
partitions each OTA writes, for every build above, read as biscuit's are.

- 5.5.5.4, 4305 and 4315 are block OTAs. As on biscuit, a radar that Amazon's
  updater installed matches their `/system` only if its eMMC reads erased
  blocks as zeros.
- The three readings below need what is inside `/system`, not its hash, and
  cover only the ten OTAs read before 2026-10-28. 8338, 8344 and 8349 are in
  the tables and the csv above, but nothing here has looked inside their
  `/system`. 4315, 4936 and 8149 are unread
  too and do not need the reading: `boot-root.zip` rooted each of them in
  place on a radar on 2026-10-29, in 1 min 11 s to 1 min 13 s, which is the
  stronger test.
- The three `--no-way-back` builds never reach the zip. `BUILDS` is also what
  `fireos.installed_build` checks before `boot-root.zip` patches a build in
  place, so adding them for `stock` would have made the in-place root accept
  them as well. `no_way_back` says one thing, that installing the build cannot
  be undone, and the in-place root takes it the only way it can: a build this
  will not install without the flag is not one it patches behind your back
  either. It says to use `--factory-reset`, which installs 8149 instead.
  Separately, nothing here has looked inside those builds' `/system` or run the
  zip on one, so every build the zip does patch is either read below or rooted
  in place.
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

[crown-partitions.csv](crown-partitions.csv) has the sha256 of the 5
partitions each OTA writes, for every build above, read as biscuit's are.

- Every crown OTA is a block OTA. As on biscuit, a crown that Amazon's updater
  installed matches its `/system` hash only if its eMMC reads erased blocks as
  zeros. Amazon's updater erases and does not write 119,598 to 132,373 of the
  794,368 blocks, depending on the build.
- Every build has its own boot, `/system` and preloader hash. `/system` is
  3,253,731,328 bytes in every build.
- Crown has no slot suffix. Hash `boot`, `system`, `lk` and `tee1` by name,
  where biscuit's steps say to use the active slot.

## donut

The Echo Dot (3rd Generation) of 2018, model `AEODN`. Read in October 2026 from
the 17 OTAs on ftvdb: Fire OS 6 1895, 6009, 6071, 6077, 6086, 6176, 6193, 6199,
6208, 6220, 6425, 6813, 8138, 8149, 8338, 8344 and 8349. ftvdb has no other
donut OTA, and none is Fire OS 5. Its build numbers are its own, as crown's
are, and they do not follow release order: 6813 is Fire OS 6.5.6.6, where 6425
is 6.5.7.2.

The Echo Dot (3rd Generation) Refresh of 2019 is a different device, model
`AEOCP` and codename crumpet, and nothing here covers it.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK |
| --- | --- | --- | --- | --- |
| Fire OS 6 6176 to 8349, except 6813 | `6f7225e-20230407_013816` | `<none>` | [3](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 6009 to 6086, and 6813 | `6f7225e-20230407_013816` | `<none>` | [2](#tee-images-3) | 0x0001, 0x0001, 0x0001 |
| Fire OS 6 1895 | `0d18cf4-20181206_233555` | `<none>` | [1](#tee-images-3) | 0x0001, 0x0001, 0x0001 |

- The table has no fastbrick column. kamakiri-donut v1.0.0 ships no fastbrick
  image and no `profile.sh`, where every amonet release here ships both, so no
  LK of donut's chooses one.
- No donut preloader carries a build description, so `pl_build_desc` is
  `<none>` in every build. Two preloaders ship across the 17: 1895's, of
  147456 bytes, and one of 151552 bytes in every later build. Where biscuit's
  and radar's preloaders of one row differ in boot0's GPT, donut's later
  sixteen builds ship the same preloader byte for byte.
- Only two LKs ship: 1895's, and one in every build from 6009. Each is read as
  biscuit's are, in [Anti-rollback](#anti-rollback).
- Every version is 1. The PL version is 1 as crown's is, where biscuit's and
  radar's are 5, and the TEE version 0x0001 is below every other device here.
  No OTA raises one.
- kamakiri-donut v1.0.0 writes the LK of 6009 and later byte for byte, and the
  TEE of 6176 and later byte for byte. Its preloader is in no OTA.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
| 3 | 2363392 | `3838fb54db104f8fe9799484afdd77e2` | `07cff71c598b7665f17c769b0504c8b7ad91647414c280b10a26be4ea5761194` |
| 2 | 2367488 | `5f0569a8c128a3288f962937a0a0fc10` | `01e61100d278854620561dd1a8b3d2a1d1b91999c83a6d6e0ffb60cdf9cb7d95` |
| 1 | 2301952 | `7db11fb38d534b993d80d10f5b9b7d64` | `d52ffd7e030898cb87a83db8ca572bd14b23e84a0c7e957edf5806499c975a14` |

- Each donut TEE is numbered here, so a number in the table above is always
  donut's own. TEE 3 is smaller than TEE 2 and newer.

### Partition hashes

[donut-partitions.csv](donut-partitions.csv) has the sha256 of the 6
partitions each OTA writes, for every build above, read as biscuit's are.

- donut's payload names `tee1` and `tee2` as two partitions and writes the
  same TEE image to both, in all 17 builds. Every other device here names one
  `tee`, so donut is the only one with 6 rows a build rather than 5. The
  Builds table above keeps one TEE column because the two images are equal.
- Every donut OTA is an A/B payload OTA, 1895 included. So every hash is the
  one in its `payload.bin` manifest, and none carries the erased-block caveat
  the block OTAs of the other three devices do: a donut that Amazon's updater
  installed matches these `/system` hashes whatever its eMMC returns for an
  erased block.
- `/system` is 1073741824 bytes in every build. Every build has its own boot
  and `/system` hash.
- Nothing here has looked inside a donut `/system`, and nothing has run
  `boot-root.zip` on one. Whether it roots a donut in place, as it does a
  biscuit and a radar, is unread.

### eMMC chips

No donut has been seen here, so nothing is read: no chip, no capacity and no
wear. Running `report` once on one would fill this in, as it did for radar.

- kamakiri-donut v1.0.0 carries a `gpt-donut.bin` of its own, whose table has
  16 partitions and a last usable sector of 7634910, which is the last usable
  sector of radar's `FJ25AB` Echo, on an eMMC of 7634944 sectors. It is the
  kit's table rather than one read off a donut, so it says
  what the kit would write and not what a donut carries.
