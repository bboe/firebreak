"""Serve the simulated Dot's bootrom, then amonet's payload, on a pseudo-terminal.

python3 sim/bootrom.py
"""

from __future__ import annotations

import collections
import enum
import hashlib
import os
import struct
import subprocess
import sys
import time
import tty
import zipfile

import dot

ACKNOWLEDGEMENT = b"\xd0\xd0\xd0\xd0"
AES_LENGTH = 1
AES_SLOT_POINTERS = [18, 26, 26]
AREAS = {0: "user", 1: "boot0", 2: "boot1"}
BLOCK = 512
BOOTROM_COMMANDS = frozenset({0xC8, 0xD1, 0xD4})
DECRYPT_FUNCTION = 126
EMMC_HEADER = struct.Struct(">cBQI")
EXTENDED = 0xC8
FINISHED = 0x1
FLUSH_ADDRESS = 0x201000
FLUSH_LENGTH = 4
GCPU = 0x10210000
GCPU_ACQUIRE = (0x1F, 0x12000)
GCPU_COMMAND = GCPU + 0x0C00
GCPU_DESTINATION = GCPU + 0x0C08
GCPU_INPUT = GCPU + 0x0C68
GCPU_INTERRUPT_CLEAR = GCPU + 0x0804
GCPU_INTERRUPT_STATUS = GCPU + 0x0800
GCPU_LENGTH = GCPU + 0x0C0C
GCPU_MONITOR = GCPU + 0x0418
GCPU_PROGRAM_CONTROL = GCPU + 0x0400
GCPU_SLOT_POINTERS = GCPU + 0x0C14
HANDSHAKE = ((0xA0, 0x5F), (0x0A, 0xF5), (0x50, 0xAF), (0x05, 0xFA))
JUMP_REGISTER = 0x1028A8
MAGIC = 0xF00DD00D
MMIO_START = 0x10000000
PAYLOAD_ADDRESS = 0x201000
PAYLOAD_VERSIONS = ("v1.1.0", "v2.0.0")
RANGE_CHECK = 0x102868
RANGE_CHECK_OFF = bytes(12) + b"\x80" + bytes(3)
READY = b"\xb1\xb2\xb3\xb4"
READ_STATUS = b"\x00\x00"
READ_WORDS = 0xD1
REFUSED = b"\x1d\x0c"
REFUSED_STATUS = 0x3
RPMB_AREA = 3
RPMB_SIZE = 0x100
SHOWN_WORDS = 16
START_WAIT = 10
V1_COMMANDS = frozenset({0x1000, 0x1001, 0x1002, 0x2000, 0x2001, 0x3000})
WRITE_STATUS = b"\x00\x01"
WRITE_WORDS = 0xD4
ZERO_DECRYPTION = bytes.fromhex("4dd12bdf0ec7d26c482490b3482a1b1f")


