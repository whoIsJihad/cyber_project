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


def track_offenders(
    counts: dict[str, int], threshold: int, strikes: dict[str, int], persistence: int
) -> list[str]:
    """Update each source's consecutive over-threshold streak; return sources that just
    reached `persistence` in a row.

    A real handshake finishes within one poll interval, so a source that briefly spikes
    over the threshold (a burst of legitimate traffic, a slow but real client) drops back
    below it on the very next check and its streak resets to zero. A flood source never
    completes its handshakes, so it stays over threshold poll after poll. Requiring several
    consecutive over-threshold checks before blocking is what tells the two apart, instead
    of judging a source off a single snapshot.
    """
    over_threshold = set(sources_over_threshold(counts, threshold))
    newly_confirmed = []
    for source_ip in over_threshold:
        strikes[source_ip] = strikes.get(source_ip, 0) + 1
        if strikes[source_ip] == persistence:
            newly_confirmed.append(source_ip)
    for source_ip in list(strikes):
        if source_ip not in over_threshold:
            del strikes[source_ip]
    return newly_confirmed


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
    strikes: dict[str, int],
    persistence: int = 3,
    command_runner=run_command,
    time_source=time.monotonic,
) -> None:
    """Poll SYN-RECEIVED state once, block persistent offenders, lift expired blocks."""
    now = time_source()
    output = command_runner(["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", f":{port}", ")"])
    counts = count_by_source(parse_syn_recv_sources(output))

    for source_ip in track_offenders(counts, threshold, strikes, persistence):
        if source_ip in active_blocks:
            continue
        if not dry_run:
            command_runner(block_rule(source_ip, port))
        active_blocks[source_ip] = now + block_seconds
        log_event(csv_path, "block", source_ip, counts[source_ip], block_seconds)
        print(
            f"blocked {source_ip}: {counts[source_ip]} half-open connections on port {port} "
            f"for {persistence} consecutive checks"
        )

    for source_ip in expired_blocks(active_blocks, now):
        if not dry_run:
            command_runner(unblock_rule(source_ip, port))
        del active_blocks[source_ip]
        log_event(csv_path, "unblock", source_ip, counts.get(source_ip, 0), block_seconds)
        print(f"unblocked {source_ip}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect per-source SYN-flood pressure and apply temporary firewall blocks."
    )
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--threshold", type=int, default=5)
    parser.add_argument("--block-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path, default=Path("results/defense-events.csv"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--persistence",
        type=int,
        default=3,
        help="consecutive over-threshold checks required before a source is blocked",
    )
    arguments = parser.parse_args()
    if arguments.interval <= 0:
        raise ValueError("interval must be positive")
    if arguments.persistence < 1:
        raise ValueError("persistence must be at least 1")

    active_blocks: dict[str, float] = {}
    strikes: dict[str, int] = {}
    mode = "dry-run (no iptables changes)" if arguments.dry_run else "active blocking"
    print(
        f"SYN Guard watching port {arguments.port}: threshold {arguments.threshold} "
        f"half-open/source for {arguments.persistence} consecutive checks, "
        f"{arguments.block_seconds}s blocks, {mode}; press Ctrl+C to stop"
    )
    try:
        while True:
            run_once(
                arguments.port,
                arguments.threshold,
                arguments.block_seconds,
                active_blocks,
                arguments.output,
                arguments.dry_run,
                strikes,
                arguments.persistence,
            )
            time.sleep(arguments.interval)
    except KeyboardInterrupt:
        print(f"SYN Guard stopped; evidence saved to {arguments.output}")


if __name__ == "__main__":
    main()
