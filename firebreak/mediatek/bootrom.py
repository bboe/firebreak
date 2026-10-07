from __future__ import annotations

import contextlib
import os
import pathlib
import struct
import sys
import time

BROM_PID = 0x0003
HANDSHAKE_WAIT = 10
MEDIATEK_VID = 0x0E8D
PRELOADER_PID = 0x2000


def child_bootrom() -> int:  # ruff: ignore[complex-structure, too-many-statements]
    sys.path.insert(0, str(pathlib.Path.cwd()))
    import common  # ruff: ignore[import-outside-top-level]
    import main as amonet  # ruff: ignore[import-outside-top-level]
    import serial  # ruff: ignore[import-outside-top-level]
    from logger import log  # ruff: ignore[import-outside-top-level]
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    marker = os.environ.get("FIREBREAK_ERASED")
    resume = os.environ.get("FIREBREAK_RESUME")
    start_payload = amonet.load_payload

    def emmc_read(self: common.Device, idx: int) -> bytes:
        self.dev.write(struct.pack(">III", 0xF00DD00D, 0x1000, idx))
        return read_flushed(self, 0x200)

    def emmc_write_blocks(self: common.Device, idx: int, data: bytes) -> None:
        self.dev.write(
            struct.pack(">IIII", 0xF00DD00D, 0x1003, idx, len(data) // 0x200)
        )
        self.dev.write(data)
        if self.dev.read(4) != b"\xd0\xd0\xd0\xd0":
            msg = "device failure"
            raise RuntimeError(msg)

    def flash_data(
        dev: common.Device, data: bytes, start_block: int, max_size: int = 0
    ) -> None:
        if marker:
            pathlib.Path(marker).touch()
        data += b"\0" * (-len(data) % 0x200)
        if max_size and len(data) > max_size:
            msg = "data too big to flash"
            raise RuntimeError(msg)
        for x in range(0, len(data), 64 * 0x200):
            dev.emmc_write_blocks(start_block + x // 0x200, data[x : x + 64 * 0x200])

    def read_flushed(self: common.Device, size: int) -> bytes:
        self.dev.write(struct.pack(">IIII", 0xF00DD00D, 0x5000, 0x201000, 4))
        data = self.dev.read(size + 4)
        if len(data) != size + 4:
            msg = "read fail"
            raise RuntimeError(msg)
        return data[:size]

    def rpmb_read(self: common.Device) -> bytes:
        self.dev.write(struct.pack(">II", 0xF00DD00D, 0x2000))
        return read_flushed(self, 0x100)

    def find_device(self: common.Device, *_: object) -> None:
        seen = {
            p.device: p.pid
            for p in list_ports.comports()
            if p.vid == MEDIATEK_VID and not (resume and p.pid == BROM_PID)
        }
        failed = {}
        log("Waiting for bootrom")
        while True:
            pids = {
                p.device: p.pid for p in list_ports.comports() if p.vid == MEDIATEK_VID
            }
            seen = {port: pid for port, pid in seen.items() if port in pids}
            failed = {port: at for port, at in failed.items() if port in pids}
            for port, pid in sorted(pids.items()):
                if pid is None or seen.get(port) == pid:
                    continue
                if pid == BROM_PID:
                    try:
                        self.dev = serial.Serial(
                            port, common.BAUD, timeout=common.TIMEOUT
                        )
                    except serial.SerialException as e:
                        at = failed.setdefault(port, time.monotonic())
                        if at and time.monotonic() - at >= 1:
                            failed[port] = 0
                            log("Cannot open " + port + ": " + str(e))
                        continue
                    log("Found port = " + port)
                    return
                seen[port] = pid
                if pid == PRELOADER_PID:
                    log("Ignoring the preloader on " + port)
            time.sleep(0.25)

    def answered(self: common.Device) -> bool:
        deadline = time.monotonic() + HANDSHAKE_WAIT
        try:
            while time.monotonic() < deadline:
                if self._writeb(b"\xa0") == b"\x5f":
                    return True
                self.dev.flushInput()
        except serial.SerialException:
            pass
        return False

    def handshake(self: common.Device) -> None:
        while not answered(self):
            log("The bootrom did not answer the handshake")
            port = self.dev.port
            with contextlib.suppress(serial.SerialException):
                self.dev.close()
            self.dev = None
            while any(p.device == port for p in list_ports.comports()):
                time.sleep(0.25)
            find_device(self)
        self.check(self._writeb(b"\x0a"), b"\xf5")
        self.check(self._writeb(b"\x50"), b"\xaf")
        self.check(self._writeb(b"\x05"), b"\xfa")

    def load_payload(dev: common.Device, path: str) -> None:
        start_payload(dev, path)
        try:
            dev.emmc_switch(0)
            answered = dev.emmc_read(0)[510:512] == b"\x55\xaa"
        except RuntimeError:
            answered = False
        if not answered:
            log("The eMMC did not answer")
            raise SystemExit(3)

    common.Device.emmc_read = emmc_read
    common.Device.emmc_write_blocks = emmc_write_blocks
    common.Device.find_device = find_device
    common.Device.handshake = handshake
    common.Device.rpmb_read = rpmb_read
    amonet.flash_data = flash_data
    amonet.load_payload = load_payload
    amonet.main()
    return 0


def child_reset() -> int:
    import serial  # ruff: ignore[import-outside-top-level]
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    for port in list_ports.comports():
        if port.vid == MEDIATEK_VID:
            try:
                with serial.Serial(
                    port.device, 115200, timeout=1, write_timeout=1
                ) as dev:
                    dev.write(struct.pack(">II", 0xF00DD00D, 0x3000))
            except serial.SerialException:
                pass
    return 0
