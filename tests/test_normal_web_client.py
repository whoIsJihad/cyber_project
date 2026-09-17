"""Tests for normal HTTP measurement without contacting a VM."""

import csv

from client.normal_web_client import CSV_FIELDS, make_request, run_requests, write_rows


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status
        self.closed = False

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self.closed = True


def test_successful_request_records_status_and_latency() -> None:
    response = FakeResponse(200)
    clock_values = iter([10.0, 10.125])
    received_request = None

    def opener(request, timeout):
        nonlocal received_request
        received_request = request
        assert timeout == 5
        return response

    row = make_request(
        "http://example.invalid/",
        5,
        opener=opener,
        clock=lambda: next(clock_values),
    )

    assert row == {"success": True, "latency_ms": 125.0, "http_status": 200, "error": ""}
    assert response.closed is True
    assert received_request.get_header("Connection") == "close"


def test_failed_request_records_error() -> None:
    clock_values = iter([10.0, 10.05])

    def failing_opener(_url: str, timeout: float):
        raise OSError("connection refused")

    row = make_request("http://example.invalid/", 5, opener=failing_opener, clock=lambda: next(clock_values))

    assert row["success"] is False
    assert row["http_status"] == ""
    assert "connection refused" in row["error"]


def test_write_rows_creates_one_header_and_all_rows(tmp_path) -> None:
    output_path = tmp_path / "results" / "normal-web.csv"
    rows = [
        {"timestamp_utc": "one", "request_number": 1, "concurrency": 1, "success": True, "latency_ms": 1.0, "http_status": 200, "error": ""},
        {"timestamp_utc": "two", "request_number": 2, "concurrency": 1, "success": False, "latency_ms": 2.0, "http_status": "", "error": "timeout"},
    ]

    write_rows(output_path, rows)

    with output_path.open(newline="", encoding="utf-8") as input_file:
        saved_rows = list(csv.DictReader(input_file))
    assert list(saved_rows[0]) == CSV_FIELDS
    assert len(saved_rows) == 2
    assert saved_rows[1]["error"] == "timeout"


def test_concurrent_requests_record_the_requested_concurrency(monkeypatch) -> None:
    def successful_request(_url: str, _timeout: float):
        return {"success": True, "latency_ms": 1.0, "http_status": 200, "error": ""}

    monkeypatch.setattr("client.normal_web_client.make_request", successful_request)
    rows = run_requests("http://example.invalid/", 6, pause=0, timeout=1, concurrency=3)

    assert len(rows) == 6
    assert [row["request_number"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert all(row["concurrency"] == 3 for row in rows)
