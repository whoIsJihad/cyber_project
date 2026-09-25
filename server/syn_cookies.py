"""A stateless SYN-cookie defense, modelled on Linux's net/ipv4/syncookies.c.

Where server/defense.py *reacts* to a flood by counting half-open connections
per source and firewalling the noisy ones, SYN cookies take the opposite
approach: they never let a half-open queue build up in the first place. When
the SYN backlog would overflow, the server refuses to store any per-connection
state. Instead it encodes everything it needs to rebuild the connection into
the 32-bit initial sequence number of the SYN-ACK it sends back -- the
"cookie". A legitimate client echoes that number (plus one) in its final ACK,
so the server can recompute the cookie, confirm it made it, recover the
client's chosen MSS, and only then build the real socket. A spoofed SYN never
completes the handshake, so it costs the server nothing but one SYN-ACK.

This module reimplements the kernel's exact encode/verify arithmetic in plain,
testable Python. On real Linux this same idea runs in the kernel and is turned
on with `sysctl net.ipv4.tcp_syncookies=1`; this file exists so the mechanism
can be read, unit-tested, and demonstrated as evidence alongside defense.py.

Kernel reference (function names below mirror it):
    secure_tcp_syn_cookie()  -> make_syn_cookie()
    check_tcp_syn_cookie()   -> check_syn_cookie()
    cookie_hash()            -> cookie_hash()
"""

import argparse
import hmac
import os
import struct
import time


# The kernel packs the client's MSS into the cookie using only a few bits, by
# storing an *index* into a fixed table rather than the MSS itself. Modern
# Linux uses these four values (include/net/tcp.h, msstab). encode_mss() rounds
# a requested MSS down to the nearest table entry; decode_mss() reverses it.
MSS_TABLE = (536, 1300, 1440, 1460)

# COOKIE_BITS is how many low bits carry the per-connection hash + MSS data.
# The top 8 bits (32 - 24) carry a coarse timestamp so old cookies expire.
COOKIE_BITS = 24
COOKIE_MASK = (1 << COOKIE_BITS) - 1
# The timestamp is masked to the 8 bits left above COOKIE_BITS.
COUNTER_MASK = 0xFFFFFFFF >> COOKIE_BITS
# A cookie is accepted only if it was issued within this many counter ticks of
# now. Linux uses 2; with a 60-second tick that is a ~2-minute grace window,
# comfortably longer than any real client's SYN -> ACK round trip.
MAX_SYNCOOKIE_AGE = 2
# The counter advances one step per minute, exactly like tcp_cookie_time().
COUNTER_SECONDS = 60

# Every value is kept inside 32 bits, the width of a TCP sequence number.
U32_MASK = 0xFFFFFFFF


def generate_secrets() -> tuple[bytes, bytes]:
    """Return two random secret keys, one per hash domain (like the kernel).

    The kernel keeps `syncookie_secret[2]`. The secrets are what stop an
    attacker from forging a valid cookie: without them, the hashes below are
    unpredictable, so a guessed ACK almost never verifies.
    """
    return os.urandom(32), os.urandom(32)


def cookie_hash(
    source_ip: bytes,
    destination_ip: bytes,
    source_port: int,
    destination_port: int,
    counter: int,
    domain: int,
    secrets: tuple[bytes, bytes],
) -> int:
    """Return a 32-bit keyed hash binding a cookie to one connection tuple.

    `domain` (0 or 1) selects which secret key is used, mirroring the kernel's
    two `cookie_hash()` calls: one that fixes the connection identity and one
    that also folds in the time counter. Any change to the four-tuple, the
    counter, or the secret produces an unrelated result.
    """
    # Pack the connection identity plus the counter into a fixed byte string so
    # the same inputs always hash identically. Ports and counter are network
    # order for reproducibility; the IPs already arrive as four bytes each.
    message = (
        source_ip
        + destination_ip
        + struct.pack("!HHI", source_port, destination_port, counter & U32_MASK)
    )
    digest = hmac.new(secrets[domain], message, "sha256").digest()
    # Fold the digest down to the 32 bits a sequence number can hold.
    return int.from_bytes(digest[:4], "big")


def encode_mss(mss: int) -> int:
    """Return the MSS_TABLE index whose value is the largest not exceeding mss.

    Very small or unknown MSS values fall back to index 0 (the smallest entry),
    exactly as the kernel does, so decode_mss() always yields a safe MSS.
    """
    for index in range(len(MSS_TABLE) - 1, 0, -1):
        if mss >= MSS_TABLE[index]:
            return index
    return 0


def decode_mss(index: int) -> int | None:
    """Return the MSS for a table index, or None if the index is out of range.

    An out-of-range index means the recovered `data` field was not one we could
    have produced, i.e. the cookie is forged or corrupt.
    """
    if 0 <= index < len(MSS_TABLE):
        return MSS_TABLE[index]
    return None


