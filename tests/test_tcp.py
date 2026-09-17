"""Tests for offline construction of the initial TCP SYN header."""

from client.checksum import internet_checksum
from client.tcp import add_tcp_checksum, build_tcp_pseudo_header, build_tcp_syn_header


def build_example_header() -> bytes:
    return build_tcp_syn_header(
        source_port=0x3039,
        destination_port=0x0050,
        sequence_number=0x11223344,
        window_size=0x4000,
    )


def test_syn_header_is_20_bytes() -> None:
    header = build_example_header()

    assert len(header) == 20


def test_ports_are_in_the_first_four_bytes() -> None:
    header = build_example_header()

    assert header[0:2] == b"\x30\x39"
    assert header[2:4] == b"\x00\x50"


def test_sequence_and_acknowledgement_numbers_are_correct() -> None:
    header = build_example_header()

    assert header[4:8] == b"\x11\x22\x33\x44"
    assert header[8:12] == b"\x00\x00\x00\x00"


def test_header_length_and_syn_flag_are_correct() -> None:
    header = build_example_header()

    assert header[12] == 0x50
    assert header[13] == 0x02


def test_window_checksum_and_urgent_pointer_are_correct() -> None:
    header = build_example_header()

    assert header[14:16] == b"\x40\x00"
    assert header[16:18] == b"\x00\x00"
    assert header[18:20] == b"\x00\x00"


def test_pseudo_header_has_the_required_12_bytes() -> None:
    pseudo_header = build_tcp_pseudo_header(
        source_ip=b"\xC0\xA8\x96\x0A",
        destination_ip=b"\xC0\xA8\x96\x14",
        tcp_length=0x0014,
    )

    assert pseudo_header == b"\xC0\xA8\x96\x0A\xC0\xA8\x96\x14\x00\x06\x00\x14"


def test_checksum_is_inserted_and_validates_the_complete_tcp_header() -> None:
    source_ip = b"\xC0\xA8\x96\x0A"
    destination_ip = b"\xC0\xA8\x96\x14"
    header_without_checksum = build_example_header()

    complete_header = add_tcp_checksum(
        header_without_checksum,
        source_ip,
        destination_ip,
    )
    pseudo_header = build_tcp_pseudo_header(source_ip, destination_ip, len(complete_header))

    assert complete_header[16:18] != b"\x00\x00"
    assert internet_checksum(pseudo_header + complete_header) == 0x0000
