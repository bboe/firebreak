# firebreak

firebreak unlocks and roots an Echo Dot (2nd Generation), an Echo (2nd
Generation) or an Echo Dot (3rd Generation) over USB, or returns it to stock.
Run it again with another target to move the device. A stopped run picks up
where it left off.

> [!NOTE]
> All of this is possible because of Rortiz2's work. firebreak runs the
> unlocks they publish on XDA, one thread for each Echo:
>
> - [Echo Dot (2nd Generation), biscuit](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/)
> - [Echo (2nd Generation), radar](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-2nd-gen-2017-radar.4801290/)
> - [Echo Dot (3rd Generation), donut](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-3rd-gen-2018-donut.4801400/)
>
> To support that work:
>
> - [PayPal](https://www.paypal.com/paypalme/R0rt1z2/)
> - [Ko-fi](https://ko-fi.com/r0rt1z2)
> - [GitHub Sponsors](https://github.com/sponsors/R0rt1z2)

## Quick start

> [!CAUTION]
> Avoid connecting a stock Echo to Wi-Fi before you unlock it. Amazon can
> update the device to a build firebreak does not support.

Install firebreak's [prerequisites](#install). Then plug your Echo into your
computer, and run:

```sh
uvx firebreak@latest unlock
```

On Windows, run `uvx --managed-python firebreak@latest unlock` instead, as
[Windows](#windows) says. Follow any instructions that may appear.

## Install

firebreak needs `adb` and `fastboot` from Android platform-tools, and
[uv](https://docs.astral.sh/uv/), which runs firebreak from PyPI.

### macOS

These commands use [Homebrew](https://brew.sh). Without it, download Google's
[platform-tools](https://developer.android.com/tools/releases/platform-tools).

```sh
brew install --cask android-platform-tools
brew install uv
brew install libusb               # for an Echo Dot (3rd Generation)
```

### Linux

These commands are for Debian and Ubuntu. Run firebreak without `sudo`.

```sh
sudo apt install adb fastboot curl libusb-1.0-0
curl -LsSf https://astral.sh/uv/install.sh | sh
```

These udev rules let your own user open the Echo in each of its USB modes, so
firebreak needs no `sudo`. A run that cannot open the Echo prints the same
commands.

<!-- markdownlint-disable MD013 -->
```sh
sudo groupadd -f plugdev
sudo tee /etc/udev/rules.d/51-echo-dot.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="1949", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="4ee2", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", ATTR{idProduct}=="d001", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0bb4", ATTR{idProduct}=="0c01", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="0e8d", ATTR{idProduct}=="201c", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="0e8d", ATTRS{idProduct}=="0003", MODE="0660", GROUP="plugdev", TAG+="uaccess"
SUBSYSTEM=="tty", ATTRS{idVendor}=="1949", ATTRS{idProduct}=="2007", MODE="0660", GROUP="plugdev", TAG+="uaccess"
EOF
sudo udevadm control --reload
sudo udevadm trigger
sudo usermod -aG plugdev "$USER"
adb kill-server
```
<!-- markdownlint-enable MD013 -->

Then log in again, so your shell has the `plugdev` group.

### Windows

> [!WARNING]
> firebreak has been tested on Windows only from an administrator PowerShell,
> for both the setup and the run.

```powershell
winget install Google.PlatformTools
winget install astral-sh.uv
cd $env:TEMP
curl.exe -fo fastboot.cab https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2016/10/20940218_0ae8695c01fb84d1fdea5c9a04baf336ec5b1ba7.cab
curl.exe -fo mtk.cab https://catalog.s.download.windowsupdate.com/d/msdownload/update/driver/drvs/2016/07/20896845_fdc6bb5aa9a9bac99adf85d931d6c21d1130a96e.cab
curl.exe -fLo UsbDk.msi https://github.com/daynix/UsbDk/releases/download/v1.00-22/UsbDk_1.0.22_x64.msi
curl.exe -fLo libusb.7z https://github.com/libusb/libusb/releases/download/v1.0.30/libusb-1.0.30.7z
mkdir -Force fastboot, mtk
expand -F:* fastboot.cab fastboot
expand -F:* mtk.cab mtk
pnputil /add-driver fastboot\tplink_winusb.inf /install
pnputil /add-driver mtk\cdc-acm.inf /install
$d = "$env:LOCALAPPDATA\Programs\libusb"
mkdir -Force $d
tar -xf libusb.7z -C $d VS2022/MS64/dll/libusb-1.0.dll
Remove-Item -Recurse fastboot.cab, mtk.cab, fastboot, mtk
[Environment]::SetEnvironmentVariable("Path", [Environment]::GetEnvironmentVariable("Path", "User") + ";$d\VS2022\MS64\dll", "User")
Start-Process msiexec -Wait -ArgumentList "/i $env:TEMP\UsbDk.msi /qn"
Remove-Item UsbDk.msi
```

Then open a new administrator PowerShell, so it has the new PATH, and run
firebreak:

```powershell
uvx --managed-python firebreak@latest unlock
```

> [!TIP]
> `--managed-python` makes uv use its own Python. firebreak stops on a Python
> from the Microsoft Store, because adb and fastboot cannot see the files it
> keeps.

Windows on ARM, Windows 11 25H2 and Windows older than 11 23H2 have limits:
see [Windows][troubleshooting-windows] in the troubleshooting guide.

## Usage

`uvx firebreak@latest --help` prints this:

```text
usage: firebreak [-h] [--credits] [--no-update-check] [--verbose] [--version]
                 COMMAND ...

Change the firmware on an Echo Dot (2nd Generation), an Echo (2nd
Generation) or an Echo Dot (3rd Generation) over USB: unlock it, or return it
to stock. It discovers what state the Echo is in and moves it toward the
target.

positional arguments:
  COMMAND            the command to run, one of those listed below

options:
  -h, --help         show this help message and exit
  --credits          show acknowledgement of those whose work firebreak is
                     built upon and exit
  --no-update-check  do not ask PyPI whether a newer firebreak exists
  --verbose          print each adb and fastboot command, its exit status and
                     the time, and each state the Echo reaches
  --version          show program's version number and exit

commands for the Echo Dot (2nd Generation):
  stock [BUILD]
      Amazon's Fire OS BUILD, 8349 when left out, which erases the whole
      Dot.
  unlock [TARGET], where TARGET is one of:
    fireos6, the default
        boot-root.zip's root adb on Fire OS 6 8349, installed over an older
        Fire OS 6, or over Fire OS 5.5.5.4 through Amazon's bridge build
        4315, if need be, which keeps the Dot's setup; with --factory-reset,
        Fire OS 6 8349 with TWRP 3.7.0, with the Dot erased.
    fireos5
        rooted Fire OS 5.5.5.4 on amonet v1.1.0, with TWRP 3.7.0_9-bboe2.

commands for the Echo Dot (3rd Generation):
  stock [BUILD]
      Amazon's Fire OS BUILD, 8349 when left out, which erases the whole
      Echo and locks it again.
  unlock [TARGET], where TARGET is one of:
    fireos6, the default
        boot-root.zip's root adb on Fire OS 6 8349, installed over an older
        Fire OS 6 if need be, which keeps the Echo's setup; with
        --factory-reset, Fire OS 6 8349, with the Echo erased.

commands for the Echo (2nd Generation):
  stock [BUILD]
      Amazon's Fire OS BUILD, 8349 when left out, which erases the whole
      Echo.
  unlock [TARGET], where TARGET is one of:
    fireos6, the default
        boot-root.zip's root adb on Fire OS 6 8349, installed over an older
        Fire OS 6 if need be, which keeps the Echo's setup; with
        --factory-reset, Fire OS 6 8349, with the Echo erased.

Run it again with another of these to move the Echo there.

commands that reach one entry point and stop there:
  reboot
      start the Echo's firmware, as an ordinary power-on does. It reboots
      an Echo in its TWRP or its fastboot, and leaves one that already
      runs its firmware alone. An Echo held in its bootrom needs a power
      cycle, and it says so. It writes nothing.
  fastboot
      start the Echo's fastboot, whichever bootloader it holds. It reboots
      an Echo that answers adb, and asks for the button gesture where it
      cannot. It writes nothing.
  twrp
      start the Echo's TWRP. On an unlocked Echo it restarts into the
      recovery already there and writes nothing, and says what to do where
      that is not a TWRP. A locked Echo has to be unlocked first, which
      erases it, so that one is asked about.
  bootrom
      hold the Echo in its bootrom, where amonet's payload can reach the
      eMMC with no firmware running. It asks before it clears boot0, which
      is what leaves an Echo startable from its bootrom alone. An Echo
      that shows no light cannot be reached this way: `firebreak short` is
      for that one.
  short
      hold the bootrom of an Echo that shows no light, by shorting its
      test point. It says where to short, waits for the bootrom, says when
      the short may come off, and leaves amonet's payload holding it. It
      writes nothing, and --device picks whose test point to describe.

other commands:
  backup [DIRECTORY]
      copy every partition of the Echo's eMMC, its boot areas and both
      copies of its partition table into DIRECTORY, and write backup.json,
      which says how to put each byte back. A partition that begins with
      an image from an OTA firebreak can download names that image instead
      of copying it. It starts the Echo's TWRP to read them, which unlocks
      a locked Echo first and asks before that.
  builds
      list every build `stock` takes for each Echo, newest first, with its
      Fire OS version. It needs no Echo.
  report
      print what the Echo and this computer are, and the Echo's partition
      table, for a support request. It starts the Echo's recovery to read
      them and writes no partition.
  restore DIRECTORY
      put back every byte a backup read, from DIRECTORY, onto the Echo it
      was read from. It rebuilds each partition first, downloading the
      OTAs the backup names, and checks each against the backup before it
      writes anything. It asks before it writes, and leaves the Echo in
      its TWRP.
  survey OTA [OTA ...]
      read each Amazon OTA zip for the tables in docs/devices.md. It needs
      no Echo.
  write-test
      write a known pattern over the Echo's cache partition and read it
      back, which tells a failing eMMC from a failing USB cable because
      nothing crosses USB. It leaves a fresh empty filesystem there, or
      says it could not.

Run `firebreak COMMAND --help` for what that command takes.
```

### adb after an unlock

An unlocked Echo answers root adb over USB and, on Fire OS 6, over Wi-Fi on
port 5555. `unlock` lets in only the computer that ran it: the key in that
computer's `~/.android/adbkey.pub`. Any other computer sees the Echo as
`unauthorized`. From the computer that ran the unlock:

```sh
adb connect ECHO-IP:5555
adb shell
```

Keep `~/.android/adbkey`. Without it, adb cannot reach rooted Fire OS from
any computer. TWRP is not locked, so to move to another computer, or after
losing the key, run `firebreak unlock` from that computer. It asks for the
button gesture, and the install it does from TWRP lets in that computer's key
in place of the old one. On Fire OS 5 that install needs `--factory-reset`,
which erases the Echo's setup: the move that keeps it starts only from a Fire
OS 5 that lets in the computer's key.

## Documentation

- [docs/troubleshooting.md][troubleshooting]: USB and cable problems, Windows
  limits, an Echo Dot (2nd Generation) or Echo (2nd Generation) with no light,
  and an Echo rooted by an older firebreak.
- [docs/unlocking.md][unlocking]: why each step is there.
- [docs/measurements.md][measurements]: the ring at each step, so you can tell
  where a run has got to.

## Reporting a problem

When a run fails, run `uvx firebreak@latest report`. Then go to
`#firebreak-support` in the
[0x7E Labs Discord](https://discord.gg/huE5XhWbsz) and paste both the output of
the run that failed and what `report` prints. `report` writes no partition.

## Credits

firebreak automates work that other people did first.

- [xyz](https://github.com/xyzz/amonet) wrote amonet, a MediaTek bootrom
  exploit. firebreak's bootrom and payload clients follow its protocol.
- [k4y0z](https://github.com/chaosmaster) made the first port of amonet to the
  Echo Dot (2nd Generation).
- [Rortiz2](https://github.com/R0rt1z2) continued
  [that port](https://github.com/R0rt1z2/amonet/tree/mt8163-biscuit), released
  it with TWRP, and keeps its
  [XDA thread](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-2nd-gen-2016-biscuit.4761416/).
  Rortiz2 also wrote amonet-radar and kamakiri-donut, the unlocks for the
  [Echo (2nd Generation)](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-2nd-gen-2017-radar.4801290/)
  and the
  [Echo Dot (3rd Generation)](https://xdaforums.com/t/unlock-root-twrp-unbrick-amazon-echo-dot-3rd-gen-2018-donut.4801400/).
  The `bboe` TWRP is a fork of
  [their TWRP tree](https://github.com/R0rt1z2/twrp_device_amazon_echo-mt8163).
  Rortiz2 takes support for that work through
  [PayPal](https://www.paypal.com/paypalme/R0rt1z2/),
  [Ko-fi](https://ko-fi.com/r0rt1z2) and
  [GitHub Sponsors](https://github.com/sponsors/R0rt1z2).
- AntiEngineer helped find the pins and bring up UART on a Dot.
- [topjohnwu](https://github.com/topjohnwu/Magisk) wrote Magisk, which roots
  Fire OS 5.
- [Andy Goetz](https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/)
  described how to short the eMMC bus at the passives beside R60.
- [mtkclient](https://github.com/bkerler/mtkclient), by bkerler, agrees with
  two of firebreak's bootrom addresses.
- [ftvdb](https://ftvdb.com/) keeps an archive of Fire OS builds.

## Licence

firebreak uses the BSD 2-Clause licence, in [LICENSE.txt][licence]. This
repository contains no Amazon code, and firebreak is not affiliated with,
endorsed by, or supported by Amazon.

[licence]: https://github.com/bboe/firebreak/blob/main/LICENSE.txt
[measurements]: https://github.com/bboe/firebreak/blob/main/docs/measurements.md
[troubleshooting]: https://github.com/bboe/firebreak/blob/main/docs/troubleshooting.md
[troubleshooting-windows]: https://github.com/bboe/firebreak/blob/main/docs/troubleshooting.md#windows
[unlocking]: https://github.com/bboe/firebreak/blob/main/docs/unlocking.md