def cookie_counter(now: float) -> int:
    """Return the coarse minute counter used to age cookies (tcp_cookie_time)."""
    return int(now // COUNTER_SECONDS)


def make_syn_cookie(
    source_ip: bytes,
    destination_ip: bytes,
    source_port: int,
    destination_port: int,
    client_sequence: int,
    mss: int,
    secrets: tuple[bytes, bytes],
    now: float | None = None,
) -> int:
    """Return the SYN-ACK initial sequence number (the cookie) for one SYN.

    This is secure_tcp_syn_cookie(): the server sends this value as its ISN and
    then forgets the connection entirely. Layout of the 32-bit result:

        bits 31..24  coarse timestamp counter (for expiry)
        bits 23..0   per-connection hash mixed with the MSS index (for identity)

    The client's own SYN sequence number is added in so the cookie also tracks
    which byte stream the client started, just as the kernel does.
    """
    if now is None:
        now = time.time()
    counter = cookie_counter(now)

    # First hash fixes the connection's identity, independent of time.
    identity_hash = cookie_hash(
        source_ip, destination_ip, source_port, destination_port, 0, 0, secrets
    )
    # Second hash is time-dependent, so a cookie only verifies for a while.
    timed_hash = cookie_hash(
        source_ip, destination_ip, source_port, destination_port, counter, 1, secrets
    )
    data = encode_mss(mss)

    cookie = (
        identity_hash
        + client_sequence
        + (counter << COOKIE_BITS)
        + ((timed_hash + data) & COOKIE_MASK)
    )
    return cookie & U32_MASK


def check_syn_cookie(
    cookie: int,
    source_ip: bytes,
    destination_ip: bytes,
    source_port: int,
    destination_port: int,
    client_sequence: int,
    secrets: tuple[bytes, bytes],
    now: float | None = None,
) -> int | None:
    """Return the encoded MSS if the cookie is valid and fresh, else None.

    This is check_tcp_syn_cookie(). The server receives it as (ACK number - 1)
    in the client's final ACK. It undoes make_syn_cookie() step by step: strip
    the identity hash and the client's sequence number, read the timestamp off
    the top byte, reject anything too old, then recompute the time-dependent
    hash for the exact counter the cookie claims and recover the MSS index. A
    forged cookie almost never lands on a valid MSS index, so it is rejected.
    """
    if now is None:
        now = time.time()
    counter = cookie_counter(now)

    identity_hash = cookie_hash(
        source_ip, destination_ip, source_port, destination_port, 0, 0, secrets
    )
    # Remove the time-independent parts. What remains is
    # (counter << 24) + ((timed_hash + data) & COOKIE_MASK), modulo 2**32.
    remainder = (cookie - identity_hash - client_sequence) & U32_MASK

    # The top 8 bits are the counter value at issue time. How many ticks ago?
    issued_counter = remainder >> COOKIE_BITS
    age = (counter - issued_counter) & COUNTER_MASK
    if age >= MAX_SYNCOOKIE_AGE:
        return None

    # Recompute the time-dependent hash for the counter this cookie was issued
    # under (now minus its age), then peel it off to reveal the MSS index.
    timed_hash = cookie_hash(
        source_ip,
        destination_ip,
        source_port,
        destination_port,
        counter - age,
        1,
        secrets,
    )
    data = (remainder - timed_hash) & COOKIE_MASK
    return decode_mss(data)


def _demonstrate(connections: int) -> None:
    """Print a round-trip walkthrough proving the server stores no state."""
    secrets = generate_secrets()
    server_ip = b"\x0A\x2A\x00\x51"  # 10.42.0.81, the lab receiver
    server_port = 80
    stored_half_open_entries = 0  # the whole point: this never grows

    print(
        f"SYN-cookie defense: answering {connections} SYN(s) statelessly "
        f"(secrets generated this run; no half-open queue kept)\n"
    )

    accepted = 0
    for index in range(connections):
        # Fabricate one distinct spoofed-looking source, as a flood would.
        source_ip = bytes((10, 42, 0, 193 + (index % 62)))
        source_port = 1024 + (index % 64000)
        client_sequence = (0xC0FFEE00 + index) & U32_MASK
        client_mss = 1460

        # --- server sees the SYN, replies with a cookie, keeps nothing ---
        cookie = make_syn_cookie(
            source_ip,
            server_ip,
            source_port,
            server_port,
            client_sequence,
            client_mss,
            secrets,
        )
        # stored_half_open_entries deliberately stays 0 here.

        # --- a real client would ACK with (cookie + 1); verify that ACK ---
        recovered_mss = check_syn_cookie(
            cookie,
            source_ip,
            server_ip,
            source_port,
            server_port,
            client_sequence,
            secrets,
        )
        if recovered_mss is not None:
            accepted += 1

        if index == 0:
            source_text = ".".join(str(b) for b in source_ip)
            print(
                f"  example: SYN from {source_text}:{source_port} "
                f"-> SYN-ACK ISN (cookie) = {cookie} (0x{cookie:08X})\n"
                f"           client ACK ({cookie} + 1) verifies, "
                f"recovered MSS = {recovered_mss}"
            )

    # Show the two ways a bad ACK is rejected: forged cookie, and stale cookie.
    forged = check_syn_cookie(
        0xDEADBEEF, b"\x0A\x2A\x00\xC1", server_ip, 4444, server_port, 1, secrets
    )
    stale = check_syn_cookie(
        make_syn_cookie(
            b"\x0A\x2A\x00\xC1", server_ip, 4444, server_port, 1, 1460, secrets, now=0.0
        ),
        b"\x0A\x2A\x00\xC1",
        server_ip,
        4444,
        server_port,
        1,
        secrets,
        now=MAX_SYNCOOKIE_AGE * COUNTER_SECONDS + 1.0,
    )

    print(
        f"\n  legitimate ACKs accepted : {accepted}/{connections}"
        f"\n  forged cookie rejected   : {forged is None}"
        f"\n  expired cookie rejected  : {stale is None}"
        f"\n  half-open entries stored : {stored_half_open_entries}  "
        f"<- unchanged by the flood"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demonstrate the stateless SYN-cookie handshake defense."
    )
    parser.add_argument(
        "--connections",
        type=int,
        default=5,
        help="how many SYNs to answer in the demonstration (default 5)",
    )
    arguments = parser.parse_args()
    if arguments.connections < 1:
        raise ValueError("connections must be at least 1")
    _demonstrate(arguments.connections)


if __name__ == "__main__":
    main()
