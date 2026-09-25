# server/syn_cookies.py — Stateless SYN Cookies

## Purpose

`syn_cookies.py` reimplements the defense that Linux ships in the kernel and
turns on with `sysctl net.ipv4.tcp_syncookies=1`. It is the counterpart to
`server/defense.py`:

| | `defense.py` (SYN Guard) | `syn_cookies.py` (SYN cookies) |
|---|---|---|
| Strategy | detect and block noisy sources | never store half-open state at all |
| State kept | one timer per blocked IP | **none** |
| Acts by | inserting `iptables` DROP rules | encoding state into the SYN-ACK ISN |
| Kernel analogue | none (application-level) | `net/ipv4/syncookies.c` |

A SYN flood works by making the server hold thousands of half-open
(`SYN-RECEIVED`) connections until its backlog queue overflows and real
clients can no longer connect. SYN cookies remove the thing the attack targets:
if there is no per-connection state to exhaust, there is nothing to flood.

## The core idea

A normal handshake makes the server remember the connection between the SYN and
the ACK:

```
client  --SYN(seq=C)-->  server   (server allocates a half-open entry)
client  <--SYN-ACK(seq=S, ack=C+1)--  server
client  --ACK(seq=C+1, ack=S+1)-->  server   (entry promoted to a socket)
```

With SYN cookies the server allocates nothing. It chooses its ISN `S` to *be* a
cookie — a value it can recompute later — and forgets the connection:

```
client  --SYN(seq=C)-->  server   (NO state stored)
client  <--SYN-ACK(seq=cookie, ack=C+1)--  server
client  --ACK(ack=cookie+1)-->  server   (server recomputes & verifies cookie)
```

Because the client must echo `cookie + 1` in its ACK, only a client that
actually received the SYN-ACK can complete the handshake. A spoofed SYN never
sends a matching ACK, so it costs the server exactly one SYN-ACK and zero
memory.

## What goes into the 32 bits

A TCP sequence number is only 32 bits, so the cookie has to be small. Layout
(`make_syn_cookie()`):

```
 bits 31..24 | bits 23..0
 timestamp   | keyed hash of the connection, mixed with the MSS index
 (for expiry)| (for authenticity + to remember the client's MSS)
```

- **Timestamp (top 8 bits)** — a coarse counter that advances once per minute
  (`cookie_counter()`, mirroring the kernel's `tcp_cookie_time()`). On
  verification the server rejects any cookie older than `MAX_SYNCOOKIE_AGE`
  ticks (2, a ~2-minute window — longer than any real round trip, short enough
  that captured cookies go stale quickly).
- **Keyed hash (low 24 bits)** — `cookie_hash()` is an HMAC over the
  connection's four-tuple (source IP/port, dest IP/port) and the counter, keyed
  with a per-process secret. Without the secret an attacker cannot predict it,
  so forged ACKs almost never verify. Two secrets/domains are used exactly as
  the kernel keeps `syncookie_secret[2]`.
- **MSS index** — the client's Maximum Segment Size can't be stored (no state!),
  so it is squeezed into a few bits as an index into a small fixed table
  (`MSS_TABLE`), and recovered on the ACK. `encode_mss()` rounds down to the
  nearest table entry; `decode_mss()` reverses it.

## Encode → verify

`make_syn_cookie()` (kernel `secure_tcp_syn_cookie`):

```
identity = hash(tuple, counter=0, secret0)      # time-independent identity
timed    = hash(tuple, counter,   secret1)      # ages out over time
cookie   = identity + client_seq + (counter << 24) + ((timed + mss_index) & 0xFFFFFF)
```

`check_syn_cookie()` (kernel `check_tcp_syn_cookie`) undoes it:

1. Strip `identity` and `client_seq`.
2. Read the counter from the top byte; if it is `>= MAX_SYNCOOKIE_AGE` ticks
   old, reject.
3. Recompute `timed` for the counter the cookie claims and subtract it.
4. What remains is the MSS index. If it maps to a real table entry, the cookie
   is authentic and we return the MSS; otherwise reject.

## How to run the demonstration

```bash
python3 -m server.syn_cookies --connections 1000
```

It fabricates many distinct spoofed-looking SYNs (as the flood does), answers
each with a cookie, verifies the matching ACK, and prints:

- legitimate ACKs accepted (all of them),
- a forged cookie rejected,
- an expired cookie rejected,
- **half-open entries stored: 0** — unchanged no matter how many SYNs arrive.

That last line is the whole point, and the contrast to graph against the
`syn_recv_count` column that `server/monitor.py` records during an undefended
flood.

## Limitations (worth stating in the write-up)

- **Not a drop-in for the lab's nginx path.** On a real Linux server the kernel
  already owns the TCP stack on port 80, so this userspace model can't
  intercept the flood in place — the *real* kernel cookies (your "protected"
  trial's `net.ipv4.tcp_syncookies=1`) are what actually defend nginx. This
  file exists to show, test, and explain the exact mechanism.
- **TCP options are lost.** Only the MSS survives (a few bits); window scaling,
  SACK, and timestamps can't be encoded, so cookie-built connections use
  conservative defaults. This is why kernels use cookies only when the backlog
  overflows, not for every connection.
- **Weak sequence binding by design.** The client's sequence number is folded in
  additively, so its authentication strength comes from the 24-bit keyed hash,
  not the sequence number — see `test_wrong_client_sequence_is_almost_always_rejected`.

## Where the tests are

`tests/test_syn_cookies.py`: MSS encode/decode round-trips, a fresh-cookie
round-trip, the grace window vs. expiry, tampered four-tuples, wrong secrets,
and blind-forgery/wrong-sequence rejection rates. All use fixed secrets so they
are deterministic.
