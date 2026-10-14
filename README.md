# firebreak

firebreak unlocks an Echo Dot (2nd Generation) over USB, moves it between amonet
targets, or returns it to stock. Run it again with another target to move the
Dot. A stopped run picks up where it left off.

| target | the Dot ends with | time |
| --- | --- | --- |
| `amonet-biscuit-v1.1.0-bboe` (default) | rooted Fire OS [5.5.5.4][fireos-5554] on amonet v1.1.0, TWRP 3.7.0_9-bboe2 | about 9 min from stock |
| `amonet-biscuit-v1.1.0` | the same, with amonet v1.1.0's TWRP 3.2.3 | about 10 s from `amonet-biscuit-v1.1.0-bboe` |
| `amonet-biscuit-v2.0.0` | rooted Fire OS 6 [8146][fireos-8146] on amonet v2.0.0; opens your browser to download `boot-root.zip` from [the amonet XDA thread](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/) | about 5 min from `amonet-biscuit-v1.1.0-bboe` |
| `stock [BUILD]` | stock Fire OS at that build, with the Dot erased: Fire OS 6 [8149][fireos-8149] when left out, or Fire OS 5 from [5.5.3.1][fireos-5531] to [5.5.5.4][fireos-5554] | about 3 min from `amonet-biscuit-v1.1.0-bboe` |

## Run it

