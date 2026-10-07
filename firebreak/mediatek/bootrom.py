from __future__ import annotations

import contextlib
import os
import pathlib
import struct
import sys
import time
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any, Protocol

    class Device(Protocol):
        dev: Any

        def _writeb(self, *, out_str: bytes) -> bytes: ...

        def check(self, *, gold: bytes, test: bytes) -> None: ...

        def emmc_read(self, *, index: int) -> bytes: ...

        def emmc_switch(self, *, part: int) -> None: ...

        def emmc_write_blocks(self, *, data: bytes, index: int) -> None: ...

    class UsbPort(Protocol):
        device: str
        pid: int | None
        vid: int | None


ACKNOWLEDGED = b"\xd0\xd0\xd0\xd0"
BAUD = 115200
BLOCKS_PER_WRITE = 64
BLOCK_SIZE = 0x200
BOOTROM_PRODUCT_ID = 0x0003
BOOT_SIGNATURE = b"\x55\xaa"
EMMC_READ = 0x1000
EMMC_WRITE = 0x1003
FLUSH_ADDRESS = 0x201000
FLUSH_LENGTH = 4
HANDSHAKE_WAIT = 10
MAGIC = 0xF00DD00D
MEDIATEK_VENDOR_ID = 0x0E8D
MEMORY_READ = 0x5000
PRELOADER_PRODUCT_ID = 0x2000
RESET = 0x3000
RPMB_READ = 0x2000
RPMB_SIZE = 0x100
Value = TypeVar("Value")


def answered(*, device: Device) -> bool:
    import serial  # ruff: ignore[import-outside-top-level]

    deadline = time.monotonic() + HANDSHAKE_WAIT
    try:
        while time.monotonic() < deadline:
            if device._writeb(out_str=b"\xa0") == b"\x5f":  # ruff: ignore[private-member-access]
                return True
            device.dev.flushInput()
    except serial.SerialException:
        pass
    return False


def child_bootrom() -> int:
    sys.path.insert(0, str(pathlib.Path.cwd()))
    import common  # ruff: ignore[import-outside-top-level]
    import main as amonet  # ruff: ignore[import-outside-top-level]

    start_payload = amonet.load_payload

    def load_payload(device: Device, path: str) -> None:
        start_payload(dev=device, path=path)
        try:
            device.emmc_switch(part=0)
            first_block = device.emmc_read(index=0)
            signature = first_block[BLOCK_SIZE - len(BOOT_SIGNATURE) : BLOCK_SIZE]
            booted = signature == BOOT_SIGNATURE
        except RuntimeError:
            booted = False
        if not booted:
            log(message="The eMMC did not answer")
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
                    baudrate=BAUD, port=port.device, timeout=1, write_timeout=1
                ) as connection:
                    connection.write(data=struct.pack(">II", MAGIC, RESET))
            except serial.SerialException:
                pass
    return 0


def emmc_read(self: Device, index: int) -> bytes:
    self.dev.write(data=struct.pack(">III", MAGIC, EMMC_READ, index))
    return read_flushed(device=self, size=BLOCK_SIZE)


def emmc_write_blocks(self: Device, index: int, data: bytes) -> None:
    self.dev.write(
        data=struct.pack(">IIII", MAGIC, EMMC_WRITE, index, len(data) // BLOCK_SIZE)
    )
    self.dev.write(data=data)
    if self.dev.read(size=len(ACKNOWLEDGED)) != ACKNOWLEDGED:
        message = "device failure"
        raise RuntimeError(message)


def find_device(self: Device, *_: object) -> None:
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    resume = os.environ.get("FIREBREAK_RESUME")
    seen = {
        port: product_id
        for port, product_id in mediatek_ports(ports=list_ports.comports()).items()
        if not (resume and product_id == BOOTROM_PRODUCT_ID)
    }
    failed: dict[str, float] = {}
    log(message="Waiting for bootrom")
    while True:
        product_ids = mediatek_ports(ports=list_ports.comports())
        seen = still_present(known=seen, ports=product_ids)
        failed = still_present(known=failed, ports=product_ids)
        for port, product_id in sorted(product_ids.items()):
            if product_id is None or seen.get(port) == product_id:
                continue
            if product_id == BOOTROM_PRODUCT_ID:
                if open_bootrom(device=self, failed=failed, port=port):
                    return
            else:
                seen[port] = product_id
                if product_id == PRELOADER_PRODUCT_ID:
                    log(message="Ignoring the preloader on " + port)
        time.sleep(0.25)


def flash_data(
    device: Device, data: bytes, start_block: int, max_size: int = 0
) -> None:
    marker = os.environ.get("FIREBREAK_ERASED")
    if marker:
        pathlib.Path(marker).touch()
    data += b"\0" * (-len(data) % BLOCK_SIZE)
    if max_size and len(data) > max_size:
        message = "data too big to flash"
        raise RuntimeError(message)
    span = BLOCKS_PER_WRITE * BLOCK_SIZE
    for offset in range(0, len(data), span):
        device.emmc_write_blocks(
            data=data[offset : offset + span],
            index=start_block + offset // BLOCK_SIZE,
        )


def handshake(self: Device) -> None:
    import serial  # ruff: ignore[import-outside-top-level]
    from serial.tools import list_ports  # ruff: ignore[import-outside-top-level]

    while not answered(device=self):
        log(message="The bootrom did not answer the handshake")
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


def log(*, message: str) -> None:
    from logger import log as amonet_log  # ruff: ignore[import-outside-top-level]

    amonet_log(s=message)


def mediatek_ports(*, ports: Sequence[UsbPort]) -> dict[str, int | None]:
    return {
        port_info.device: port_info.pid
        for port_info in ports
        if port_info.vid == MEDIATEK_VENDOR_ID
    }


def open_bootrom(*, device: Device, failed: dict[str, float], port: str) -> bool:
    import common  # ruff: ignore[import-outside-top-level]
    import serial  # ruff: ignore[import-outside-top-level]

    try:
        device.dev = serial.Serial(
            baudrate=common.BAUD, port=port, timeout=common.TIMEOUT
        )
    except serial.SerialException as error:
        first_failure = failed.setdefault(port, time.monotonic())
        if first_failure and time.monotonic() - first_failure >= 1:
            failed[port] = 0
            log(message="Cannot open " + port + ": " + str(error))
        return False
    log(message="Found port = " + port)
    return True


def read_flushed(*, device: Device, size: int) -> bytes:
    device.dev.write(
        data=struct.pack(">IIII", MAGIC, MEMORY_READ, FLUSH_ADDRESS, FLUSH_LENGTH)
    )
    data = device.dev.read(size=size + FLUSH_LENGTH)
    if len(data) != size + FLUSH_LENGTH:
        message = "read fail"
        raise RuntimeError(message)
    return data[:size]


def rpmb_read(self: Device) -> bytes:
    self.dev.write(data=struct.pack(">II", MAGIC, RPMB_READ))
    return read_flushed(device=self, size=RPMB_SIZE)


def still_present(
    *, known: dict[str, Value], ports: dict[str, int | None]
) -> dict[str, Value]:
    return {port: value for port, value in known.items() if port in ports}
