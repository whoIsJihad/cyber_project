"""Tests for the complete offline IPv4 and TCP SYN packet."""

from client.checksum import internet_checksum
from client.packet import build_ipv4_tcp_syn_packet
from client.tcp import build_tcp_pseudo_header


def build_example_packet() -> bytes:
    return build_ipv4_tcp_syn_packet(
        source_ip=b"\xC0\xA8\x96\x0A",
        destination_ip=b"\xC0\xA8\x96\x14",
        source_port=0x3039,
        destination_port=0x0050,
        sequence_number=0x11223344,
        window_size=0x4000,
        identification=0x1234,
        ttl=0x40,
    )


def test_complete_packet_is_40_bytes() -> None:
    assert len(build_example_packet()) == 40


def test_complete_packet_has_expected_ipv4_and_tcp_bytes() -> None:
    packet = build_example_packet()

    assert packet[0:20] == bytes.fromhex(
        "45 00 00 28 12 34 00 00 40 06 BB 2C C0 A8 96 0A C0 A8 96 14"
    )
    assert packet[20:40] == bytes.fromhex(
        "30 39 00 50 11 22 33 44 00 00 00 00 50 02 40 00 4D 83 00 00"
    )


def test_both_checksums_validate() -> None:
    packet = build_example_packet()
    ipv4_header = packet[0:20]
    tcp_header = packet[20:40]
    pseudo_header = build_tcp_pseudo_header(
        source_ip=ipv4_header[12:16],
        destination_ip=ipv4_header[16:20],
        tcp_length=len(tcp_header),
    )

    assert internet_checksum(ipv4_header) == 0x0000
    assert internet_checksum(pseudo_header + tcp_header) == 0x0000
