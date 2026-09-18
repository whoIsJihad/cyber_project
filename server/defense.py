"""Detect per-source SYN-flood pressure and apply temporary firewall blocks.

Unlike net.ipv4.tcp_syncookies, this is not a built-in kernel defense: it
watches SYN-RECEIVED state the same way server/monitor.py does, decides when
one source IP holds too many half-open connections on the protected port,
and reacts by inserting a temporary iptables rule that drops further SYNs
from that source until a cooldown expires.
"""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time


CSV_FIELDS = [
    "timestamp_utc",
    "action",
    "source_ip",
    "syn_recv_count",
    "block_seconds",
]


def run_command(command_parts: list[str]) -> str:
    """Run one system command and return its standard output."""
    result = subprocess.run(command_parts, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command_parts)} failed: {result.stderr.strip()}")
    return result.stdout


def parse_syn_recv_sources(output: str) -> list[str]:
    """Return one source IP per half-open connection line from `ss`."""
    sources = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        peer_address = line.split()[-1]
        sources.append(peer_address.rsplit(":", 1)[0])
    return sources


def count_by_source(sources: list[str]) -> dict[str, int]:
    """Count half-open connections per source IP."""
    return dict(Counter(sources))


def sources_over_threshold(counts: dict[str, int], threshold: int) -> list[str]:
    """Return source IPs whose half-open count meets or exceeds the threshold."""
    return [source_ip for source_ip, count in counts.items() if count >= threshold]


def block_rule(source_ip: str, port: int) -> list[str]:
    """Return the iptables command that drops new SYNs from one source."""
    return ["iptables", "-I", "INPUT", "-p", "tcp", "-s", source_ip, "--dport", str(port), "--syn", "-j", "DROP"]


def unblock_rule(source_ip: str, port: int) -> list[str]:
    """Return the iptables command that lifts a previously applied block."""
    return ["iptables", "-D", "INPUT", "-p", "tcp", "-s", source_ip, "--dport", str(port), "--syn", "-j", "DROP"]


def expired_blocks(active_blocks: dict[str, float], now: float) -> list[str]:
    """Return source IPs whose block cooldown has passed."""
    return [source_ip for source_ip, expires_at in active_blocks.items() if now >= expires_at]


def log_event(csv_path: Path, action: str, source_ip: str, syn_recv_count: int, block_seconds: float) -> None:
    """Append one detection/action event to the evidence CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "action": action,
                "source_ip": source_ip,
                "syn_recv_count": syn_recv_count,
                "block_seconds": block_seconds,
            }
        )


def run_once(
    port: int,
    threshold: int,
    block_seconds: float,
    active_blocks: dict[str, float],
    csv_path: Path,
    dry_run: bool,
    command_runner=run_command,
    time_source=time.monotonic,
) -> None:
    """Poll SYN-RECEIVED state once, block new offenders, lift expired blocks."""
    now = time_source()
    output = command_runner(["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", f":{port}", ")"])
    counts = count_by_source(parse_syn_recv_sources(output))

    for source_ip in sources_over_threshold(counts, threshold):
        if source_ip in active_blocks:
            continue
        if not dry_run:
            command_runner(block_rule(source_ip, port))
        active_blocks[source_ip] = now + block_seconds
        log_event(csv_path, "block", source_ip, counts[source_ip], block_seconds)
        print(f"blocked {source_ip}: {counts[source_ip]} half-open connections on port {port}")

    for source_ip in expired_blocks(active_blocks, now):
        if not dry_run:
            command_runner(unblock_rule(source_ip, port))
        del active_blocks[source_ip]
        log_event(csv_path, "unblock", source_ip, counts.get(source_ip, 0), block_seconds)
        print(f"unblocked {source_ip}")



        print(f"SYN Guard stopped; evidence saved to {arguments.output}")


if __name__ == "__main__":
    main()
