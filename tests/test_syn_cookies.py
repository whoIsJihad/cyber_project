"""Tests for the stateless SYN-cookie defense in server/syn_cookies.py."""

from server.syn_cookies import (
    COUNTER_SECONDS,
    MAX_SYNCOOKIE_AGE,
    MSS_TABLE,
    check_syn_cookie,
    cookie_counter,
    decode_mss,
    encode_mss,
    make_syn_cookie,
)


# Fixed secrets so every test is deterministic; production uses random ones.
SECRETS = (b"secret-key-zero-0123456789abcdef", b"secret-key-one-0123456789abcdef!")

CLIENT_IP = b"\x0A\x2A\x00\xC1"  # 10.42.0.193, a spoofed-looking source
SERVER_IP = b"\x0A\x2A\x00\x51"  # 10.42.0.81, the lab receiver
CLIENT_PORT = 40000
SERVER_PORT = 80
CLIENT_SEQ = 0xC0FFEE00


def test_encode_mss_rounds_down_to_table_entries() -> None:
    assert encode_mss(1460) == len(MSS_TABLE) - 1
    assert encode_mss(1500) == len(MSS_TABLE) - 1  # above table -> largest
    assert encode_mss(1440) == MSS_TABLE.index(1440)
    assert encode_mss(1400) == MSS_TABLE.index(1300)  # between entries -> lower
    assert encode_mss(1) == 0  # below table -> smallest


def test_decode_mss_reverses_encode_and_rejects_bad_index() -> None:
    for mss in MSS_TABLE:
        assert decode_mss(encode_mss(mss)) == mss
    assert decode_mss(len(MSS_TABLE)) is None
    assert decode_mss(-1) is None


def test_round_trip_recovers_mss_for_a_fresh_cookie() -> None:
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=1000.0
    )
    recovered = check_syn_cookie(
        cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, SECRETS, now=1000.0
    )
    assert recovered == 1460


def test_cookie_fits_in_32_bits() -> None:
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1300, SECRETS, now=1000.0
    )
    assert 0 <= cookie <= 0xFFFFFFFF


def test_cookie_still_valid_within_grace_window() -> None:
    issued_at = 1000.0
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=issued_at
    )
    # One counter tick later is still inside MAX_SYNCOOKIE_AGE.
    later = issued_at + COUNTER_SECONDS
    assert cookie_counter(later) == cookie_counter(issued_at) + 1
    recovered = check_syn_cookie(
        cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, SECRETS, now=later
    )
    assert recovered == 1460


def test_cookie_expires_after_max_age() -> None:
    issued_at = 1000.0
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=issued_at
    )
    too_late = issued_at + MAX_SYNCOOKIE_AGE * COUNTER_SECONDS + 1.0
    recovered = check_syn_cookie(
        cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, SECRETS, now=too_late
    )
    assert recovered is None


def test_tampered_connection_tuple_is_rejected() -> None:
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=1000.0
    )
    # Same cookie, but the ACK claims a different source port: must fail.
    wrong_port = check_syn_cookie(
        cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT + 1, SERVER_PORT, CLIENT_SEQ, SECRETS, now=1000.0
    )
    assert wrong_port is None
    # Different source IP: must fail.
    wrong_ip = check_syn_cookie(
        cookie, b"\x0A\x2A\x00\xC2", SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, SECRETS, now=1000.0
    )
    assert wrong_ip is None


def test_wrong_client_sequence_is_almost_always_rejected() -> None:
    # The client's SYN sequence number is folded into the cookie additively
    # (as the kernel folds `sseq`), so it round-trips only when the ACK echoes
    # the exact value used at issue time. A tiny delta can still shift onto a
    # neighbouring valid MSS index, so the honest property is statistical: an
    # attacker who cannot reproduce the client's sequence is rejected almost
    # always, exactly like a blind cookie forgery.
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=1000.0
    )
    accepted = 0
    for delta in range(1, 5001):
        if check_syn_cookie(
            cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ + delta, SECRETS, now=1000.0
        ) is not None:
            accepted += 1
    assert accepted < 100  # < ~2%: a wrong sequence does not verify


def test_different_secret_cannot_verify() -> None:
    cookie = make_syn_cookie(
        CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, 1460, SECRETS, now=1000.0
    )
    attacker_secrets = (b"guessed-key-zero-000000000000000", b"guessed-key-one-1111111111111111")
    recovered = check_syn_cookie(
        cookie, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, attacker_secrets, now=1000.0
    )
    assert recovered is None


def test_forged_random_cookie_is_almost_always_rejected() -> None:
    # Sweep many forged ISNs; a guess only "works" if it happens to land on a
    # valid MSS index, which is rare. It must be far below chance of success.
    accepted = 0
    for guess in range(0, 5000):
        if check_syn_cookie(
            guess, CLIENT_IP, SERVER_IP, CLIENT_PORT, SERVER_PORT, CLIENT_SEQ, SECRETS, now=1000.0
        ) is not None:
            accepted += 1
    assert accepted < 100  # < ~2% of blind guesses, i.e. no cheap forgery
