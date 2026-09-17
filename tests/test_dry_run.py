"""Tests for the no-network packet report."""

from pathlib import Path
import subprocess
import sys

from client.dry_run import format_packet_report
from client.packet import build_ipv4_tcp_syn_packet


def test_packet_report_shows_headers_and_no_send_message() -> None:
    packet = build_ipv4_tcp_syn_packet(
        source_ip=b"\xC0\xA8\x96\x0A",
        destination_ip=b"\xC0\xA8\x96\x14",
        source_port=0x3039,
        destination_port=0x0050,
        sequence_number=0x11223344,
        window_size=0x4000,
        identification=0x1234,
        ttl=0x40,
    )

    report = format_packet_report(packet)

    assert "packet length: 40 bytes" in report
    assert "IPv4 header: 45 00 00 28" in report
    assert "TCP header:  30 39 00 50" in report
    assert "dry run: no packet was sent" in report


def test_dry_run_can_run_as_a_normal_script() -> None:
    project_root = Path(__file__).resolve().parent.parent

    result = subprocess.run(
        [sys.executable, "client/dry_run.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=True,
    )

    assert "packet length: 40 bytes" in result.stdout
    assert "dry run: no packet was sent" in result.stdout
