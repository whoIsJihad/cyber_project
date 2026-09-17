"""Send verified IPv4/TCP SYN packets to the isolated receiver VM only."""

import argparse
import ipaddress
from pathlib import Path
import socket
import sys
import time


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

from client.packet import build_ipv4_tcp_syn_packet


# The lab contains only the sender at .10 and receiver at .20. Reserve the
# upper half of this isolated subnet for synthetic sources. Keeping the source
# pool on the receiver's own link avoids reverse-path and routing ambiguity.
# `hosts()` excludes .128 (network) and .255 (broadcast).
SOURCE_NETWORK = ipaddress.ip_network("192.168.150.128/25")
SOURCE_IP_ADDRESSES = tuple(SOURCE_NETWORK.hosts())
# C0 A8 96 14 is 192.168.150.20, the fixed isolated receiver address.
DESTINATION_IP_BYTES = b"\xC0\xA8\x96\x14"
# sendto needs the receiver address as readable text, not as four raw bytes.
DESTINATION_IP_TEXT = "192.168.150.20"
# 0x0050 is decimal 80, the receiver's Nginx TCP port.
DESTINATION_PORT = 0x0050
# Use every non-privileged TCP source port for one synthetic source IP, then
# automatically advance to the next IP. The maximum is derived from the source
# pool and the 16-bit TCP port field rather than an arbitrary experiment limit.
FIRST_SOURCE_PORT = 1024
LAST_SOURCE_PORT = 65535
PORTS_PER_SOURCE_IP = LAST_SOURCE_PORT - FIRST_SOURCE_PORT + 1
MAX_PACKET_COUNT = len(SOURCE_IP_ADDRESSES) * PORTS_PER_SOURCE_IP


def source_identity(packet_number: int) -> tuple[bytes, int]:
    """Return the synthetic source IP and port for one unique connection."""
    if packet_number < 0 or packet_number >= MAX_PACKET_COUNT:
        raise ValueError(f"packet number must be 0 through {MAX_PACKET_COUNT - 1}")

    source_ip_index, port_offset = divmod(packet_number, PORTS_PER_SOURCE_IP)
    source_ip = SOURCE_IP_ADDRESSES[source_ip_index].packed
    source_port = FIRST_SOURCE_PORT + port_offset
    return source_ip, source_port


def build_packet(packet_number: int) -> bytes:
    """Build one SYN packet with visible changing sequence values."""
    source_ip, source_port = source_identity(packet_number)
    return build_ipv4_tcp_syn_packet(
        source_ip=source_ip,
        destination_ip=DESTINATION_IP_BYTES,
        source_port=source_port,
        destination_port=DESTINATION_PORT,
        # Start from a visible test sequence number and change it per packet.
        sequence_number=(0x11223344 + packet_number) & 0xFFFFFFFF,
        # 0x4000 is the advertised 16-bit TCP receive window for this packet.
        window_size=0x4000,
        # IPv4 identification is only 16 bits. Wrapping it is valid and does
        # not merge TCP connections because their source ports remain unique.
        identification=(0x1234 + packet_number) & 0xFFFF,
        # 0x40 is decimal 64, a conventional IPv4 Time To Live value.
        ttl=0x40,
    )


def validate_settings(packet_count: int, rate: int) -> None:
    """Reject impossible values and values outside this isolated-lab sender."""
    if packet_count < 1 or packet_count > MAX_PACKET_COUNT:
        raise ValueError(f"packet count must be 1 through {MAX_PACKET_COUNT}")

    if rate < 1:
        raise ValueError("rate must be a positive integer")


def packet_count_for_duration(duration: float, rate: int) -> int:
    """Return the bounded packet count for one requested lab duration."""
    if duration <= 0:
        raise ValueError("duration must be positive")

    validate_settings(1, rate)
    packet_count = int(duration * rate)
    if packet_count < 1:
        raise ValueError("duration and rate must produce at least one packet")
    validate_settings(packet_count, rate)
    return packet_count


def send_syn_packets(
    packet_count: int,
    rate: int,
    socket_factory=socket.socket,
    wait_function=time.sleep,
) -> int:
    """Send packet_count SYN packets to the fixed isolated receiver only."""
    validate_settings(packet_count, rate)

    # AF_INET means IPv4. SOCK_RAW allows our program to provide packet bytes.
    # IPPROTO_RAW selects raw IPv4 output rather than a normal TCP connection.
    raw_socket = socket_factory(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)

    try:
        # IP_HDRINCL = 1 tells Linux our packet already includes the IPv4
        # header, so Linux must not create a second IPv4 header around it.
        raw_socket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

        for packet_number in range(packet_count):
            packet = build_packet(packet_number)
            # The port is 0 here because the finished TCP header already holds
            # the real destination port, 0x0050. The raw IPv4 socket uses the
            # address only to choose the route and local network interface.
            raw_socket.sendto(packet, (DESTINATION_IP_TEXT, 0))

            if packet_number < packet_count - 1:
                wait_function(1 / rate)
    finally:
        raw_socket.close()

    return packet_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Send SYN packets to the isolated receiver VM.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--count", type=int, default=10)
    selection.add_argument("--duration", type=float, help="Seconds to send.")
    parser.add_argument("--rate", type=int, default=10)
    arguments = parser.parse_args()

    try:
        packet_count = arguments.count
        if arguments.duration is not None:
            packet_count = packet_count_for_duration(arguments.duration, arguments.rate)
        else:
            validate_settings(packet_count, arguments.rate)
    except ValueError as error:
        parser.error(str(error))

    started_at = time.monotonic()
    sent_count = send_syn_packets(packet_count, arguments.rate)
    elapsed_seconds = time.monotonic() - started_at
    print(
        f"sent {sent_count} SYN packets with synthetic sources from "
        f"{SOURCE_NETWORK} to {DESTINATION_IP_TEXT}:{DESTINATION_PORT}"
    )
    print(f"rate: {arguments.rate} packets/second; elapsed: {elapsed_seconds:.2f} seconds")


if __name__ == "__main__":
    main()
