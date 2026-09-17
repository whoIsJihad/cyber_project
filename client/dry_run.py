"""Print one complete SYN packet without opening a network socket."""

from pathlib import Path
import sys


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

from client.generator import DESTINATION_IP_BYTES, DESTINATION_PORT, source_identity
from client.packet import build_ipv4_tcp_syn_packet


def format_packet_report(packet: bytes) -> str:
    """Return a readable report for one already-built IPv4/TCP packet."""
    # Our first packet has a 20-byte IPv4 header with no options. TCP starts
    # at byte 20 and this bare SYN header occupies the next 20 bytes.
    ipv4_header = packet[0:20]
    tcp_header = packet[20:40]

    return "\n".join(
        [
            f"packet length: {len(packet)} bytes",
            f"IPv4 header: {ipv4_header.hex(' ')}",
            f"TCP header:  {tcp_header.hex(' ')}",
            f"full packet: {packet.hex(' ')}",
            "dry run: no packet was sent",
        ]
    )


def main() -> None:
    source_ip, source_port = source_identity(0)
    packet = build_ipv4_tcp_syn_packet(
        source_ip=source_ip,
        destination_ip=DESTINATION_IP_BYTES,
        source_port=source_port,
        destination_port=DESTINATION_PORT,
        sequence_number=0x11223344,
        window_size=0x4000,
        identification=0x1234,
        ttl=0x40,
    )
    print(format_packet_report(packet))


if __name__ == "__main__":
    main()
