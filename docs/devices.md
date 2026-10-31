# Devices

The firmware each supported device's OTAs ship. radar has a `stock` target and
an unlock, both on 8149, and crown has neither yet.

`firebreak survey OTA` prints, from one OTA zip and nothing else, what its
row in a Builds table and its rows in a partition hash CSV say: the build
descriptions, the anti-rollback versions, the TEE's hashes and the 5
partition hashes. Only the fastbrick image comes from elsewhere, amonet's
`profile.sh`. It needs no Dot. Its CSV rows name the build as the CSVs do,
so each is a line of its CSV, word for word.

Every CSV row starts with the device's codename and model, so the CSVs can
be joined into one table. The model is `ro.product.model`, which every OTA of
a device gives the same. The codename is `ro.product.device` without
`_puffin`. Biscuit's and radar's Fire OS 6 OTAs add that suffix: they are
built from a second device tree, `device/amazon/biscuit_puffin`, where their
Fire OS 5 OTAs say `biscuit`. Crown shipped on Fire OS 6 and has no suffix.
So `_puffin` appears to mark a Fire OS 5 device's later move to Fire OS 6;
no OTA says so.

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

[radar-partitions.csv](radar-partitions.csv) has the sha256 of the 5
partitions each OTA writes, for every build above, read as biscuit's are.

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
