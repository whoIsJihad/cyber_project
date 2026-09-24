"""Send verified IPv4/TCP SYN packets to the isolated receiver VM only."""

import argparse
import ipaddress
from multiprocessing import Process
from pathlib import Path
import socket
import signal
import sys
import time


if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

from client.packet import build_ipv4_tcp_syn_packet


# 2-device hotspot demo on NetworkManager's shared subnet 10.42.0.0/24. The
# real hosts are gateway .1, server (receiver) .81 and attacker .157. Draw
# synthetic sources from the .192/26 block (.193-.254), which avoids all three,
# so a spoofed SYN never carries a real device's address -- otherwise the
# server's SYN-ACK would reach that real host, which would RST and tear down
# the half-open slot early. `hosts()` excludes .192 (network) and .255 (broadcast).
SOURCE_NETWORK = ipaddress.ip_network("10.42.0.192/26")
SOURCE_IP_ADDRESSES = tuple(SOURCE_NETWORK.hosts())
# 0A 2A 00 51 is 10.42.0.81, the receiver (server) address.
DESTINATION_IP_BYTES = b"\x0A\x2A\x00\x51"
# sendto needs the receiver address as readable text, not as four raw bytes.
DESTINATION_IP_TEXT = "10.42.0.81"
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
    packet_count: int | None,
    rate: int,
    socket_factory=socket.socket,
    wait_function=time.sleep,
    start_offset: int = 0,
    stride: int = 1,
) -> int:
    """Send to the fixed receiver; None continues until interrupted.

    ``start_offset``/``stride`` let several worker processes share the packet
    number space without ever reusing the same source IP/port pair at once.
    """
    validate_settings(1 if packet_count is None else packet_count, rate)
    sent_count = 0
    packet_number = start_offset

    # AF_INET means IPv4. SOCK_RAW allows our program to provide packet bytes.
    # IPPROTO_RAW selects raw IPv4 output rather than a normal TCP connection.
    raw_socket = socket_factory(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)

    try:
        # IP_HDRINCL = 1 tells Linux our packet already includes the IPv4
        # header, so Linux must not create a second IPv4 header around it.
        raw_socket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)

        while packet_count is None or sent_count < packet_count:
            packet = build_packet(packet_number % MAX_PACKET_COUNT)
            # The port is 0 here because the finished TCP header already holds
            # the real destination port, 0x0050. The raw IPv4 socket uses the
            # address only to choose the route and local network interface.
            raw_socket.sendto(packet, (DESTINATION_IP_TEXT, 0))

            sent_count += 1
            packet_number += stride
            if packet_count is None or sent_count < packet_count:
                wait_function(1 / rate)
    except KeyboardInterrupt:
        pass
    finally:
        raw_socket.close()

    return sent_count


def run_worker(worker_index: int, workers: int, packet_count: int | None, rate: int, result_queue) -> None:
    """Entry point for one worker process; shares the total rate evenly."""
    sent_count = send_syn_packets(
        packet_count,
        rate,
        start_offset=worker_index,
        stride=workers,
    )
    result_queue.put(sent_count)


def stop_on_signal(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description="Send SYN packets to the isolated receiver VM.")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--count", type=int, default=10)
    selection.add_argument("--continuous", action="store_true", help="Send until Ctrl+C or SIGTERM.")
    selection.add_argument("--duration", type=float, help="Seconds to send.")
    parser.add_argument("--rate", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1,
        help="Parallel sender processes; one raw socket in one process tops out "
             "around 800-1000 pkt/s, so use several to reach a high total rate.")
    arguments = parser.parse_args()

    if arguments.workers < 1:
        parser.error("workers must be a positive integer")

    try:
        packet_count = arguments.count
        if arguments.continuous:
            validate_settings(1, arguments.rate)
            packet_count = None
        elif arguments.duration is not None:
            packet_count = packet_count_for_duration(arguments.duration, arguments.rate)
        else:
            validate_settings(packet_count, arguments.rate)
    except ValueError as error:
        parser.error(str(error))

    signal.signal(signal.SIGTERM, stop_on_signal)
    print(f"Sending to {DESTINATION_IP_TEXT}:{DESTINATION_PORT} with {arguments.workers} worker(s); Ctrl+C stops sending.", flush=True)
    started_at = time.monotonic()

    if arguments.workers == 1:
        sent_count = send_syn_packets(packet_count, arguments.rate)
    else:
        from multiprocessing import Queue

        per_worker_rate = max(1, arguments.rate // arguments.workers)
        per_worker_count = None if packet_count is None else max(1, packet_count // arguments.workers)
        result_queue = Queue()
        processes = [
            Process(target=run_worker, args=(index, arguments.workers, per_worker_count, per_worker_rate, result_queue))
            for index in range(arguments.workers)
        ]
        for process in processes:
            process.start()

        try:
            for process in processes:
                process.join()
        except KeyboardInterrupt:
            for process in processes:
                process.terminate()
            for process in processes:
                process.join()

        sent_count = 0
        while not result_queue.empty():
            sent_count += result_queue.get()

    elapsed_seconds = time.monotonic() - started_at
    print(
        f"sent {sent_count} SYN packets with synthetic sources from "
        f"{SOURCE_NETWORK} to {DESTINATION_IP_TEXT}:{DESTINATION_PORT}"
    )
    print(f"requested rate: {arguments.rate} packets/second; elapsed: {elapsed_seconds:.2f} seconds; "
        f"actual rate: {sent_count / elapsed_seconds:.2f} packets/second")


if __name__ == "__main__":
    main()
