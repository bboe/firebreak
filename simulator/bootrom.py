"""Serve the simulated Echo's bootrom, then amonet's payload or kamakiri's two
stages, on a pseudo-terminal. A second pseudo-terminal carries the control
transfers that a donut's exploits send.

python3 simulator/bootrom.py WORK
"""

from __future__ import annotations

import collections
import enum
import hashlib
import json
import os
import select
import signal
import struct
import subprocess
import sys
import threading
import time
import tty
import zipfile
from typing import TYPE_CHECKING

import dot

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from firebreak_sim_ports import REAL_MONOTONIC, REAL_SLEEP
except ImportError:
    REAL_MONOTONIC, REAL_SLEEP = time.monotonic_ns, time.sleep

ACCESS = 0xDA
ACCESS_OFFSET = 0x40
ACCESS_WALKS = frozenset({0xD7A8, 0xD7A9, 0xD7AA, 0xD7B1, 0xD7B2, 0xD7B3})
ACKNOWLEDGEMENT = b"\xd0\xd0\xd0\xd0"
AES_LENGTH = 1
AES_SLOT_POINTERS = [18, 26, 26]
AREAS = {0: "user", 1: "boot0", 2: "boot1"}
BLOCK = 512
BOOTROM_COMMANDS = frozenset({0xC8, 0xD1, 0xD4, 0xFD})
CONFIGURATION = bytes.fromhex("0902430002010080fa")
CONTROL_STALL = {"error": "[Errno 32] Pipe error"}
DECRYPT_FUNCTION = 126
EMMC_HEADER = struct.Struct(">cBQI")
EXTENDED = 0xC8
FAST_SEND_PATTERN = bytes((index * 7) & 0xFF for index in range(0x200))
FED = threading.Event()
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
GET_DESCRIPTOR = (0x80, 0x06, 0x0200)
GET_LINE_CODING = (0xA1, 0x21)
HANDSHAKE = ((0xA0, 0x5F), (0x0A, 0xF5), (0x50, 0xAF), (0x05, 0xFA))
HARDWARE_CODE = 0xFD
JUMP_REGISTER = 0x1028A8
KAMAKIRI_COMMANDS = frozenset({
    0x1000,
    0x1002,
    0x1003,
    0x1004,
    0x2000,
    0x3000,
    0x3001,
    0x5000,
    0x6000,
})
KAMAKIRI_PAYLOAD = 0x100A00
LADDER = frozenset(range(2, 17))
LINE_CODING = bytes.fromhex("00c20100000008")
LOAD_STAGE2 = 0x4000
MAGIC = 0xF00DD00D
MAXIMUM_BLOCKS = 64
MMIO_START = 0x10000000
NANOSECONDS = 1_000_000_000
PAYLOAD_ADDRESS = 0x201000
RANGE_CHECK = 0x102868
RANGE_CHECK_OFF = bytes(12) + b"\x80" + bytes(3)
READY = b"\xb1\xb2\xb3\xb4"
READ_STATUS = b"\x00\x00"
READ_WORDS = 0xD1
REFUSED = b"\x1d\x0c"
REFUSED_STATUS = 0x3
RPMB_AREA = 3
RPMB_SIZE = 0x100
SEND_PAYLOAD = 0xE0
SEND_POINTER = 0xD2E4
SEND_ROUTINE = 0x102C40
SET_FASTBOOT_FLAG = 0x6000
SET_LINE_CODING = (0x21, 0x20)
SHOWN_WORDS = 16
STAGE1_READY = b"\xa1\xa2\xa3\xa4"
STAGES = {
    "stage1": "brom-payload/stage1/stage1.bin",
    "stage2": "brom-payload/stage2/stage2.bin",
}
START_STAGE2 = 0x4001
START_WAIT = 10
TRIGGER = (0xA1, 0x00, 0xCC)
V1_COMMANDS = frozenset({0x1000, 0x1001, 0x1002, 0x2000, 0x2001, 0x3000})
WATCHDOG_DARK_SECONDS = 39
WATCHDOG_RESTART = 0x10007050
WATCHDOG_SECONDS = 40
WRITE_STATUS = b"\x00\x01"
WRITE_WORDS = 0xD4
ZERO_DECRYPTION = bytes.fromhex("4dd12bdf0ec7d26c482490b3482a1b1f")


