from __future__ import annotations

import base64
import binascii
import struct

INTEGER = 0x02
MODULUS_BITS = 2048
OCTET_STRING = 0x04
RSA_ALGORITHM = bytes.fromhex("06092a864886f70d0101010500")
SEQUENCE = 0x30
WORD_BITS = 32


def element(*, data: bytes, offset: int, tag: int) -> tuple[bytes, int]:
    if data[offset] != tag:
        raise ValueError(tag)
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[offset : offset + count], byteorder="big")
        offset += count
    end = offset + length
    if end > len(data):
        raise ValueError(end)
    return data[offset:end], end


def modulus_and_exponent(*, der: bytes) -> tuple[int, int]:
    info, _ = element(data=der, offset=0, tag=SEQUENCE)
    _, offset = element(data=info, offset=0, tag=INTEGER)
    algorithm, offset = element(data=info, offset=offset, tag=SEQUENCE)
    if algorithm != RSA_ALGORITHM:
        raise ValueError(algorithm)
    octets, _ = element(data=info, offset=offset, tag=OCTET_STRING)
    key, _ = element(data=octets, offset=0, tag=SEQUENCE)
    _, offset = element(data=key, offset=0, tag=INTEGER)
    modulus, offset = element(data=key, offset=offset, tag=INTEGER)
    exponent, _ = element(data=key, offset=offset, tag=INTEGER)
    return int.from_bytes(modulus, byteorder="big"), int.from_bytes(
        exponent, byteorder="big"
    )


def public_key(*, pem: bytes) -> bytes:
    try:
        der = base64.b64decode(
            b"".join(
                line for line in pem.splitlines() if not line.startswith(b"-----")
            ),
            validate=True,
        )
        modulus, exponent = modulus_and_exponent(der=der)
    except (IndexError, ValueError, binascii.Error):
        return b""
    if (
        modulus.bit_length() != MODULUS_BITS
        or not modulus & 1
        or exponent >= 1 << WORD_BITS
    ):
        return b""
    size = MODULUS_BITS // 8
    blob = (
        struct.pack(
            "<II",
            MODULUS_BITS // WORD_BITS,
            -pow(modulus, -1, 1 << WORD_BITS) % (1 << WORD_BITS),
        )
        + modulus.to_bytes(byteorder="little", length=size)
        + pow(2, 2 * MODULUS_BITS, modulus).to_bytes(byteorder="little", length=size)
        + struct.pack("<I", exponent)
    )
    return base64.b64encode(blob) + b"\n"
