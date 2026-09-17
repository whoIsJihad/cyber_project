"""Build the 20-byte IPv4 header that carries the TCP header."""

from client.checksum import internet_checksum


def build_ipv4_header(
    source_ip: bytes,
    destination_ip: bytes,
    payload_length: int,
    identification: int,
    ttl: int,
) -> bytes:
    """Return a no-options IPv4 header with its checksum inserted."""
    if ttl < 0x00 or ttl > 0xFF:
        raise ValueError("ttl must fit in one byte: 0x00 through 0xFF")

    header = bytearray()

    # 0x45 means IPv4 (4) with a five-word header (5 × 4 = 20 bytes).
    header.append(0x45)

    # This is the DSCP/ECN byte. 0x00 means we request no special service and
    # do not signal Explicit Congestion Notification in this first packet.
    header.append(0x00)

    # IPv4 total length includes this 20-byte IPv4 header and its TCP payload.
    total_length = 20 + payload_length
    header.extend(total_length.to_bytes(2, "big"))

    # This value identifies fragments belonging to the same original packet.
    header.extend(identification.to_bytes(2, "big"))

    # These two bytes contain three fragmentation flags plus a 13-bit fragment
    # offset. 0x0000 means every flag is off and this packet starts at offset 0.
    header.extend((0x0000).to_bytes(2, "big"))

    # TTL is one byte chosen by the caller. 0x06 is IPv4's protocol value for
    # TCP, so a receiver knows the next 20 bytes should be read as TCP.
    header.append(ttl)
    header.append(0x06)

    # IPv4 checksum occupies bytes 10 and 11. It must be zero while the
    # checksum is being calculated, then we replace these two bytes below.
    header.extend((0x0000).to_bytes(2, "big"))

    # IPv4 addresses already arrive as their four network-order bytes.
    header.extend(source_ip)
    header.extend(destination_ip)

    checksum = internet_checksum(bytes(header))
    # Slice 10:12 selects IPv4 bytes 10 and 11, the 16-bit checksum field.
    header[10:12] = checksum.to_bytes(2, "big")

    return bytes(header)
