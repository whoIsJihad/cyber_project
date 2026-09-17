"""Build the 20-byte TCP header for the lab's first SYN packet."""

from client.checksum import internet_checksum


def build_tcp_syn_header(
    source_port: int,
    destination_port: int,
    sequence_number: int,
    window_size: int,
) -> bytes:
    """Return a TCP header with SYN set and the checksum left as zero.

    The checksum stays at zero in this first step. We will calculate it only
    after building the pseudo-header used by TCP checksums.
    """
    header = bytearray()

    # TCP stores ports as two bytes, most-significant byte first.
    header.extend(source_port.to_bytes(2, "big"))
    header.extend(destination_port.to_bytes(2, "big"))

    # A TCP sequence number occupies four bytes. We choose the test value
    # outside this function so tests can inspect its exact bytes.
    header.extend(sequence_number.to_bytes(4, "big"))

    # The first packet has not received anything yet, so it acknowledges 0.
    header.extend((0).to_bytes(4, "big"))

    # 0x50 means: header length 5 groups of four bytes = 20 bytes.
    # Its low four bits keep the reserved bits and NS control bit clear.
    # 0x02 is binary 00000010. Its SYN flag bit is on; FIN, RST, PSH, ACK,
    # URG, ECE, and CWR are off.
    header.append(0x50)
    header.append(0x02)

    # The window size is supplied by the caller so it stays visible in tests.
    header.extend(window_size.to_bytes(2, "big"))

    # TCP needs its checksum, but we leave it zero until the pseudo-header
    # exists. The next component will calculate and insert the real value.
    header.extend((0).to_bytes(2, "big"))

    # SYN packets do not use the urgent pointer, so it is zero.
    header.extend((0).to_bytes(2, "big"))

    return bytes(header)


def build_tcp_pseudo_header(
    source_ip: bytes,
    destination_ip: bytes,
    tcp_length: int,
) -> bytes:
    """Return the 12 extra bytes TCP uses only for checksum calculation."""
    pseudo_header = bytearray()

    # TCP's checksum includes both IPv4 addresses, but they are not copied
    # into the real TCP header.
    pseudo_header.extend(source_ip)
    pseudo_header.extend(destination_ip)

    # This zero byte is required by the IPv4/TCP checksum format.
    pseudo_header.append(0x00)

    # 0x06 is the IPv4 protocol number for TCP. It must match the Protocol
    # byte that we later place in the real IPv4 header.
    pseudo_header.append(0x06)

    # The checksum needs the length of the real TCP header plus any payload.
    pseudo_header.extend(tcp_length.to_bytes(2, "big"))

    return bytes(pseudo_header)


def add_tcp_checksum(
    tcp_header: bytes,
    source_ip: bytes,
    destination_ip: bytes,
) -> bytes:
    """Return a copy of tcp_header with its calculated checksum inserted."""
    pseudo_header = build_tcp_pseudo_header(
        source_ip,
        destination_ip,
        len(tcp_header),
    )
    checksum = internet_checksum(pseudo_header + tcp_header)

    complete_header = bytearray(tcp_header)

    # TCP puts its 16-bit checksum in bytes 16 and 17 of the 20-byte base
    # header. Slice 16:18 means “start at 16 and stop before 18”.
    complete_header[16:18] = checksum.to_bytes(2, "big")

    return bytes(complete_header)
