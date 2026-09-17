"""Run several normal HTTP concurrency levels and save one CSV per level."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from client.normal_web_client import DEFAULT_URL, run_requests, write_rows


def run_profile(url: str, count: int, timeout: float, concurrency: int, output_path: Path) -> tuple[int, int]:
    """Run one concurrency level and return its success and failure counts."""
    rows = run_requests(url, count, pause=0, timeout=timeout, concurrency=concurrency)
    write_rows(output_path, rows)
    successes = sum(row["success"] is True for row in rows)
    return successes, len(rows) - successes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a range of legitimate HTTP concurrency levels.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--levels", type=int, nargs="+", default=[1, 5, 20, 50])
    parser.add_argument("--count", type=int, default=250, help="Requests per concurrency level.")
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    arguments = parser.parse_args()

    if arguments.count < 1 or arguments.timeout <= 0 or any(level < 1 for level in arguments.levels):
        parser.error("count, timeout, and every concurrency level must be positive")

    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    # Run all profiles together. Their combined legitimate load is identical
    # in baseline and during-flood conditions, making the comparison fair.
    with ThreadPoolExecutor(max_workers=len(arguments.levels)) as executor:
        futures = {}
        for level in arguments.levels:
            output_path = arguments.output_dir / f"{arguments.prefix}-c{level}.csv"
            future = executor.submit(run_profile, arguments.url, arguments.count, arguments.timeout, level, output_path)
            futures[level] = future

        for level in arguments.levels:
            successes, failures = futures[level].result()
            print(f"concurrency {level}: success={successes}, failed={failures}")


if __name__ == "__main__":
    main()
