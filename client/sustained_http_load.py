"""Run one fixed-concurrency HTTP workload for a measured duration."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

from client.normal_web_client import DEFAULT_URL, make_request, utc_timestamp, write_rows


def run_worker(url: str, timeout: float, deadline: float, concurrency: int) -> list[dict[str, str | int | float | bool]]:
    """Keep one HTTP worker busy until the shared deadline passes."""
    rows = []
    while time.monotonic() < deadline:
        row = make_request(url, timeout)
        row["timestamp_utc"] = utc_timestamp()
        row["concurrency"] = concurrency
        rows.append(row)
    return rows


def run_for_duration(url: str, duration: float, timeout: float, concurrency: int) -> list[dict[str, str | int | float | bool]]:
    """Run exactly ``concurrency`` workers for approximately ``duration`` seconds."""
    if duration <= 0 or timeout <= 0 or concurrency < 1:
        raise ValueError("duration and timeout must be positive and concurrency must be at least one")

    deadline = time.monotonic() + duration
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_worker, url, timeout, deadline, concurrency) for _ in range(concurrency)]

    rows = []
    for future in futures:
        rows.extend(future.result())
    rows.sort(key=lambda row: row["timestamp_utc"])
    for request_number, row in enumerate(rows, start=1):
        row["request_number"] = request_number
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure normal HTTP access for a fixed duration.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    try:
        rows = run_for_duration(arguments.url, arguments.duration, arguments.timeout, arguments.concurrency)
    except ValueError as error:
        parser.error(str(error))

    write_rows(arguments.output, rows)
    successes = sum(row["success"] is True for row in rows)
    print(f"saved {len(rows)} HTTP results; successes: {successes}/{len(rows)}")


if __name__ == "__main__":
    main()
