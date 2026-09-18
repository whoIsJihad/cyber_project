# server/defense.py — SYN Guard

## Purpose

`defense.py` is an active countermeasure to the SYN-flood attack this project
studies. Where `server/monitor.py` only *observes* receiver health (nginx
status, socket counts, load, memory) and writes it to CSV, `defense.py`
observes the same SYN-RECEIVED socket state and *acts* on it: it detects
which source IPs are holding an abnormal number of half-open connections and
temporarily firewalls them with `iptables`.

It is explicitly **not** a replacement for `net.ipv4.tcp_syncookies` (the
kernel's built-in SYN-flood defense) — it's a separate, application-level
detector/responder built for this project so the mitigation itself can be
observed, tuned, and logged as evidence.

## The detect → block → expire loop

Everything runs through `run_once()`, called on a timer (`--interval`,
default 1s) from `main()`.

### 1. Detect half-open connections per source

```
ss -Hnt state syn-recv ( sport = :<port> )
```

`parse_syn_recv_sources()` strips each line down to the peer's IP (last
whitespace-separated column, IP:port, split on the final `:`). `count_by_source()`
then tallies how many half-open connections each source IP currently holds.

### 2. Decide who's over the line

`sources_over_threshold()` returns any source IP whose half-open count is
`>= --threshold` (default 5). This is the same idea as a rate/volume alarm:
a real client might have one or two SYNs in flight; a flood source has many.

### 3. Block new offenders

For each offending IP not already tracked in `active_blocks`:

- Runs `iptables -I INPUT -p tcp -s <ip> --dport <port> --syn -j DROP`
  (skipped under `--dry-run`) — this drops future SYNs from that IP before
  they can create more half-open state, without touching already-established
  connections.
- Records `active_blocks[ip] = now + block_seconds` (an expiry timestamp).
- Appends a `block` row to the evidence CSV and prints a status line.

### 4. Expire old blocks

`expired_blocks()` finds any tracked IP whose expiry time has passed. For
each one, the daemon removes the matching `iptables -D ...` rule, drops it
from `active_blocks`, and logs an `unblock` row. This makes blocks
self-healing — no manual firewall cleanup needed after an experiment run.

## Evidence trail

Every block/unblock decision is appended to a CSV (`--output`, default
`results/defense-events.csv`) via `log_event()`, with columns:

| column | meaning |
|---|---|
| `timestamp_utc` | when the event was logged |
| `action` | `block` or `unblock` |
| `source_ip` | the IP acted on |
| `syn_recv_count` | half-open count observed for that IP at the time |
| `block_seconds` | configured block duration |

This gives a timestamped log to correlate against `monitor.py`'s receiver
health samples when writing up results (e.g. "receiver load drops back to
normal N seconds after source X was blocked").

## Testability

`run_once()` takes `command_runner` and `time_source` as injectable
parameters (defaulting to the real `subprocess`-based `run_command` and
`time.monotonic`). `tests/test_defense.py` swaps these for fakes, so the
block/unblock/logging logic can be unit tested without a real `iptables`
binary, root privileges, or actual elapsed time. `--dry-run` provides the
same safety at the CLI level — it still detects and logs, but never mutates
firewall rules.

## CLI flags

| flag | default | meaning |
|---|---|---|
| `--interval` | `1.0` | seconds between polls |
| `--port` | `80` | protected port to watch |
| `--threshold` | `5` | half-open connections from one source that triggers a block |
| `--block-seconds` | `30.0` | how long a block stays active before it's lifted |
| `--output` | `results/defense-events.csv` | evidence CSV path |
| `--dry-run` | off | detect and log, but don't touch `iptables` |

## Key limitation to call out in the report

Blocking is purely IP-based and reactive: it doesn't reset connections
already sitting in SYN-RECEIVED for a blocked IP (the kernel's own
SYN-RECEIVED timeout still applies to those), and it can't distinguish a
spoofed-source flood (many distinct fake IPs, each under threshold) from a
genuine single-source flood — a well-known real-world weakness of
per-IP-threshold SYN-flood defenses, worth discussing alongside
`tcp_syncookies` as a comparison point.
