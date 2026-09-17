"""Sample receiver health and TCP states into a CSV evidence file."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time


CSV_FIELDS = [
    "timestamp_utc",
    "nginx_active",
    "port_80_listening",
    "syn_recv_count",
    "established_count",
    "load_1m",
    "mem_available_kib",
]


def run_command(command_parts: list[str]) -> str:
    """Run one read-only system command and return its standard output."""
    result = subprocess.run(command_parts, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{' '.join(command_parts)} failed: {result.stderr.strip()}")
    return result.stdout


def is_nginx_active(output: str) -> bool:
    return output.strip() == "active"


def is_port_80_listening(output: str) -> bool:
    return any(":80" in line for line in output.splitlines())


def count_socket_lines(output: str) -> int:
    return len([line for line in output.splitlines() if line.strip()])


def read_load_1m(output: str) -> float:
    return float(output.split()[0])


def read_mem_available_kib(output: str) -> int:
    for line in output.splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    raise ValueError("MemAvailable was not found in meminfo")


def collect_sample(command_runner=run_command, loadavg_path=Path("/proc/loadavg"), meminfo_path=Path("/proc/meminfo")) -> dict[str, str | int | float | bool]:
    """Collect one receiver-health sample without changing system state."""
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "nginx_active": is_nginx_active(command_runner(["systemctl", "is-active", "nginx"])),
        "port_80_listening": is_port_80_listening(command_runner(["ss", "-H", "-ltn"])),
        "syn_recv_count": count_socket_lines(command_runner(["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", ":80", ")"])),
        "established_count": count_socket_lines(command_runner(["ss", "-Hnt", "state", "established", "(", "sport", "=", ":80", ")"])),
        "load_1m": read_load_1m(loadavg_path.read_text(encoding="utf-8")),
        "mem_available_kib": read_mem_available_kib(meminfo_path.read_text(encoding="utf-8")),
    }


def append_sample(csv_path: Path, sample: dict[str, str | int | float | bool]) -> None:
    """Append one complete monitor sample to a CSV file."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(sample)


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor isolated receiver health and TCP state.")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("results/receiver-monitor.csv"))
    arguments = parser.parse_args()
    if arguments.interval <= 0:
        raise ValueError("interval must be positive")

    print(f"sampling every {arguments.interval} seconds; press Ctrl+C to stop")
    try:
        while True:
            append_sample(arguments.output, collect_sample())
            time.sleep(arguments.interval)
    except KeyboardInterrupt:
        print(f"monitor stopped; evidence saved to {arguments.output}")


if __name__ == "__main__":
    main()
