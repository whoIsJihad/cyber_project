"""Measure normal HTTP access to the isolated receiver and save CSV evidence."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


DEFAULT_URL = "http://192.168.150.20/"
CSV_FIELDS = ["timestamp_utc", "request_number", "concurrency", "success", "latency_ms", "http_status", "error"]


def utc_timestamp() -> str:
    """Return one unambiguous timestamp for an evidence row."""
    return datetime.now(timezone.utc).isoformat()


def make_request(url: str, timeout: float, opener=urlopen, clock=time.perf_counter) -> dict[str, str | int | float | bool]:
    """Make one ordinary HTTP request over a new TCP connection.

    ``Connection: close`` asks the receiver to close the HTTP/1.1 connection
    after this response. Closing the response locally releases the matching
    client socket before the next measured request starts.
    """
    started_at = clock()
    try:
        request = Request(url, headers={"Connection": "close"})
        response = opener(request, timeout=timeout)
        status = response.getcode()
        response.close()
        return {
            "success": 200 <= status < 400,
            "latency_ms": round((clock() - started_at) * 1000, 2),
            "http_status": status,
            "error": "",
        }
    except (URLError, TimeoutError, OSError) as error:
        return {
            "success": False,
            "latency_ms": round((clock() - started_at) * 1000, 2),
            "http_status": "",
            "error": str(error),
        }


def write_rows(csv_path: Path, rows: list[dict[str, str | int | float | bool]]) -> None:
    """Write normal-client evidence with one stable CSV header."""
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def run_requests(
    url: str,
    request_count: int,
    pause: float,
    timeout: float,
    concurrency: int = 1,
) -> list[dict[str, str | int | float | bool]]:
    """Run sequential or concurrent requests and return every result row."""
    if request_count < 1:
        raise ValueError("request count must be at least 1")
    if pause < 0 or timeout <= 0 or concurrency < 1:
        raise ValueError("pause must be non-negative and timeout must be positive")

    def run_one_request(request_number: int) -> dict[str, str | int | float | bool]:
        row = make_request(url, timeout)
        row["timestamp_utc"] = utc_timestamp()
        row["request_number"] = request_number
        row["concurrency"] = concurrency
        return row

    if concurrency == 1:
        rows = []
        for request_number in range(1, request_count + 1):
            rows.append(run_one_request(request_number))
            if request_number < request_count:
                time.sleep(pause)
        return rows

    # The executor keeps at most `concurrency` requests active. All failures
    # are converted into result rows by make_request, so one failed connection
    # does not cancel the remaining workload.
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        rows = list(executor.map(run_one_request, range(1, request_count + 1)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure ordinary HTTP access to the isolated receiver.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("results/normal-web.csv"))
    arguments = parser.parse_args()

    rows = run_requests(arguments.url, arguments.count, arguments.pause, arguments.timeout, arguments.concurrency)
    write_rows(arguments.output, rows)
    successes = sum(row["success"] is True for row in rows)
    print(f"saved {len(rows)} HTTP results to {arguments.output}; successes: {successes}/{len(rows)}")


if __name__ == "__main__":
    main()
