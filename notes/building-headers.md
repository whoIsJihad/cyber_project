# Building headers

The TCP checksum creates a dependency between TCP and IP. The checksum is
stored in the TCP header, but its calculation uses the source and destination
IP addresses.

This does not make it an IP checksum. It is still a TCP field. TCP uses a few
IP values to make sure the segment belongs to the correct endpoints.

## Layer order and coding order are different

The final frame contains these headers in this order:

1. Ethernet header
2. IPv4 header
3. TCP header

Our program does not need to finish them in that order. It needs to build each
header only after the values used by that header are known.

The source and destination IP addresses are a good example. We can choose
those addresses before building the IPv4 header. Once we know them, we can
also use them to calculate the TCP checksum.

## What the TCP checksum needs

For our first SYN, the TCP checksum uses:

- source IP address;
- destination IP address;
- protocol number 6, which means TCP;
- TCP length;
- TCP header with its checksum field set to zero;
- TCP data, if there is any.

Our first SYN has no data and no TCP options. Its TCP length is 20 bytes.

The two IP addresses, protocol number, and TCP length form a temporary
12-byte structure called the **TCP pseudo-header**. It is used only during the
checksum calculation. It is not added to the transmitted frame.

## What the IPv4 checksum needs

The IPv4 checksum is calculated separately. It covers only the IPv4 header.
It does not cover the TCP header.

Before calculating it, we fill the IPv4 header fields and put zero in the IPv4
checksum field. We calculate the checksum over those 20 header bytes and put
the result back into the checksum field.

The IPv4 Total Length field is 40 because the IPv4 header and TCP header are
20 bytes each. That field describes their combined size. It does not mean the
TCP header is included in the IPv4 checksum.

## A practical construction order

### 1. Choose the field values

Choose the MAC addresses, IP addresses, ports, TCP sequence number, TCP flags,
and other header values.

At this point, they are ordinary values held by the program. We have not
assembled the final frame.

### 2. Build the unfinished TCP header

Write the TCP fields into a 20-byte header. Put zero in the TCP checksum field.

### 3. Build the temporary pseudo-header

Write the source IP, destination IP, protocol number, and TCP length into the
12-byte pseudo-header.

### 4. Finish the TCP header

Calculate the checksum over the pseudo-header and unfinished TCP header. Put
the result into the TCP checksum field.

The pseudo-header is no longer needed after this calculation.

### 5. Build the unfinished IPv4 header

Write the IPv4 fields into a 20-byte header. Set Total Length to 40 and put
zero in the IPv4 checksum field.

### 6. Finish the IPv4 header

Calculate the checksum over the 20-byte IPv4 header. Put the result into the
IPv4 checksum field.

### 7. Build the Ethernet header

Write the destination MAC, source MAC, and EtherType into a 14-byte header.
EtherType `0x0800` means IPv4.

### 8. Assemble the frame

Combine the finished headers in transmitted order:

1. 14-byte Ethernet header
2. 20-byte IPv4 header
3. 20-byte TCP header

The result is the 54-byte frame from Note 2.

## Values and bytes are not the same thing

An IP address can first exist as a value in the program:

```text
192.0.2.10
```

When serialized, that address becomes four bytes:

```text
c0 00 02 0a
```

The TCP checksum needs the IP address value. It does not need a completed IPv4
header. We only need to encode that value correctly in the pseudo-header.

## What depends on what

| Result | Required input |
|---|---|
| Unfinished TCP header | Ports, sequence number, flags, window |
| TCP pseudo-header | IP addresses, protocol number, TCP length |
| Finished TCP header | Unfinished TCP header and pseudo-header |
| Unfinished IPv4 header | IPv4 fields and total length |
| Finished IPv4 header | Unfinished IPv4 header |
| Ethernet header | MAC addresses and EtherType |
| Final frame | All three finished headers |

## What we will test

Using the fixed example from Note 2, our tests should confirm:

- the unfinished TCP header has a zero checksum;
- the pseudo-header is exactly 12 bytes;
- the TCP checksum is `0x0c56`;
- the unfinished IPv4 header has a zero checksum;
- the IPv4 checksum is `0xa47d`;
- the pseudo-header is absent from the final frame;
- the final frame is exactly 54 bytes;
- checking each completed checksum input produces zero.

All of this can be tested without opening a socket.

## The main point

The TCP checksum is a TCP field that depends on a few IP values. We calculate
it after choosing the IP addresses and store it inside the TCP header. We
calculate the IPv4 checksum separately over the IPv4 header.

## Primary references

- [TCP checksum: RFC 9293, section 3.1](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.1)
- [IPv4 header checksum: RFC 791, section 3.1](https://www.rfc-editor.org/rfc/rfc791.html#section-3.1)

## Next step

Next, read [Choosing a language](choosing-a-language.md). It compares
C and Python for this exact project and selects the language for our first
implementation.