class Bootrom:
    def __init__(self, *, payloads: dict[str, bytes], port: Port) -> None:
        self.acquired = False
        self.defeated = False
        self.memory: dict[int, int] = {}
        self.payloads = payloads
        self.port = port
        self.recorder = Recorder()

    def aes(self) -> int:
        pointers = [
            self.memory.get(GCPU_SLOT_POINTERS + 4 * index, 0) for index in range(3)
        ]
        if (
            not self.acquired
            or self.memory.get(GCPU_COMMAND) != DECRYPT_FUNCTION
            or self.memory.get(GCPU_LENGTH) != AES_LENGTH
            or pointers != AES_SLOT_POINTERS
        ):
            return REFUSED_STATUS
        mask = struct.unpack("<4I", ZERO_DECRYPTION)
        address = self.memory.get(GCPU_DESTINATION, 0)
        for index in range(4):
            value = self.memory.get(GCPU_INPUT + 4 * index, 0) ^ mask[index]
            self.memory[address + 4 * index] = value
        found = self.bytes_at(address=RANGE_CHECK, length=len(RANGE_CHECK_OFF))
        self.defeated = self.defeated or found == RANGE_CHECK_OFF
        return FINISHED

    def allowed(self, *, address: int) -> bool:
        return self.defeated or address >= MMIO_START

    def bytes_at(self, *, address: int, length: int) -> bytes:
        return b"".join(
            struct.pack("<I", self.memory.get(address + offset, 0))
            for offset in range(0, length, 4)
        )[:length]

    def echo(self, *, length: int) -> int:
        data = self.port.read(length=length)
        self.port.write(data=data)
        return int.from_bytes(data, "big")

    def handshake(self) -> None:
        step = 0
        while step < len(HANDSHAKE):
            sent, answer = HANDSHAKE[step]
            if self.port.read(length=1)[0] == sent:
                self.port.write(data=bytes([answer]))
                step += 1
            else:
                step = 0
        self.recorder.say(tool="bootrom", words=["handshake"])

    def identify(self) -> str | None:
        for name, payload in self.payloads.items():
            padded = payload + bytes(-len(payload) % 4)
            if self.bytes_at(address=PAYLOAD_ADDRESS, length=len(padded)) == padded:
                return name
        return None

    def jump(self, *, target: int) -> str:
        found = self.identify() if target == PAYLOAD_ADDRESS else None
        self.recorder.say(
            tool="bootrom", words=["jump", f"{target:#x}", found or "unknown code"]
        )
        while found is None:
            self.port.read(length=1)
        self.port.write(data=READY)
        return found

    def read_words(self) -> None:
        address = self.echo(length=4)
        count = self.echo(length=4)
        self.recorder.say(tool="bootrom", words=["read32", f"{address:#x}", str(count)])
        if not self.allowed(address=address):
            self.port.write(data=REFUSED)
            return
        values = [self.memory.get(address + 4 * index, 0) for index in range(count)]
        self.port.write(
            data=READ_STATUS + struct.pack(f">{count}I", *values) + READ_STATUS
        )

    def serve(self) -> str:
        self.handshake()
        while True:
            command = self.port.read(length=1)[0]
            if command not in BOOTROM_COMMANDS:
                self.recorder.say(tool="bootrom", words=["unknown", f"{command:#04x}"])
                continue
            self.port.write(data=bytes([command]))
            if command == READ_WORDS:
                self.read_words()
            elif command == WRITE_WORDS:
                jumped = self.write_words()
                if jumped is not None:
                    return jumped
            else:
                subcommand = self.echo(length=1)
                self.port.write(data=bytes(3))
                self.recorder.say(tool="bootrom", words=["ext", f"{subcommand:#04x}"])

    def store(self, *, address: int, word: int) -> None:
        self.memory[address] = word
        if address == GCPU:
            self.acquired = False
        if address == GCPU + 4:
            self.acquired = (self.memory.get(GCPU), word) == GCPU_ACQUIRE
        if address == GCPU_INTERRUPT_CLEAR:
            self.memory[GCPU_INTERRUPT_STATUS] = 0
            self.memory[GCPU_MONITOR] = 0
        if address == GCPU_PROGRAM_CONTROL:
            status = self.aes()
            self.memory[GCPU_INTERRUPT_STATUS] = status
            self.memory[GCPU_MONITOR] = status & FINISHED

    def write_words(self) -> str | None:
        address = self.echo(length=4)
        count = self.echo(length=4)
        if not self.allowed(address=address):
            self.recorder.say(
                tool="bootrom", words=["write32", f"{address:#x}", f"refused {count}"]
            )
            self.port.write(data=REFUSED)
            return None
        self.port.write(data=WRITE_STATUS)
        words = [self.echo(length=4) for _ in range(count)]
        if count > SHOWN_WORDS:
            data = struct.pack(f"<{count}I", *words)
            shown = [f"{count} words", dot.md5(data=data)]
        else:
            shown = [f"{word:#x}" for word in words]
        self.recorder.say(tool="bootrom", words=["write32", f"{address:#x}", *shown])
        for index, word in enumerate(words):
            self.store(address=address + 4 * index, word=word)
        if address == JUMP_REGISTER and count == 1:
            return self.jump(target=words[0])
        self.port.write(data=WRITE_STATUS)
        return None


class Command(enum.IntEnum):
    READ_BLOCK = 0x1000
    WRITE_BLOCK = 0x1001
    SWITCH_PARTITION = 0x1002
    WRITE_BLOCKS = 0x1003
    READ_BLOCKS = 0x1004
    READ_RPMB = 0x2000
    WRITE_RPMB = 0x2001
    REBOOT = 0x3000
    KICK_WATCHDOG = 0x3001
    READ_MEMORY = 0x5000