class Bootrom:
    def __init__(
        self,
        *,
        hardware: int,
        payloads: dict[str, bytes],
        port: Port,
        stages: dict[str, bytes] | None = None,
    ) -> None:
        self.acquired = False
        self.defeated = False
        self.hardware = hardware
        self.ladder: set[int] = set()
        self.line_coding = LINE_CODING
        self.memory: dict[int, int] = (
            {} if stages is None else {SEND_POINTER: SEND_ROUTINE}
        )
        self.payloads = payloads
        self.pointer: int | None = None
        self.port = port
        self.recorder = Recorder()
        self.sent = b""
        self.stages = stages
        self.walked: set[int] = set()
        port.answer = self.control

    def access(self) -> str | None:
        writing, address, length = (self.echo(length=4) for _ in range(3))
        operation = "write" if writing else "read"
        if not self.walked >= ACCESS_WALKS:
            self.recorder.say(
                tool="bootrom",
                words=["access", operation, f"{address:#x}", f"refused {length}"],
            )
            self.port.write(data=REFUSED)
            return None
        self.walked.clear()
        real = address + ACCESS_OFFSET
        self.port.write(data=READ_STATUS)
        if not writing:
            self.recorder.say(
                tool="bootrom", words=["access", "read", f"{real:#x}", str(length)]
            )
            self.port.write(data=self.bytes_at(address=real, length=length))
            self.port.write(data=READ_STATUS)
            return None
        data = self.port.read(length=length)
        shown = dot.md5(data=data) if length > SHOWN_WORDS * 4 else data.hex()
        self.recorder.say(
            tool="bootrom", words=["access", "write", f"{real:#x}", str(length), shown]
        )
        self.put(address=real, data=data)
        if real == self.memory[SEND_POINTER] + 8:
            return self.jump(target=self.memory.get(real, 0))
        self.port.write(data=READ_STATUS)
        return None

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

    def control(self, *, request: dict) -> dict:
        data = bytes.fromhex(request.get("data", ""))
        kind, code = request["request_type"], request["request"]
        words = [f"{kind:#04x}", f"{code:#04x}", f"{request['index']:#x}"]
        self.recorder.say(tool="control", words=[*words, data.hex()] if data else words)
        if self.stages is None:
            return CONTROL_STALL
        if (kind, code) == SET_LINE_CODING and request["index"] == 0:
            self.line_coding = data[: len(LINE_CODING)]
            if len(data) >= len(LINE_CODING) + 5:
                self.pointer = struct.unpack_from("<I", data, len(LINE_CODING) + 1)[0]
            return {}
        if (kind, code) == GET_LINE_CODING and request["index"] == 0:
            return {"data": self.line_coding.hex()}
        if (kind, code, request["value"]) == GET_DESCRIPTOR:
            if self.pointer is not None:
                self.walked.add(self.pointer)
                self.pointer = None
            return {"data": CONFIGURATION[: request["length"]].hex()}
        if (kind, code, request["index"]) == TRIGGER and self.triggered():
            self.put(address=KAMAKIRI_PAYLOAD, data=self.sent)
            self.sent = b""
            self.port.jumping = KAMAKIRI_PAYLOAD
        return CONTROL_STALL

    def echo(self, *, length: int) -> int:
        data = self.port.read(length=length)
        self.port.write(data=data)
        return int.from_bytes(data, "big")

    def handshake(self) -> None:
        step = 0
        while step < len(HANDSHAKE):
            sent, answer = HANDSHAKE[step]
            got = self.port.read(length=1)[0]
            if got == sent:
                self.port.write(data=bytes([answer]))
                step += 1
            else:
                self.port.write(data=bytes([(got + 1) & 0xFF]))
                step = 0
        FED.set()
        self.recorder.say(tool="bootrom", words=["handshake"])

    def hardware_code(self) -> None:
        self.recorder.say(
            tool="bootrom", words=["hardware code", f"{self.hardware:#06x}"]
        )
        self.port.write(data=struct.pack(">HH", self.hardware, 0))

    def identify(self, *, target: int) -> str | None:
        known = (
            {"stage1": self.stages["stage1"]}
            if self.stages is not None and target == KAMAKIRI_PAYLOAD
            else self.payloads
            if target == PAYLOAD_ADDRESS
            else {}
        )
        for name, payload in known.items():
            padded = payload + bytes(-len(payload) % 4)
            if self.bytes_at(address=target, length=len(padded)) == padded:
                return name
        return None

    def jump(self, *, target: int) -> str:
        found = self.identify(target=target)
        self.recorder.say(
            tool="bootrom", words=["jump", f"{target:#x}", found or "unknown code"]
        )
        while found is None:
            self.port.read(length=1)
        self.port.write(data=STAGE1_READY if found == "stage1" else READY)
        return found

    def put(self, *, address: int, data: bytes) -> None:
        whole = data + bytes(-len(data) % 4)
        for offset in range(0, len(whole), 4):
            (self.memory[address + offset],) = struct.unpack_from("<I", whole, offset)

    def read_words(self) -> None:
        address = self.echo(length=4)
        count = self.echo(length=4)
        if not self.allowed(address=address):
            self.recorder.say(
                tool="bootrom", words=["read32", f"{address:#x}", f"refused {count}"]
            )
            self.port.write(data=REFUSED)
            return
        self.recorder.say(tool="bootrom", words=["read32", f"{address:#x}", str(count)])
        if address + 4 * count == WATCHDOG_RESTART + 4:
            self.ladder.add(count)
        values = [self.memory.get(address + 4 * index, 0) for index in range(count)]
        self.port.write(
            data=READ_STATUS + struct.pack(f">{count}I", *values) + READ_STATUS
        )

    def send_payload(self) -> None:
        length = self.echo(length=4)
        self.port.write(data=READ_STATUS)
        self.sent = self.port.read(length=length)
        self.recorder.say(
            tool="bootrom",
            words=["send payload", str(length), dot.md5(data=self.sent)],
        )
        self.port.write(data=READ_STATUS + READ_STATUS)

    def serve(self) -> str:
        self.handshake()
        try:
            return self.served()
        except Jumped as jumped:
            return self.jump(target=jumped.target)

    def served(self) -> str:
        commands = BOOTROM_COMMANDS | (
            frozenset() if self.stages is None else {ACCESS, SEND_PAYLOAD}
        )
        while True:
            command = self.port.read(length=1)[0]
            if command not in commands:
                self.recorder.say(tool="bootrom", words=["unknown", f"{command:#04x}"])
                continue
            self.port.write(data=bytes([command]))
            jumped = None
            if command == READ_WORDS:
                self.read_words()
            elif command == WRITE_WORDS:
                jumped = self.write_words()
            elif command == HARDWARE_CODE:
                self.hardware_code()
            elif command == ACCESS:
                jumped = self.access()
            elif command == SEND_PAYLOAD:
                self.send_payload()
            else:
                subcommand = self.echo(length=1)
                self.port.write(data=bytes(3))
                self.recorder.say(tool="bootrom", words=["ext", f"{subcommand:#04x}"])
            if jumped is not None:
                return jumped

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

    def triggered(self) -> bool:
        reversed_address = struct.unpack("<I", struct.pack(">I", KAMAKIRI_PAYLOAD))[0]
        return (
            bool(self.sent)
            and self.ladder >= LADDER
            and self.memory.get(WATCHDOG_RESTART) == reversed_address
        )

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
    TRY_FAST_SEND = 0x5002
    STOCK_SEND = 0x5003


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
        with dot.busy():
            self.process.stdin.write(EMMC_HEADER.pack(b"r", area, first, count))
            status = self.answer(length=1)
            data = self.answer(length=count * BLOCK)
        return data if status == b"k" else None

    def write(self, *, area: int, data: bytes, first: int) -> bool:
        header = EMMC_HEADER.pack(b"w", area, first, len(data) // BLOCK)
        with dot.busy():
            self.process.stdin.write(header + data)
            return self.answer(length=1) == b"k"


class Jumped(Exception):  # ruff: ignore[error-suffix-on-exception-name]
    def __init__(self, *, target: int) -> None:
        super().__init__(f"{target:#x}")
        self.target = target


class Payload:
    def __init__(self, *, bootrom: Bootrom, emmc: Emmc, version: str) -> None:
        self.area = 0
        self.bootrom = bootrom
        self.commands = {
            "stage2": KAMAKIRI_COMMANDS,
            "v1.1.0": V1_COMMANDS,
        }.get(version, frozenset(Command))
        self.emmc = emmc
        self.fastboot = False
        self.port = bootrom.port
        self.recorder = bootrom.recorder

    def area_name(self) -> str:
        return AREAS.get(self.area, f"area {self.area}")

    def check_count(self, *, command: int, count: int, first: int) -> None:
        if (
            command in {Command.READ_BLOCKS, Command.WRITE_BLOCKS}
            and not 1 <= count <= MAXIMUM_BLOCKS
        ):
            self.halt(words=[f"{command:#06x}", "count", f"{first}+{count}"])

    def halt(self, *, words: list[str]) -> None:
        self.recorder.say(tool="payload", words=["halted", *words])
        while True:
            self.port.read(length=1)

    def read(self, *, command: int, count: int, first: int) -> None:
        data = (
            self.emmc.read(area=self.area, count=count, first=first)
            if self.area in AREAS
            else None
        )
        if data is None:
            self.halt(words=["read failed", self.area_name(), f"{first}+{count}"])
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
        if address == FLUSH_ADDRESS and length == FLUSH_LENGTH:
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

    def step(self, *, command: int) -> None:  # ruff: ignore[complex-structure]
        if command == Command.READ_BLOCK:
            self.read(command=command, count=1, first=self.port.word())
        elif command == Command.READ_BLOCKS:
            first, count = self.port.word(), self.port.word()
            self.check_count(command=command, count=count, first=first)
            self.read(command=command, count=count, first=first)
        elif command in {Command.WRITE_BLOCK, Command.WRITE_BLOCKS}:
            first = self.port.word()
            count = 1 if command == Command.WRITE_BLOCK else self.port.word()
            self.check_count(command=command, count=count, first=first)
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
        elif command == Command.TRY_FAST_SEND:
            self.recorder.say(tool="payload", words=["fast send"])
            self.port.write(data=FAST_SEND_PATTERN)
        elif command == Command.STOCK_SEND:
            self.recorder.say(tool="payload", words=["stock send"])
            self.port.write(data=ACKNOWLEDGEMENT)
        elif command == SET_FASTBOOT_FLAG:
            self.recorder.say(tool="payload", words=["fastboot flag"])
            self.fastboot = True

    def write(self, *, command: int, data: bytes, first: int) -> None:
        written = self.area in AREAS and self.emmc.write(
            area=self.area, data=data, first=first
        )
        if not written:
            self.halt(
                words=[
                    "write failed",
                    self.area_name(),
                    f"{first}+{len(data) // BLOCK}",
                ]
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
        self.control_master, self.control_slave = os.openpty()
        tty.setraw(self.control_slave)
        self.control_name = os.ttyname(self.control_slave)
        self.answer: Callable[..., dict] | None = None
        self.jumping: int | None = None
        self.requests = b""

    def read(self, *, length: int) -> bytes:
        data = b""
        while len(data) < length:
            readable, _, _ = select.select([self.master, self.control_master], [], [])
            if self.control_master in readable:
                self.serve_control()
            if self.master in readable:
                data += os.read(self.master, length - len(data))
        return data

    def serve_control(self) -> None:
        self.requests += os.read(self.control_master, 4096)
        while b"\n" in self.requests:
            line, self.requests = self.requests.split(b"\n", 1)
            request = json.loads(line)
            reply = (
                CONTROL_STALL if self.answer is None else self.answer(request=request)
            )
            self.write_control(reply=reply)
        if self.jumping is not None:
            target, self.jumping = self.jumping, None
            raise Jumped(target=target)

    def word(self) -> int:
        return struct.unpack(">I", self.read(length=4))[0]

    def write(self, *, data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(self.master, view) :]

    def write_control(self, *, reply: dict) -> None:
        view = memoryview(json.dumps(reply).encode() + b"\n")
        while view:
            view = view[os.write(self.control_master, view) :]


class Recorder:
    def __init__(self) -> None:
        self.loose: collections.Counter[str] = collections.Counter()
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
        commands = self.loose if self.run is None else self.run.commands
        commands[f"{command:#06x}"] += 1

    def flush(self) -> None:
        current, self.run = self.run, None
        if self.loose:
            dot.record(
                entry={
                    "argv": ["between ranges"],
                    "commands": dict(sorted(self.loose.items())),
                    "loose": True,
                    "tool": "payload",
                }
            )
            self.loose.clear()
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


class Watchdog(Exception):  # ruff: ignore[error-suffix-on-exception-name]
    pass


def bite(*_: object) -> None:
    if not FED.is_set():
        raise Watchdog


def claim(*, port: Port) -> dict | None:
    deadline = REAL_MONOTONIC() + START_WAIT * NANOSECONDS
    mode = "gone"
    while REAL_MONOTONIC() < deadline:
        with dot.locked():
            state = dot.load() if dot.STATE.exists() else {}
            mode = state.get("mode", "gone")
            if mode == "bootrom":
                state.update(
                    bootrom_pid=os.getpid(), control=port.control_name, port=port.name
                )
                dot.save(state=state)
                return state
        REAL_SLEEP(0.1)
    print(
        f"no bootrom mode to claim within {START_WAIT} seconds; the Dot is {mode}",
        file=sys.stderr,
    )
    return None


def driven(*, bootrom: Bootrom, container: str) -> str:
    version = bootrom.serve()
    if version == "stage1":
        version = stage1(bootrom=bootrom)
    bootrom.recorder.say(tool="payload", words=["ready", version])
    payload = Payload(bootrom=bootrom, emmc=Emmc(container=container), version=version)
    payload.serve()
    return "bootloader" if payload.fastboot else "system"


def known_payloads(*, cache: str, spec: dict) -> dict[str, bytes]:
    found = {}
    for version, kit in spec.get("payloads", {}).items():
        with zipfile.ZipFile(f"{cache}/{kit}") as archive:
            found[version] = dot.member(
                archive=archive, suffix="brom-payload/build/payload.bin"
            )
    return found


def known_stages(*, cache: str, spec: dict) -> dict[str, bytes] | None:
    if "kit" not in spec:
        return None
    with zipfile.ZipFile(f"{cache}/{spec['kit']}") as archive:
        return {
            name: dot.member(archive=archive, suffix=suffix)
            for name, suffix in STAGES.items()
        }


def main() -> int:
    if sys.argv[1:] != [str(dot.WORK)]:
        print(f"usage: {sys.argv[0]} {dot.WORK}", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, stop)
    port = Port()
    state = claim(port=port)
    if state is None:
        return 1
    delay, into = dot.BOOT_SECONDS, None
    try:
        spec = dot.DEVICES[state["device"]]
        bootrom = Bootrom(
            hardware=spec["hardware"],
            payloads=known_payloads(cache=state["cache"], spec=spec),
            port=port,
            stages=known_stages(cache=state["cache"], spec=spec),
        )
        if "kit" in spec:
            signal.signal(signal.SIGALRM, bite)
            threading.Thread(daemon=True, target=watch).start()
        try:
            into = driven(bootrom=bootrom, container=state["container"])
        except Watchdog:
            bootrom.recorder.say(tool="bootrom", words=["watchdog"])
            delay, into = WATCHDOG_DARK_SECONDS, "system"
        finally:
            bootrom.recorder.flush()
    finally:
        release(delay=delay, into=into)
    return 0


def release(*, delay: float, into: str | None) -> None:
    FED.set()
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    with dot.locked():
        if not dot.STATE.exists():
            return
        state = dot.load()
        if state.get("bootrom_pid") != os.getpid():
            return
        state.pop("bootrom_pid", None)
        state.pop("control", None)
        state.pop("port", None)
        if into is not None:
            dot.reboot(delay=delay, into=into, state=state)
        dot.save(state=state)


def stage1(*, bootrom: Bootrom) -> str:
    port, recorder = bootrom.port, bootrom.recorder
    stage2 = b""
    while True:
        if port.word() != MAGIC:
            recorder.say(tool="stage1", words=["no magic"])
            continue
        command = port.word()
        if command == LOAD_STAGE2:
            address, length = port.word(), port.word()
            stage2 = port.read(length=length)
            recorder.say(
                tool="stage1",
                words=["load", f"{address:#x}", str(length), dot.md5(data=stage2)],
            )
            port.write(data=ACKNOWLEDGEMENT)
        elif command == START_STAGE2:
            address = port.word()
            known = stage2 == (bootrom.stages or {}).get("stage2")
            recorder.say(
                tool="stage1",
                words=["start", f"{address:#x}", "stage2" if known else "unknown code"],
            )
            while not known:
                port.read(length=1)
            port.write(data=READY)
            return "stage2"
        else:
            recorder.say(tool="stage1", words=["unknown", f"{command:#06x}"])


def stop(*_: object) -> None:
    raise SystemExit(1)


def watch() -> None:
    deadline = time.monotonic() + WATCHDOG_SECONDS
    while time.monotonic() < deadline and not FED.is_set():
        time.sleep(0.1)
    if not FED.is_set():
        signal.pthread_kill(threading.main_thread().ident, signal.SIGALRM)


if __name__ == "__main__":
    sys.exit(main())
