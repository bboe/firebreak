# firebreak

firebreak unlocks an Echo Dot (2nd Generation) over USB, moves it between amonet
targets, or returns it to stock. Run it again with another target to move the
Dot. A stopped run picks up where it left off.

| target | the Dot ends with | time |
| --- | --- | --- |
| `amonet-biscuit-v1.1.0-bboe` (default) | rooted Fire OS 5.5.5.4 on amonet v1.1.0, TWRP 3.7.0_9-bboe2 | about 9 min from stock |
| `amonet-biscuit-v1.1.0` | the same, with amonet v1.1.0's TWRP 3.2.3 | about 10 s from `amonet-biscuit-v1.1.0-bboe` |
| `amonet-biscuit-v2.0.0` | rooted Fire OS 6 8146 on amonet v2.0.0; needs `boot-root.zip` from [the amonet XDA thread](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/) in `~/Downloads` | about 5 min from `amonet-biscuit-v1.1.0-bboe` |
| `stock BUILD` | stock Fire OS 6 at that build, with the Dot erased | about 3 min from `amonet-biscuit-v1.1.0-bboe` |

## Run it

It needs `adb` and `fastboot` from Android platform-tools, and
[uv](https://docs.astral.sh/uv/), which runs firebreak from this repository and
fetches a Python for it when needed.

### macOS

These commands use [Homebrew](https://brew.sh). Without it, download Google's
[platform-tools](https://developer.android.com/tools/releases/platform-tools).

```sh
brew install --cask android-platform-tools uv
uvx --from git+https://github.com/bboe/firebreak firebreak              # amonet-biscuit-v1.1.0-bboe
uvx --from git+https://github.com/bboe/firebreak firebreak stock 8146   # or 4315, 4405, 5041, 6302, 8138, 8142
```

### Linux

These commands are for Debian and Ubuntu. Run firebreak without `sudo`.

```sh
sudo apt install adb fastboot curl
curl -LsSf https://astral.sh/uv/install.sh | sh
uvx --from git+https://github.com/bboe/firebreak firebreak
```

### Windows

Run these in PowerShell. Open a new terminal after the installs.

```powershell
winget install Google.PlatformTools
winget install astral-sh.uv
uvx --from git+https://github.com/bboe/firebreak firebreak
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
- Do not set up a stock Dot in the Alexa app before you unlock it. On Wi-Fi it
  can update to a build the script does not support.
- [docs/rooting.md](docs/rooting.md) says why each step is there.

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
3. With the Dot unplugged, run
   `uvx --from git+https://github.com/bboe/firebreak firebreak --short`.
4. When the script prints "Short the Dot's test point and plug it in", hold a
   wire from that passive to the shield frame beside it, which is ground, and
   plug the Dot in. A Dot plugged in before that message can go unseen. On
   "Short … missed", unplug it and try again.
5. Take the wire off when the script prints "The short may come off now".

## Licence

firebreak uses the BSD 2-Clause licence, in [LICENSE.txt](LICENSE.txt). This
repository contains no Amazon code, and firebreak is not affiliated with,
endorsed by, or supported by Amazon.
