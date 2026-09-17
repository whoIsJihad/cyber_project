"""Join one verified IPv4 header and one verified TCP SYN header."""

from client.ipv4 import build_ipv4_header
from client.tcp import add_tcp_checksum, build_tcp_syn_header


def build_ipv4_tcp_syn_packet(
    source_ip: bytes,
    destination_ip: bytes,
    source_port: int,
    destination_port: int,
    sequence_number: int,
    window_size: int,
    identification: int,
    ttl: int,
) -> bytes:
    """Return one complete IPv4 packet containing a TCP SYN header.

    The returned value contains IPv4 bytes followed immediately by TCP bytes.
    It does not contain Ethernet bytes and it does not send anything.
    """
    tcp_header_without_checksum = build_tcp_syn_header(
        source_port,
        destination_port,
        sequence_number,
        window_size,
    )
    tcp_header = add_tcp_checksum(
        tcp_header_without_checksum,
        source_ip,
        destination_ip,
    )

    ipv4_header = build_ipv4_header(
        source_ip,
        destination_ip,
        len(tcp_header),
        identification,
        ttl,
    )

    # IPv4 is first because it is the outer envelope. TCP follows immediately
    # as IPv4's payload, so 20 IPv4 bytes + 20 TCP bytes = 40 packet bytes.
    return ipv4_header + tcp_header
