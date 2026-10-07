from __future__ import annotations

import contextlib
import os
import pathlib
import struct
import sys
import time

BOOTROM_PRODUCT_ID = 0x0003
HANDSHAKE_WAIT = 10
MEDIATEK_VENDOR_ID = 0x0E8D
PRELOADER_PRODUCT_ID = 0x2000


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

    def emmc_read(self: common.Device, index: int) -> bytes:
        self.dev.write(data=struct.pack(">III", 0xF00DD00D, 0x1000, index))
        return read_flushed(device=self, size=0x200)

    def emmc_write_blocks(self: common.Device, index: int, data: bytes) -> None:
        self.dev.write(
            data=struct.pack(">IIII", 0xF00DD00D, 0x1003, index, len(data) // 0x200)
        )
        self.dev.write(data=data)
        if self.dev.read(size=4) != b"\xd0\xd0\xd0\xd0":
            message = "device failure"
            raise RuntimeError(message)

    def flash_data(
        device: common.Device, data: bytes, start_block: int, max_size: int = 0
    ) -> None:
        if marker:
            pathlib.Path(marker).touch()
        data += b"\0" * (-len(data) % 0x200)
        if max_size and len(data) > max_size:
            message = "data too big to flash"
            raise RuntimeError(message)
        for offset in range(0, len(data), 64 * 0x200):
            device.emmc_write_blocks(
                data=data[offset : offset + 64 * 0x200],
                index=start_block + offset // 0x200,
            )

    def read_flushed(*, device: common.Device, size: int) -> bytes:
        device.dev.write(data=struct.pack(">IIII", 0xF00DD00D, 0x5000, 0x201000, 4))
        data = device.dev.read(size=size + 4)
        if len(data) != size + 4:
            message = "read fail"
            raise RuntimeError(message)
        return data[:size]

    def rpmb_read(self: common.Device) -> bytes:
        self.dev.write(data=struct.pack(">II", 0xF00DD00D, 0x2000))
        return read_flushed(device=self, size=0x100)

    def find_device(self: common.Device, *_: object) -> None:
        seen = {
            port_info.device: port_info.pid
            for port_info in list_ports.comports()
            if port_info.vid == MEDIATEK_VENDOR_ID
            and not (resume and port_info.pid == BOOTROM_PRODUCT_ID)
        }
        failed = {}
        log(s="Waiting for bootrom")
        while True:
            product_ids = {
                port_info.device: port_info.pid
                for port_info in list_ports.comports()
                if port_info.vid == MEDIATEK_VENDOR_ID
            }
            seen = {
                port: product_id
                for port, product_id in seen.items()
                if port in product_ids
            }
            failed = {
                port: first_failure
                for port, first_failure in failed.items()
                if port in product_ids
            }
            for port, product_id in sorted(product_ids.items()):
                if product_id is None or seen.get(port) == product_id:
                    continue
                if product_id == BOOTROM_PRODUCT_ID:
                    try:
                        self.dev = serial.Serial(
                            baudrate=common.BAUD, port=port, timeout=common.TIMEOUT
                        )
                    except serial.SerialException as error:
                        first_failure = failed.setdefault(port, time.monotonic())
                        if first_failure and time.monotonic() - first_failure >= 1:
                            failed[port] = 0
                            log(s="Cannot open " + port + ": " + str(error))
                        continue
                    log(s="Found port = " + port)
                    return
                seen[port] = product_id
                if product_id == PRELOADER_PRODUCT_ID:
                    log(s="Ignoring the preloader on " + port)
            time.sleep(0.25)

    def answered(*, device: common.Device) -> bool:
        deadline = time.monotonic() + HANDSHAKE_WAIT
        try:
            while time.monotonic() < deadline:
                if device._writeb(out_str=b"\xa0") == b"\x5f":  # ruff: ignore[private-member-access]
                    return True
                device.dev.flushInput()
        except serial.SerialException:
            pass
        return False

    def handshake(self: common.Device) -> None:
        while not answered(device=self):
            log(s="The bootrom did not answer the handshake")
            port = self.dev.port
            with contextlib.suppress(serial.SerialException):
                self.dev.close()
            self.dev = None
            while any(port_info.device == port for port_info in list_ports.comports()):
                time.sleep(0.25)
            find_device(self=self)
        self.check(gold=b"\xf5", test=self._writeb(out_str=b"\x0a"))
        self.check(gold=b"\xaf", test=self._writeb(out_str=b"\x50"))
        self.check(gold=b"\xfa", test=self._writeb(out_str=b"\x05"))

    def load_payload(device: common.Device, path: str) -> None:
        start_payload(dev=device, path=path)
        try:
            device.emmc_switch(part=0)
            answered = device.emmc_read(index=0)[510:512] == b"\x55\xaa"
        except RuntimeError:
            answered = False
        if not answered:
            log(s="The eMMC did not answer")
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
        if port.vid == MEDIATEK_VENDOR_ID:
            try:
                with serial.Serial(
                    baudrate=115200, port=port.device, timeout=1, write_timeout=1
                ) as connection:
                    connection.write(data=struct.pack(">II", 0xF00DD00D, 0x3000))
            except serial.SerialException:
                pass
    return 0
