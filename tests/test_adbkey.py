from __future__ import annotations

import base64

import pytest
from conftest import ADB_KEY, adb_private_key, der, integer

from firebreak.android import adbkey

ODD = (1 << 2047) + 1


def pem(*, body: bytes) -> bytes:
    return (
        b"-----BEGIN PRIVATE KEY-----\n"
        + base64.encodebytes(body)
        + b"-----END PRIVATE KEY-----\n"
    )


def rsa(*, exponent: int, modulus: int) -> bytes:
    return der(
        body=integer(value=0) + integer(value=modulus) + integer(value=exponent),
        tag=adbkey.SEQUENCE,
    )


def test_a_key_that_is_not_base64_gives_nothing() -> None:
    assert adbkey.public_key(pem=b"-----BEGIN PRIVATE KEY-----\n!!\n") == b""


def test_adb_s_public_key_comes_from_its_private_key() -> None:
    assert adbkey.public_key(pem=adb_private_key()) == ADB_KEY


def test_an_odd_2048_bit_modulus_gives_a_key() -> None:
    assert adbkey.public_key(pem=pem(body=wrapped(key=rsa(exponent=3, modulus=ODD))))


def wrapped(*, key: bytes) -> bytes:
    return der(
        body=integer(value=0)
        + der(body=adbkey.RSA_ALGORITHM, tag=adbkey.SEQUENCE)
        + der(body=key, tag=adbkey.OCTET_STRING),
        tag=adbkey.SEQUENCE,
    )


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\x30\x05\x02\x01\x00",
        b"\x30\x82\x01\x00\x02\x01\x00",
        b"\x30\x8a",
        der(
            body=integer(value=0)
            + der(body=b"\x06\x03\x2a\x03\x04\x05\x00", tag=adbkey.SEQUENCE),
            tag=adbkey.SEQUENCE,
        ),
        rsa(exponent=3, modulus=ODD),
        wrapped(key=rsa(exponent=3, modulus=15)),
        wrapped(key=rsa(exponent=3, modulus=ODD - 1)),
        wrapped(key=rsa(exponent=1 << 32, modulus=ODD)),
    ],
    ids=[
        "empty",
        "truncated",
        "overlong",
        "no-length",
        "not-rsa",
        "pkcs1",
        "small",
        "even",
        "large-exponent",
    ],
)
def test_a_key_adb_does_not_make_gives_nothing(*, body: bytes) -> None:
    assert adbkey.public_key(pem=pem(body=body)) == b""
