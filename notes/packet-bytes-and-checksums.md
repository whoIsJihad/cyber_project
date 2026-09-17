# Packet bytes and checksums

Our program will build one SYN frame as a sequence of bytes. This note shows
what those bytes represent. It does not send anything.

## One fixed example

We will use the same values every time while learning and testing:

| Item | Value |
|---|---:|
| Source MAC address | `02:00:00:00:00:01` |
| Destination MAC address | `02:00:00:00:00:02` |
| Source IP address | `192.0.2.10` |
| Destination IP address | `192.0.2.20` |
| Source TCP port | `40000` |
| Destination TCP port | `8080` |
| TCP sequence number | `0x12345678` |
| TCP flag | SYN |
| TCP data | none |

These are simply sample values. Fixed values help us check whether our program
always produces the correct bytes.

## The final size

Our example contains three headers:

| Header | Size | Position in the complete frame |
|---|---:|---:|
| Ethernet | 14 bytes | bytes 0 to 13 |
| IPv4 | 20 bytes | bytes 14 to 33 |
| TCP | 20 bytes | bytes 34 to 53 |

The complete frame is 54 bytes.

The IPv4 header has a field called Total Length. Its value is 40 because it
counts only the IPv4 header and TCP header. It does not count the 14-byte
Ethernet header.

## How numbers become bytes

Packet fields have fixed sizes. A TCP port is 16 bits, which is 2 bytes.

Port 8080 is hexadecimal `0x1f90`. It appears in the header as:

```text
1f 90
```

The 32-bit sequence number `0x12345678` appears as:

```text
12 34 56 78
```

The most important byte is written first. This order is called **network byte
order** or **big-endian order**.

In C, functions such as `htons` and `htonl` help place integers in network
byte order. In Python, `struct.pack` can do the same job. We will cover the
chosen language when we start coding.

## Ethernet header

The Ethernet header is 14 bytes:

| Start position | Size | Field | Bytes in our example |
|---:|---:|---|---|
| 0 | 6 bytes | Destination MAC | `02 00 00 00 00 02` |
| 6 | 6 bytes | Source MAC | `02 00 00 00 00 01` |
| 12 | 2 bytes | EtherType | `08 00` |

EtherType `08 00` means that an IPv4 packet comes next.

## IPv4 header

The IPv4 header is 20 bytes:

| Start position inside this header | Size | Field | Value |
|---:|---:|---|---|
| 0 | 1 byte | Version and header length | `0x45` |
| 1 | 1 byte | Service information | `0x00` |
| 2 | 2 bytes | Total Length | `40` |
| 4 | 2 bytes | Identification | `0x1234` |
| 6 | 2 bytes | Fragment settings | `0x4000` |
| 8 | 1 byte | Time To Live | `64` |
| 9 | 1 byte | Protocol | `6` |
| 10 | 2 bytes | IPv4 checksum | `0xa47d` |
| 12 | 4 bytes | Source IP address | `192.0.2.10` |
| 16 | 4 bytes | Destination IP address | `192.0.2.20` |

`0x45` contains two small values:

- `4` means IPv4.
- `5` means the header is five groups of 4 bytes, so it is 20 bytes long.

Protocol `6` means that the IPv4 packet contains TCP.

## TCP header

The TCP header is 20 bytes:

| Start position inside this header | Size | Field | Value |
|---:|---:|---|---|
| 0 | 2 bytes | Source port | `40000` |
| 2 | 2 bytes | Destination port | `8080` |
| 4 | 4 bytes | Sequence number | `0x12345678` |
| 8 | 4 bytes | Acknowledgment number | `0` |
| 12 | 2 bytes | Header length and flags | `0x5002` |
| 14 | 2 bytes | Window size | `64240` |
| 16 | 2 bytes | TCP checksum | `0x0c56` |
| 18 | 2 bytes | Urgent pointer | `0` |

`0x5002` contains the TCP header length and flags:

- `5` means the TCP header is five groups of 4 bytes, so it is 20 bytes long.
- `2` means the SYN flag is set.

The ACK flag is not set because this is the first message of the TCP
handshake.

## What a checksum does

A checksum is a small value calculated from a group of bytes. The receiver can
calculate it again. If the result does not match, some bytes may be damaged or
incorrect.

IPv4 and TCP use the same checksum method, but they calculate over different
bytes.

### IPv4 checksum

The IPv4 checksum covers only the 20-byte IPv4 header.

It does not include:

- the Ethernet header;
- the TCP header.

For our example, the IPv4 checksum is `0xa47d`.

### TCP checksum

The TCP checksum covers:

- the TCP header;
- any TCP data, although our SYN has no data;
- the source and destination IP addresses;
- the IP protocol number;
- the TCP length.

The IP-related values used during this calculation are called the **TCP
pseudo-header**. The pseudo-header is not added to the frame. It exists only
as input to the checksum calculation.

For our example, the TCP checksum is `0x0c56`.

## How the checksum is calculated

For now, understand the steps rather than doing them by hand:

1. Put zero in the checksum field.
2. Read the covered data in groups of 2 bytes.
3. Add those 16-bit values.
4. Add any overflow back into the result.
5. Invert all bits of the result.

We will implement and test these steps separately before building the headers.

## The complete frame

Here are all 54 bytes, separated into their three headers:

```text
Ethernet header
02 00 00 00 00 02  02 00 00 00 00 01  08 00

IPv4 header
45 00 00 28 12 34 40 00 40 06 a4 7d c0 00 02 0a c0 00 02 14

TCP header
9c 40 1f 90 12 34 56 78 00 00 00 00 50 02 fa f0 0c 56 00 00
```

Our first packet-building code should produce these exact bytes. It should not
open a socket or send them.

## Common mistakes

- Writing multi-byte numbers in the wrong byte order.
- Setting IPv4 Total Length to 54 instead of 40.
- Forgetting to set a checksum field to zero before calculating it.
- Including the Ethernet header in a checksum.
- Calculating the TCP checksum without the pseudo-header values.
- Adding the pseudo-header to the transmitted frame.
- Setting ACK when we want an initial SYN.

## Check your understanding

1. Why is the complete frame 54 bytes?
2. Why is IPv4 Total Length only 40?
3. Why is port 8080 stored as `1f 90`?
4. Which bytes are covered by the IPv4 checksum?
5. What extra values are used by the TCP checksum?
6. Is the TCP pseudo-header transmitted?

## Primary references

- [TCP header and checksum: RFC 9293, section 3.1](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.1)
- [IPv4 header: RFC 791, section 3.1](https://www.rfc-editor.org/rfc/rfc791.html#section-3.1)
- [Internet checksum: RFC 1071](https://www.rfc-editor.org/rfc/rfc1071.html)

## Next step

Next, read [Internet checksums](internet-checksums.md). It explains
the first function we will implement. We will not create a socket yet.
