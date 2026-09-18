"""Tests for the custom SYN-flood detector and firewall-blocking daemon."""

import csv

from server.defense import (
    CSV_FIELDS,
    block_rule,
    count_by_source,
    expired_blocks,
    log_event,
    parse_syn_recv_sources,
    run_once,
    sources_over_threshold,
    unblock_rule,
)


SAMPLE_OUTPUT = (
    "0 0 192.168.150.20:80 192.168.150.99:20000\n"
    "0 0 192.168.150.20:80 192.168.150.99:20001\n"
    "0 0 192.168.150.20:80 192.168.150.99:20002\n"
    "0 0 192.168.150.20:80 192.168.150.42:30000\n"
)


def test_parse_syn_recv_sources() -> None:
    assert parse_syn_recv_sources(SAMPLE_OUTPUT) == [
        "192.168.150.99",
        "192.168.150.99",
        "192.168.150.99",
        "192.168.150.42",
    ]
    assert parse_syn_recv_sources("") == []


def test_count_by_source() -> None:
    sources = parse_syn_recv_sources(SAMPLE_OUTPUT)
    assert count_by_source(sources) == {"192.168.150.99": 3, "192.168.150.42": 1}


def test_sources_over_threshold_includes_equal_and_excludes_below() -> None:
    counts = {"192.168.150.99": 3, "192.168.150.42": 1}
    assert sources_over_threshold(counts, 3) == ["192.168.150.99"]
    assert sources_over_threshold(counts, 4) == []


def test_block_and_unblock_rule_shape() -> None:
    assert block_rule("192.168.150.99", 80) == [
        "iptables", "-I", "INPUT", "-p", "tcp", "-s", "192.168.150.99", "--dport", "80", "--syn", "-j", "DROP",
    ]
    assert unblock_rule("192.168.150.99", 80) == [
        "iptables", "-D", "INPUT", "-p", "tcp", "-s", "192.168.150.99", "--dport", "80", "--syn", "-j", "DROP",
    ]


def test_expired_blocks() -> None:
    active_blocks = {"192.168.150.99": 10.0, "192.168.150.42": 20.0}
    assert expired_blocks(active_blocks, 15.0) == ["192.168.150.99"]
    assert expired_blocks(active_blocks, 25.0) == ["192.168.150.99", "192.168.150.42"]
    assert expired_blocks(active_blocks, 5.0) == []


def test_log_event_writes_csv_header_and_row(tmp_path) -> None:
    output_path = tmp_path / "defense-events.csv"

    log_event(output_path, "block", "192.168.150.99", 5, 30.0)

    with output_path.open(newline="", encoding="utf-8") as input_file:
        rows = list(csv.DictReader(input_file))
    assert list(rows[0]) == CSV_FIELDS
    assert rows[0]["action"] == "block"
    assert rows[0]["source_ip"] == "192.168.150.99"
    assert rows[0]["syn_recv_count"] == "5"


def test_run_once_blocks_new_source_and_skips_repeat_blocks(tmp_path) -> None:
    calls = []

    def fake_runner(command_parts):
        calls.append(command_parts)
        return SAMPLE_OUTPUT

    active_blocks: dict[str, float] = {}
    csv_path = tmp_path / "events.csv"

    run_once(80, 3, 30.0, active_blocks, csv_path, dry_run=False, command_runner=fake_runner, time_source=lambda: 0.0)
    assert active_blocks == {"192.168.150.99": 30.0}
    assert calls == [
        ["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", ":80", ")"],
        block_rule("192.168.150.99", 80),
    ]

    calls.clear()
    run_once(80, 3, 30.0, active_blocks, csv_path, dry_run=False, command_runner=fake_runner, time_source=lambda: 1.0)
    assert calls == [["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", ":80", ")"]]


def test_run_once_dry_run_never_calls_iptables(tmp_path) -> None:
    calls = []

    def fake_runner(command_parts):
        calls.append(command_parts)
        return SAMPLE_OUTPUT

    active_blocks: dict[str, float] = {}
    run_once(80, 3, 30.0, active_blocks, tmp_path / "events.csv", dry_run=True, command_runner=fake_runner, time_source=lambda: 0.0)

    assert active_blocks == {"192.168.150.99": 30.0}
    assert all(call[0] == "ss" for call in calls)


def test_run_once_unblocks_after_expiry(tmp_path) -> None:
    calls = []

    def fake_runner(command_parts):
        calls.append(command_parts)
        return ""

    active_blocks = {"192.168.150.99": 10.0}
    run_once(80, 3, 30.0, active_blocks, tmp_path / "events.csv", dry_run=False, command_runner=fake_runner, time_source=lambda: 10.0)

    assert active_blocks == {}
    assert calls == [
        ["ss", "-Hnt", "state", "syn-recv", "(", "sport", "=", ":80", ")"],
        unblock_rule("192.168.150.99", 80),
    ]
