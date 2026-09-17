"""Tests for the no-options IPv4 header."""

import pytest

from client.checksum import internet_checksum
from client.ipv4 import build_ipv4_header


def build_example_header() -> bytes:
    return build_ipv4_header(
        source_ip=b"\xC0\xA8\x96\x0A",
        destination_ip=b"\xC0\xA8\x96\x14",
        payload_length=20,
        identification=0x1234,
        ttl=0x40,
    )


def test_ipv4_header_is_20_bytes() -> None:
    assert len(build_example_header()) == 20


def test_version_header_length_and_total_length_are_correct() -> None:
    header = build_example_header()

    assert header[0] == 0x45
    assert header[1] == 0x00
    assert header[2:4] == b"\x00\x28"


def test_identification_fragment_ttl_and_protocol_are_correct() -> None:
    header = build_example_header()

    assert header[4:6] == b"\x12\x34"
    assert header[6:8] == b"\x00\x00"
    assert header[8] == 0x40
    assert header[9] == 0x06


def test_addresses_and_checksum_are_correct() -> None:
    header = build_example_header()

    assert header[12:16] == b"\xC0\xA8\x96\x0A"
    assert header[16:20] == b"\xC0\xA8\x96\x14"
    assert header[10:12] != b"\x00\x00"
    assert internet_checksum(header) == 0x0000


def test_ttl_must_fit_in_one_byte() -> None:
    with pytest.raises(ValueError, match="ttl must fit"):
        build_ipv4_header(
            source_ip=b"\xC0\xA8\x96\x0A",
            destination_ip=b"\xC0\xA8\x96\x14",
            payload_length=20,
            identification=0x1234,
            ttl=0x100,
        )
