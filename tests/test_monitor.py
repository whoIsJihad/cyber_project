"""Tests for receiver monitoring parsers and CSV output."""

import csv

import pytest

from server.monitor import (
    CSV_FIELDS,
    append_sample,
    count_socket_lines,
    is_nginx_active,
    is_port_80_listening,
    read_load_1m,
    read_mem_available_kib,
)


def test_service_and_listener_parsing() -> None:
    assert is_nginx_active("active\n") is True
    assert is_nginx_active("inactive\n") is False
    assert is_port_80_listening("LISTEN 0 511 0.0.0.0:80 0.0.0.0:*") is True
    assert is_port_80_listening("LISTEN 0 511 0.0.0.0:22 0.0.0.0:*") is False


def test_socket_count_and_proc_parsing() -> None:
    assert count_socket_lines("0 0 192.168.150.20:80 192.168.150.99:20000\n0 0 192.168.150.20:80 192.168.150.99:20001\n") == 2
    assert count_socket_lines("") == 0
    assert read_load_1m("0.42 0.10 0.05 1/100 200\n") == 0.42
    assert read_mem_available_kib("MemTotal: 1000 kB\nMemAvailable: 500 kB\n") == 500

    with pytest.raises(ValueError, match="MemAvailable"):
        read_mem_available_kib("MemTotal: 1000 kB\n")


def test_append_sample_writes_required_csv_columns(tmp_path) -> None:
    output_path = tmp_path / "receiver-monitor.csv"
    sample = {
        "timestamp_utc": "2026-09-16T00:00:00+00:00",
        "nginx_active": True,
        "port_80_listening": True,
        "syn_recv_count": 2,
        "established_count": 1,
        "load_1m": 0.2,
        "mem_available_kib": 12345,
    }

    append_sample(output_path, sample)

    with output_path.open(newline="", encoding="utf-8") as input_file:
        rows = list(csv.DictReader(input_file))
    assert list(rows[0]) == CSV_FIELDS
    assert rows[0]["syn_recv_count"] == "2"