It needs `adb` and `fastboot` from Android platform-tools, and
[uv](https://docs.astral.sh/uv/), which runs firebreak from PyPI and fetches a
Python for it when needed. Each
[release](https://github.com/bboe/firebreak/releases) also has `firebreak.pyz`,
which runs as `python3 firebreak.pyz` on Python 3.9 or later.

`uvx firebreak@latest` asks PyPI for the newest release on each run. Without a
network it fails, and `uvx firebreak` runs the copy uv already has.

### macOS

These commands use [Homebrew](https://brew.sh). Without it, download Google's
[platform-tools](https://developer.android.com/tools/releases/platform-tools).

```sh
brew install --cask android-platform-tools uv
uvx firebreak@latest              # amonet-biscuit-v1.1.0-bboe
uvx firebreak@latest stock        # 8149, or name 5.5.3.1, 5.5.4.6, 5.5.4.9, 5.5.5.0, 5.5.5.4, 4315, 4405, 5041, 6302, 8138, 8142, 8146
```

### Linux

These commands are for Debian and Ubuntu. Run firebreak without `sudo`.

```sh
sudo apt install adb fastboot curl
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx firebreak@latest
```

### Windows

Run these in PowerShell. Open a new terminal after the installs.

```powershell
winget install Google.PlatformTools
winget install astral-sh.uv
uvx firebreak@latest
```

The bootrom step also needs MediaTek's VCOM driver. It runs for `--short`, for a
Dot on amonet v2.0.0 left in fastboot, and to resume a run stopped while it
rewrote the bootloader; the script says when. The driver is "MediaTek USB Port"
3.0.1504.0 from the Microsoft Update Catalog. Install it from an administrator
PowerShell:

```powershell
cd $env:TEMP
curl.exe -o mtk.cab https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2016/07/20896845_fdc6bb5aa9a9bac99adf85d931d6c21d1130a96e.cab
mkdir mtk; expand -F:* mtk.cab mtk
pnputil /add-driver mtk\cdc-acm.inf /install
```

It has x86 and x64 builds only, so Windows on ARM cannot run the bootrom step.

## Notes

- From stock, the script asks for the fastboot gesture.
- A ring that stays solid blue at the fastboot gesture can mean a bad USB
  connection. Unplug, then try again or try another port.
- Do not set up a stock Dot in the Alexa app before you unlock it. On Wi-Fi it
  can update to a build the script does not support.
- [docs/rooting.md][rooting] says why each step is there.

## Bootloaders

From stock, only the LK decides whether firebreak can unlock a Dot.
`fastboot getvar lk_build_desc` reads it.

| `lk_build_desc` | ships in |
| --- | --- |
| `63cb91b-20221007_072309` | Fire OS 6 [4405][fireos-4405] to [8149][fireos-8149] |
| `41fb3ce-20221007_151724` | Fire OS 6 [4310][fireos-4310], [4313][fireos-4313], [4315][fireos-4315] |
| `beb022a-20211202_231918` | Fire OS [5.5.5.4][fireos-5554] |
| `a828f29-20210822_210511` | Fire OS [5.5.4.9][fireos-5549], [5.5.5.0][fireos-5550] |
| `f379dba-20170906_000423` | Fire OS [5.5.3.1][fireos-5531] to [5.5.4.6][fireos-5546] |
| `0e1d0d9-20161018_220224` | Fire OS [5.5.0.3][fireos-5503] |

- The maintainer has not unlocked a Dot on [Fire OS 5.5.0.3][fireos-5503].
- [docs/devices.md][devices] has each build's preloader, TEE and
  anti-rollback versions.

## `--short`

Use `--short` when the Dot shows no light and gives no fastboot. The run reaches
the Dot's bootrom by shorting its eMMC bus as it powers up, writes amonet
v1.1.0, and then goes on to the target. It takes any target; `--short` to
`amonet-biscuit-v2.0.0` has not been run on a Dot. On Windows it needs the [VCOM
driver](#windows).

1. Open the Dot with a Torx T8 screwdriver. Lift the shield's lid off the eMMC
   by its corners; its metal frame stays on the board.
2. Find the passive marked in [this
   photo](https://xdaforums.com/attachments/short2-jpg.6273804/), in the row
   between R60 and C52 beside the eMMC ([where that is on the
   board](https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/)). Do not
   use C52, which is a capacitor.
3. With the Dot unplugged, run `uvx firebreak@latest --short`.
4. When the script prints "Short the Dot's test point and plug it in", hold a
   wire from that passive to the shield frame beside it, which is ground, and
   plug the Dot in. A Dot plugged in before that message can go unseen. On
   "Short … missed", unplug it and try again.
5. Take the wire off when the script prints "The short may come off now".

## Reporting a problem

When a run fails, run it again with `--report`, then please stop by
`#support-device-unlocking` in the
[EchoMuse Discord](https://discord.gg/vAPHMDvREG) and paste what it prints. It
starts the Dot's recovery, prints what the Dot, its eMMC and this computer are,
and the Dot's partition table, and writes no partition. A Dot already in a
recovery stays there, and the Dot is left in its recovery afterwards.

`--report` also names the device and lists its USB devices. firebreak supports
only the Echo Dot (2nd Generation), but the report is the same on other Echo
devices, such as the Echo (2nd Generation), and helps add them.

`--write-test` then tells a failing eMMC from a failing cable. It pushes a
pattern into the Dot's RAM, then has the Dot write it over its own `cache`
partition and read it back, so nothing crosses USB. It erases `cache`, which
holds nothing the Dot needs, and leaves an empty filesystem there, or says
it could not.

## Credits

firebreak automates work that other people did first.

- [xyz](https://github.com/xyzz/amonet) wrote amonet, a MediaTek bootrom
  exploit. firebreak's bootrom and payload clients follow its protocol.
- [k4y0z](https://github.com/chaosmaster) made the first port of amonet to the
  Echo Dot (2nd Generation).
- [Rortiz2](https://github.com/R0rt1z2) continued
  [that port](https://github.com/R0rt1z2/amonet/tree/mt8163-biscuit), released
  it with TWRP, and keeps
  [the XDA thread](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/).
  The `bboe` TWRP is a fork of
  [their TWRP tree](https://github.com/R0rt1z2/twrp_device_amazon_echo-mt8163).
- AntiEngineer helped find the pins and bring up UART on a Dot.
- [topjohnwu](https://github.com/topjohnwu/Magisk) wrote Magisk, which roots
  Fire OS 5.
- [Andy Goetz](https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/)
  described how to short the eMMC bus at the passives beside R60.
- [mtkclient](https://github.com/bkerler/mtkclient), by bkerler, agrees with
  two of firebreak's bootrom addresses.
- [ftvdb](https://ftvdb.com/) keeps the Fire OS builds that the tables link to.

## Licence

firebreak uses the BSD 2-Clause licence, in [LICENSE.txt][licence]. This
repository contains no Amazon code, and firebreak is not affiliated with,
endorsed by, or supported by Amazon.

[devices]: https://github.com/bboe/firebreak/blob/main/docs/devices.md#biscuit
[fireos-4310]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/2c4db2f5fa2ddb390faf5ccf9a879b01-8087721594-fire-os-6-5-5-5-ns6555-4310-2022-11-23/
[fireos-4313]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/0c90e6241451777048da197542c82b87-8087722362-fire-os-6-5-5-5-ns6555-4313-2023-01-10/
[fireos-4315]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/03c7c4dc338a93635dda0f5e1cd4e451-8087722874-fire-os-6-5-5-5-ns6555-4315-2023-11-20/
[fireos-4405]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/570f3f6b28f94323e01e95561c87887f-8289072516-fire-os-6-5-5-6-ns6556-4405-2023-01-21/
[fireos-5503]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/6049e04dd518483ed6e5b0d72ffe9eac-564196920-fire-os-5-5-0-3-564196920-2018-09-20/
[fireos-5531]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/789c6b80b00b90a35c3016d42a7c4455-641575220-fire-os-5-5-3-1-641575220-2019-07-22/
[fireos-5546]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/547fad91b469b9d6a3a1fcdb85b43671-666694320-fire-os-5-5-4-6-666694320-2021-06-23/
[fireos-5549]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/538f9374ad45f3f1ea18948609d7446f-672720020-fire-os-5-5-4-9-672720020-2021-10-27/
[fireos-5550]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/1be9f19c0c16337c34d55390a146c990-673726720-fire-os-5-5-5-0-673726720-2021-12-14/
[fireos-5554]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/805e721e1bed461d8a81015a1f703fc1-680767620-fire-os-5-5-5-4-680767620-2022-11-18/
[fireos-8146]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/8ca06ee4ef2806c974d2944b7fadd543-13222531716-fire-os-6574-1-ns65741-8146-2026-09-17/
[fireos-8149]: https://ftvdb.com/echo/firmware/com.amazon.biscuit.android.os/a01de630f6d943dddc9b751ae74bbb52-13222532484-fire-os-6574-1-ns65741-8149-2026-09-29/
[licence]: https://github.com/bboe/firebreak/blob/main/LICENSE.txt
[rooting]: https://github.com/bboe/firebreak/blob/main/docs/rooting.md
