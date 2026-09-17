"""Tests for generator settings and its raw-socket sending loop."""

import pytest

from client.generator import (
    DESTINATION_IP_TEXT,
    FIRST_SOURCE_PORT,
    MAX_PACKET_COUNT,
    PORTS_PER_SOURCE_IP,
    SOURCE_IP_ADDRESSES,
    build_packet,
    packet_count_for_duration,
    send_syn_packets,
    source_identity,
    validate_settings,
)


class FakeRawSocket:
    """Records socket calls without opening a real network socket."""

    def __init__(self) -> None:
        self.options = []
        self.sent_packets = []
        self.closed = False

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def sendto(self, packet: bytes, destination: tuple[str, int]) -> None:
        self.sent_packets.append((packet, destination))

    def close(self) -> None:
        self.closed = True


class FakeSocketFactory:
    """Returns the fake socket when the sender asks to open one."""

    def __init__(self, fake_socket: FakeRawSocket) -> None:
        self.fake_socket = fake_socket

    def __call__(self, *_: object) -> FakeRawSocket:
        return self.fake_socket


def test_build_packet_returns_a_complete_syn_packet() -> None:
    packet = build_packet(0)

    assert len(packet) == 40
    assert packet[12:16] == SOURCE_IP_ADDRESSES[0].packed
    assert packet[16:20] == b"\xC0\xA8\x96\x14"
    assert packet[22:24] == b"\x00\x50"
    assert packet[33] == 0x02


def test_each_packet_uses_a_different_source_port() -> None:
    first_packet = build_packet(0)
    second_packet = build_packet(1)

    assert first_packet[20:22] == FIRST_SOURCE_PORT.to_bytes(2, "big")
    assert second_packet[20:22] == (FIRST_SOURCE_PORT + 1).to_bytes(2, "big")


def test_largest_allowed_run_ends_at_largest_tcp_port() -> None:
    last_packet = build_packet(MAX_PACKET_COUNT - 1)

    assert last_packet[20:22] == (65535).to_bytes(2, "big")


def test_source_ip_advances_after_source_ports_are_used() -> None:
    last_on_first_ip = source_identity(PORTS_PER_SOURCE_IP - 1)
    first_on_second_ip = source_identity(PORTS_PER_SOURCE_IP)

    assert last_on_first_ip == (SOURCE_IP_ADDRESSES[0].packed, 65535)
    assert first_on_second_ip == (SOURCE_IP_ADDRESSES[1].packed, FIRST_SOURCE_PORT)


def test_settings_reject_values_outside_the_allowed_range() -> None:
    with pytest.raises(ValueError, match="packet count"):
        validate_settings(MAX_PACKET_COUNT + 1, 1)

    with pytest.raises(ValueError, match="rate"):
        validate_settings(1, 0)


def test_duration_converts_to_a_bounded_packet_count() -> None:
    assert packet_count_for_duration(2.5, 4) == 10

    with pytest.raises(ValueError, match="duration"):
        packet_count_for_duration(0, 1)

    assert packet_count_for_duration(60, 1000) == 60000


def test_sender_uses_the_fixed_receiver_and_closes_the_socket() -> None:
    fake_socket = FakeRawSocket()
    waits = []

    sent_count = send_syn_packets(
        packet_count=3,
        rate=10,
        socket_factory=FakeSocketFactory(fake_socket),
        wait_function=waits.append,
    )

    assert sent_count == 3
    assert len(fake_socket.sent_packets) == 3
    assert fake_socket.sent_packets[0][1] == (DESTINATION_IP_TEXT, 0)
    assert fake_socket.closed is True
    assert waits == [0.1, 0.1]


class StopAfterThreeWaits:
    def __init__(self):
        self.calls = 0

    def __call__(self, seconds):
        self.calls += 1
        if self.calls == 3:
            raise KeyboardInterrupt


def test_continuous_sender_wraps_identities_and_closes_on_stop(monkeypatch):
    monkeypatch.setattr("client.generator.MAX_PACKET_COUNT", 2)
    fake_socket = FakeRawSocket()
    sent = send_syn_packets(None, 10, FakeSocketFactory(fake_socket), StopAfterThreeWaits())
    assert sent == 3
    assert fake_socket.closed
    assert fake_socket.sent_packets[0] == fake_socket.sent_packets[2]


def test_sigterm_requests_graceful_stop():
    from client.generator import stop_on_signal
    import signal

    with pytest.raises(KeyboardInterrupt):
        stop_on_signal(signal.SIGTERM, None)
