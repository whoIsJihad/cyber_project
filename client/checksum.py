"""Internet checksum calculation used by IPv4 and TCP headers."""


def internet_checksum(data: bytes) -> int:
    """Return the 16-bit Internet checksum for data.

    The checksum adds 16-bit words using one's-complement arithmetic, then
    returns the one's complement of that total. An odd final byte is padded
    with one zero byte for the calculation.
    """
    # Checksums read two bytes at a time. A lone final byte is treated as if
    # one zero byte followed it; that extra zero is never sent in a packet.
    if len(data) % 2 == 1:
        data += b"\x00"

    total = 0
    for index in range(0, len(data), 2):
        high_byte = data[index]
        low_byte = data[index + 1]
        # 0x100 is 256. Multiplying the first byte by it moves that byte into
        # the high half of a 16-bit word: F2 and 03 become F203.
        word = high_byte * 0x100 + low_byte
        total += word

        # 0xFFFF is the largest 16-bit value. One's-complement addition does
        # not discard overflow; it adds the carry back into the low 16 bits.
        if total > 0xFFFF:
            # 0x10000 is 65536, one larger than the 16-bit range.
            lower_16_bits = total % 0x10000
            carry = total // 0x10000
            total = lower_16_bits + carry

    # Subtracting from FFFF inverts every bit in this already-16-bit total.
    return 0xFFFF - total
