# Enabling the SYN-Cookie Defense

This note explains **what the SYN-cookie defense is**, **how to turn it on** for
the real server (nginx on port 80), and **how to run the project's own
reimplementation** for demonstration. For the full mechanism (how the 32-bit
cookie is built and verified) see [SYN_COOKIES_EXPLAINED.md](SYN_COOKIES_EXPLAINED.md).

## What it is, in one paragraph

A SYN flood fills the server's backlog of half-open (`SYN-RECEIVED`)
connections until legitimate clients can no longer get in. SYN cookies defeat
this by refusing to store half-open state at all: the server encodes everything
it needs to rebuild the connection into the initial sequence number of the
SYN-ACK it sends back (the "cookie"), and forgets the connection. Only a client
that truly received the SYN-ACK can echo the cookie in its final ACK, so a
spoofed SYN costs the server one packet and zero memory.

On Linux this runs **in the kernel** and is controlled by one sysctl:
`net.ipv4.tcp_syncookies`.

## Part 1 — Enable the real kernel defense (this is what protects nginx)

### 1. Check the current setting
```bash
sysctl net.ipv4.tcp_syncookies
```
Values: `0` = off, `1` = **on only when the SYN backlog overflows** (the normal,
recommended mode), `2` = always on. Most distributions ship with `1`.

### 2. Turn it on for the current session
```bash
sudo sysctl -w net.ipv4.tcp_syncookies=1
```
This takes effect immediately and lasts until reboot. For the experiment's
"unprotected" trial you disable it the same way with `=0`.

### 3. Make it persist across reboots (optional)
```bash
echo 'net.ipv4.tcp_syncookies = 1' | sudo tee /etc/sysctl.d/99-syncookies.conf
sudo sysctl --system
```

### 4. Confirm cookies actually fired during an attack
While a flood is running against nginx, cookies show up in the kernel's TCP
counters:
```bash
nstat -az | grep -Ei 'SyncookiesSent|SyncookiesRecv|SyncookiesFailed|ListenDrops|ListenOverflows'
```
- `TcpExtSyncookiesSent` rising = the server hit backlog overflow and started
  answering with cookies instead of dropping SYNs.
- `TcpExtSyncookiesRecv` rising = real clients completed cookie handshakes.
- `TcpExtListenDrops` / `TcpExtListenOverflows` staying flat while
  `SyncookiesSent` climbs = the flood arrived and was absorbed without dropping
  legitimate connections.

This is the evidence to capture for the "protected" trial: take `nstat -az`
before and after, and diff the counters.

## Part 2 — Run the project's reimplementation (for the write-up / demo)

`server/syn_cookies.py` reimplements the kernel's exact encode/verify arithmetic
in plain Python so the mechanism can be read, unit-tested, and demonstrated. It
does **not** replace the kernel on port 80 (the kernel owns that TCP stack); it
is the teaching/evidence artifact that sits beside the real switch above.

Demonstrate it answering a flood of spoofed SYNs with zero stored state:
```bash
python3 -m server.syn_cookies --connections 1000
```
Expected output ends with:
```
  legitimate ACKs accepted : 1000/1000
  forged cookie rejected   : True
  expired cookie rejected  : True
  half-open entries stored : 0  <- unchanged by the flood
```

Run its unit tests:
```bash
python3 -m pytest tests/test_syn_cookies.py -q      # or: python3 -m unittest
```

## When to use which defense

This project ships two countermeasures; they are complementary:

| | `server/syn_cookies.py` / kernel `tcp_syncookies` | `server/defense.py` (SYN Guard) |
|---|---|---|
| Approach | store **no** half-open state | detect noisy source IPs and block them |
| Blocks legitimate users? | **No** | **Yes, as a side effect** — see below |
| Best against | spoofed-source floods (many fake IPs) | a few real, high-volume sources |

**Important caveat about `defense.py`:** because it reacts by inserting an
`iptables` DROP rule per offending *source IP*, it will also block a legitimate
user whose address happens to be (or is spoofed as) one it flags, and it cannot
help against a widely-distributed/spoofed flood without blocking large swaths of
addresses. SYN cookies have no such collateral damage, which is why they are the
primary defense and `defense.py` is a secondary, tunable detector. This trade-off
is discussed in the report.