class Emmc:
    def __init__(self, *, container: str) -> None:
        self.process = subprocess.Popen(
            ["docker", "exec", "-i", container, "/sim/bin/sim-emmc"],
            bufsize=0,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )

    def answer(self, *, length: int) -> bytes:
        data = b""
        while len(data) < length:
            piece = self.process.stdout.read(length - len(data))
            if not piece:
                message = "the eMMC helper stopped"
                raise OSError(message)
            data += piece
        return data

    def read(self, *, area: int, count: int, first: int) -> bytes | None:
        self.process.stdin.write(EMMC_HEADER.pack(b"r", area, first, count))
        status = self.answer(length=1)
        data = self.answer(length=count * BLOCK)
        return data if status == b"k" else None

    def write(self, *, area: int, data: bytes, first: int) -> bool:
        header = EMMC_HEADER.pack(b"w", area, first, len(data) // BLOCK)
        self.process.stdin.write(header + data)
        return self.answer(length=1) == b"k"


class Payload:
    def __init__(self, *, bootrom: Bootrom, emmc: Emmc, version: str) -> None:
        self.area = 0
        self.bootrom = bootrom
        self.commands = V1_COMMANDS if version == "v1.1.0" else frozenset(Command)
        self.emmc = emmc
        self.port = bootrom.port
        self.recorder = bootrom.recorder

    def area_name(self) -> str:
        return AREAS.get(self.area, f"area {self.area}")

    def read(self, *, command: int, count: int, first: int) -> None:
        data = (
            self.emmc.read(area=self.area, count=count, first=first)
            if self.area in AREAS
            else None
        )
        if data is None:
            self.recorder.say(
                tool="payload",
                words=["read failed", self.area_name(), f"{first}+{count}"],
            )
            data = bytes(count * BLOCK)
        self.recorder.access(
            area=self.area_name(),
            command=command,
            data=data,
            first=first,
            operation="read",
        )
        self.port.write(data=data)

    def read_memory(self, *, command: int) -> None:
        address, length = self.port.word(), self.port.word()
        if (
            address == FLUSH_ADDRESS
            and length == FLUSH_LENGTH
            and self.recorder.run is not None
        ):
            self.recorder.count(command=command)
        else:
            self.recorder.say(
                tool="payload", words=["read memory", f"{address:#x}", str(length)]
            )
        self.port.write(
            data=self.bootrom.bytes_at(address=address, length=(length + 3) & ~3)
        )

    def rpmb(self, *, data: bytes | None) -> bytes:
        block = self.emmc.read(area=RPMB_AREA, count=1, first=0) or bytes(BLOCK)
        if data is not None:
            block = data + block[RPMB_SIZE:]
            self.emmc.write(area=RPMB_AREA, data=block, first=0)
        return block[:RPMB_SIZE]

    def serve(self) -> None:
        while True:
            if self.port.word() != MAGIC:
                self.recorder.say(tool="payload", words=["no magic"])
                continue
            command = self.port.word()
            if command not in self.commands:
                self.recorder.say(tool="payload", words=["unknown", f"{command:#06x}"])
                continue
            if command == Command.REBOOT:
                self.recorder.say(tool="payload", words=["reboot"])
                return
            self.step(command=command)

    def step(self, *, command: int) -> None:
        if command == Command.READ_BLOCK:
            self.read(command=command, count=1, first=self.port.word())
        elif command == Command.READ_BLOCKS:
            first, count = self.port.word(), self.port.word()
            self.read(command=command, count=count, first=first)
        elif command in {Command.WRITE_BLOCK, Command.WRITE_BLOCKS}:
            first = self.port.word()
            count = 1 if command == Command.WRITE_BLOCK else self.port.word()
            data = self.port.read(length=count * BLOCK)
            self.write(command=command, data=data, first=first)
        elif command == Command.SWITCH_PARTITION:
            self.area = self.port.word()
            self.recorder.say(tool="payload", words=["switch", self.area_name()])
        elif command == Command.READ_RPMB:
            found = self.rpmb(data=None)
            self.recorder.say(tool="payload", words=["rpmb read", dot.md5(data=found)])
            self.port.write(data=found)
        elif command == Command.WRITE_RPMB:
            data = self.port.read(length=RPMB_SIZE)
            self.rpmb(data=data)
            self.recorder.say(tool="payload", words=["rpmb write", dot.md5(data=data)])
        elif command == Command.KICK_WATCHDOG:
            self.recorder.count(command=command)
        elif command == Command.READ_MEMORY:
            self.read_memory(command=command)

    def write(self, *, command: int, data: bytes, first: int) -> None:
        written = self.area in AREAS and self.emmc.write(
            area=self.area, data=data, first=first
        )
        if not written:
            self.recorder.say(
                tool="payload",
                words=[
                    "write failed",
                    self.area_name(),
                    f"{first}+{len(data) // BLOCK}",
                ],
            )
        self.recorder.access(
            area=self.area_name(),
            command=command,
            data=data,
            first=first,
            operation="write",
        )
        self.port.write(data=ACKNOWLEDGEMENT)


class Port:
    def __init__(self) -> None:
        self.master, self.slave = os.openpty()
        tty.setraw(self.slave)
        self.name = os.ttyname(self.slave)

    def read(self, *, length: int) -> bytes:
        data = b""
        while len(data) < length:
            data += os.read(self.master, length - len(data))
        return data

    def word(self) -> int:
        return struct.unpack(">I", self.read(length=4))[0]

    def write(self, *, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self.master, view) :]


