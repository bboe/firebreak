# Devices

The firmware each supported device's OTAs ship.

## biscuit

The Echo Dot (2nd Generation). Read in October 2026 from 37 Fire OS 6 OTAs on
ftvdb, 4310 to 8149, and from the Fire OS 5.5.0.3, 5.5.3.1, 5.5.4.6, 5.5.4.9,
5.5.5.0 and 5.5.5.4 OTAs.

### Builds

| ships in | `lk_build_desc` | `pl_build_desc` | TEE | anti-rollback PL, TEE, LK | fastbrick image |
| --- | --- | --- | --- | --- | --- |
| Fire OS 6 4929 to 8149, except 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [5](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4405 to 4781, and 5041 | `63cb91b-20221007_072309` | `bd7ae89-20221003_215949` | [4](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 6 4310, 4313, 4315 | `41fb3ce-20221007_151724` | `919cae9-20221006_203733` | [3](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick-20221007.img` |
| Fire OS 5.5.5.4 | `beb022a-20211202_231918` | `ed021f9-20211202_231918` | [2](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.4.9, 5.5.5.0 | `a828f29-20210822_210511` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.3.1 to 5.5.4.6 | `f379dba-20170906_000423` | `531fa14-20170929_175429` | [1](#tee-images) | 0x0005, 0x0102, 0x0001 | `fastbrick.img` |
| Fire OS 5.5.0.3 | `0e1d0d9-20161018_220224` | `292ae9d-20160915_232723` | [1](#tee-images) | 0x0003, 0x0102, 0x0001 | `fastbrick.img` |

- Only the LK chooses the fastbrick image. [rooting.md](rooting.md#unlock-amonet-v200)
  says how.
- The preloaders of one row differ between builds only in boot0's GPT, whose
  partition GUIDs are random.

### TEE images

| TEE | bytes | md5 | sha256 |
| --- | --- | --- | --- |
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

- PL: a constant in the preloader's code.
- TEE: the 16 bits at offsets 0xf and 0x10 of the TEE's plaintext
  `EET KTM` header, high byte first.
- LK: the 16 bits after `LK` in the LK's signature trailer, high byte first.
- A stock 8146 Dot read `0x0005`, `0x0102` and `0x0001`.
- PL rose from 3 to 5 after 5.5.0.3. TEE and LK are the same in every OTA.

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
  `4503599628407428`. A v2 Dot on 8146 differed from 8146's `/system` in
  those files only.

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
