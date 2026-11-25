# Troubleshooting

## USB

- A ring that stays solid blue at the fastboot gesture can mean a cable that
  carries power but no data, or a bad USB connection. Try another cable, then
  another port. On Windows it can also mean the
  [drivers](https://github.com/bboe/firebreak#windows) are missing.
- A ring that restarts instead of reaching TWRP, blue with about a second of
  turning cyan and little or no white, has been a USB port that cannot power
  it. To tell, hold the + button with the device on a USB wall charger: a ring
  that reaches white there means TWRP runs. Then use another port. A USB 3
  port on the computer itself, with nothing else on it, is the most reliable.
- An Echo that drops off USB during a TWRP step, more than once, has also been
  a port that cannot power it. Where the run says boot0 may hold no
  preloader, run firebreak again first. If it fails the same way, unplug the
  Echo, run firebreak again, and plug it into another port.
- A `/system` write that keeps failing with `failed to read copy response: EOF`
  can mean a poor USB connection. Unplug both ends of the cable, plug them back
  in firmly, and try another cable if it fails again.

## Windows

- The drivers have x86 and x64 builds only, so on Windows on ARM the steps
  that use fastboot or the bootrom cannot run.
- UsbDk has run on Windows 11 23H2. mtkclient reports it broken on 25H2
  (build 26200).
- On a Windows older than 11 23H2, `tar` cannot unpack a `.7z`. It prints an
  error, but PowerShell runs the rest of the setup. An Echo Dot (3rd
  Generation) then stops because it finds no libusb. Unpack
  `VS2022\MS64\dll\libusb-1.0.dll` from `%TEMP%\libusb.7z` into
  `%LOCALAPPDATA%\Programs\libusb` with 7-Zip, and keep its folders.

## An Echo Dot (2nd Generation) or Echo (2nd Generation) with no light

Use `firebreak short` when the Echo shows no light and gives no fastboot, or
when its bootloader is one no fastbrick unlocks. It reaches the Echo's bootrom
by shorting its eMMC bus as it powers up, and holds it there. The run after it
joins that payload with no second short, so this is how a target run starts
on an Echo that cannot reach fastboot.

The short does not apply to an Echo Dot (3rd Generation), and `short` refuses
one. Run the target you want, such as `uvx firebreak@latest unlock`, and when
it asks, hold the action button from before you plug it in until the run says
the bootrom answered. That reaches its bootrom with the case closed.

1. Open the Echo with a Torx T8 screwdriver. On an Echo (2nd Generation),
   follow [iFixit's main board
   guide](https://www.ifixit.com/Guide/Amazon+Echo+2nd+Generation+MLB+Board+Replacement/114704)
   through step 8, and leave the board in. Lift the shield's lid off the eMMC
   by its corners; its metal frame stays on the board.
2. Find the passive marked in [this
   photo](https://xdaforums.com/attachments/short2-jpg.6273804/), in the row
   between R60 and C52 beside the eMMC ([where that is on the
   board](https://andygoetz.org/blog/2022/05/echo-dot-v2-dumping-emmc/)). Do not
   use C52, which is a capacitor. An Echo (2nd Generation) has the same parts
   in the same place, on a board marked `30-002527`.
3. With the Echo unplugged, run
   `uvx firebreak@latest short --device biscuit` on a Dot, or
   `uvx firebreak@latest short --device radar` on an Echo (2nd Generation).
4. When firebreak prints "Short … test point and plug it in", hold a wire from
   that passive to the shield frame beside it, which is ground, and plug the
   Echo in. An Echo plugged in before that message can go unseen. On "Short …
   missed", unplug it and try again.
5. Take the wire off when firebreak prints "The short may come off now".
6. Leave the Echo plugged in, and run the target you want, such as
   `uvx firebreak@latest unlock`. A power cycle loses the hold.

## An eMMC that sends nothing

A run that stops with "amonet's payload answered, but the eMMC sent no data",
or with "amonet's payload sent no acknowledgement" after a write, reached the
Echo's bootrom and started amonet's payload, but the eMMC gave that payload
nothing back. A short still held when the payload starts does
this, so take the wire off when firebreak says. Otherwise unplug the Echo for
a few minutes and run firebreak again once.

If it fails the same way again, the eMMC has most likely failed. On one Echo
Dot (2nd Generation) with a Samsung eMMC, the chip answered neither reads nor
writes. firebreak reaches the eMMC from the bootrom only through that
payload, so it cannot repair such an Echo.

## An Echo rooted by an older firebreak

An Echo rooted on Fire OS 6 by firebreak 1.1.x or earlier lets anyone on its
network into its root adb. One rooted by 1.0.0 or earlier also has only a
raised build number against Amazon's updates. Amazon's update server offered
nothing to that number on 2026-11-11, but `otad` still runs and the hosts file
blocks nothing.

On a Fire OS 6 build older than 8349, run a plain `unlock`. It downloads
8349, reboots the Echo into TWRP and installs 8349 over the old build. It
adds what is missing, and the Echo keeps its setup.

On 8349, a plain `unlock` says the Echo is rooted and stops. To add what is
missing there and keep the setup, start in its TWRP:

```sh
uvx firebreak@latest twrp
uvx firebreak@latest unlock
```

From TWRP, the unlock installs `boot-root.zip` again, blocks updates and
locks adb in each Fire OS 6 slot, and starts Fire OS.
`unlock --factory-reset` also adds them, but installs Fire OS 6 again and
erases the Echo.