class Recorder:
    def __init__(self) -> None:
        self.run: Run | None = None

    def access(
        self, *, area: str, command: int, data: bytes, first: int, operation: str
    ) -> None:
        current = self.run
        if (
            current is None
            or current.operation != operation
            or current.area != area
            or current.last + 1 != first
        ):
            self.flush()
            current = self.run = Run(area=area, first=first, operation=operation)
        current.commands[f"{command:#06x}"] += 1
        current.digest.update(data)
        current.last = first + len(data) // BLOCK - 1

    def count(self, *, command: int) -> None:
        if self.run is not None:
            self.run.commands[f"{command:#06x}"] += 1

    def flush(self) -> None:
        current, self.run = self.run, None
        if current is None:
            return
        dot.record(
            entry={
                "argv": [
                    current.operation,
                    current.area,
                    f"{current.first}+{current.last - current.first + 1}",
                    current.digest.hexdigest(),
                ],
                "commands": dict(sorted(current.commands.items())),
                "tool": "payload",
            }
        )

    def say(self, *, tool: str, words: list[str]) -> None:
        self.flush()
        dot.record(entry={"argv": words, "tool": tool})


class Run:
    def __init__(self, *, area: str, first: int, operation: str) -> None:
        self.area = area
        self.commands: collections.Counter[str] = collections.Counter()
        self.digest = hashlib.md5(usedforsecurity=False)
        self.first = first
        self.last = first - 1
        self.operation = operation


def claim(*, port: Port) -> dict | None:
    deadline = time.monotonic() + START_WAIT
    while time.monotonic() < deadline:
        with dot.locked():
            state = dot.load() if dot.STATE.exists() else {}
            if state.get("mode") == "bootrom":
                state.update(bootrom_pid=os.getpid(), port=port.name)
                dot.save(state=state)
                return state
        time.sleep(0.1)
    return None


def known_payloads(*, cache: str) -> dict[str, bytes]:
    found = {}
    for version in PAYLOAD_VERSIONS:
        with zipfile.ZipFile(f"{cache}/amonet-biscuit-{version}.zip") as archive:
            found[version] = dot.member(
                archive=archive, suffix="brom-payload/build/payload.bin"
            )
    return found


def main() -> int:
    port = Port()
    state = claim(port=port)
    if state is None:
        return 1
    bootrom = Bootrom(payloads=known_payloads(cache=state["cache"]), port=port)
    try:
        version = bootrom.serve()
        bootrom.recorder.say(tool="payload", words=["ready", version])
        Payload(
            bootrom=bootrom, emmc=Emmc(container=state["container"]), version=version
        ).serve()
    finally:
        bootrom.recorder.flush()
    with dot.locked():
        state = dot.load()
        state.pop("bootrom_pid", None)
        state.pop("port", None)
        dot.reboot(into="system", state=state)
        dot.save(state=state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
