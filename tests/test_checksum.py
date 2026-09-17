"""Tests for the first offline packet-building function."""

from client.checksum import internet_checksum


def test_empty_data_has_all_one_bits_checksum() -> None:
    assert internet_checksum(b"") == 0xFFFF


def test_one_complete_16_bit_word() -> None:
    assert internet_checksum(b"\x00\x01") == 0xFFFE


def test_odd_length_data_is_zero_padded_on_the_right() -> None:
    assert internet_checksum(b"\x01") == 0xFEFF


def test_all_one_bits_word_wraps_to_zero_checksum() -> None:
    assert internet_checksum(b"\xFF\xFF") == 0x0000
