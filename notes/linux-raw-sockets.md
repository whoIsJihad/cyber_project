# Linux raw sockets

Names such as `AF_INET` look arbitrary when several appear in one line. They
become easier once we separate the questions they answer.

## Start with the three arguments to `socket`

In C, a socket is created with this general form:

```c
socket(domain, type, protocol)
```

Each argument answers a different question:

| Argument | Question it answers |
|---|---|
| `domain` | Which family of addresses and protocols will this socket use? |
| `type` | What service or access style should the socket provide? |
| `protocol` | Which specific protocol should be used inside that family? |

The constants are integer values defined by system headers. Their capitalized
names help humans read the code; the kernel receives the corresponding
integers.

## `AF` means address family

The prefix `AF_` means **address family**. It describes the kind of addresses
and networking environment used by the socket.

### `AF_INET`

`INET` is short for **Internet**. In the socket API, `AF_INET` specifically
means the IPv4 family. It uses IPv4 addresses such as `192.0.2.10` and the
`sockaddr_in` address structure.

The name does not mean “use the public Internet.” An `AF_INET` socket works on
an isolated private network, a loopback interface, or our namespace lab. It
describes the protocol family, not where packets are allowed to travel.

### `AF_INET6`

`AF_INET6` means the IPv6 family. It uses IPv6 addresses and `sockaddr_in6`.
We are not using IPv6 in the first version of this project.

### `AF_PACKET`

`AF_PACKET` is Linux's interface for packets at the network-device level. It
lets a program send or receive link-layer data, such as an Ethernet frame.
The address structure is `sockaddr_ll`; the `ll` suffix means **link layer**.

`AF_PACKET` is lower-level than `AF_INET` for our purposes. With
`AF_PACKET/SOCK_RAW`, our buffer begins with an Ethernet header. With an
`AF_INET` raw socket, our buffer begins with an IPv4 header and Linux handles
the Ethernet header.

### Why do some sources say `PF_INET`?

`PF_` means **protocol family**. Historically, address families and protocol
families were described as separate ideas. On Linux, constants such as
`PF_INET` and `AF_INET` have the same value. Modern socket code conventionally
uses `AF_INET` in the `socket` call, so that is what we will use.

## `SOCK` describes the socket type

The prefix `SOCK_` identifies the style of service or access requested from
the kernel. It does not select IPv4, IPv6, or Ethernet by itself.

### `SOCK_STREAM`

`SOCK_STREAM` provides an ordered byte stream. With `AF_INET`, the usual
protocol is TCP. A normal TCP application uses something like:

```c
socket(AF_INET, SOCK_STREAM, 0)
```

Here, `0` means “choose the normal protocol for this family and socket type.”
Linux selects TCP and constructs the TCP and IP headers. This is appropriate
for web servers and ordinary clients, but it hides the header construction
required by our assignment.

### `SOCK_DGRAM`

`DGRAM` is short for **datagram**. With `AF_INET`, this normally means UDP.
Each send represents a separate message. It is useful background terminology,
but it is not the type we need for constructing a TCP SYN.

### `SOCK_RAW`

`RAW` means the program needs direct access to protocol bytes that a normal
stream or datagram socket would have the kernel create or remove.

“Raw” does not always mean the buffer starts at the same header. The address
family determines that boundary:

| Combination | First header in our outgoing buffer |
|---|---|
| `AF_INET` with `SOCK_RAW` and `IP_HDRINCL` | IPv4 header |
| `AF_PACKET` with `SOCK_RAW` | Ethernet header |

Opening raw sockets requires suitable privilege on Linux, normally the
`CAP_NET_RAW` capability. Our offline serializer and checksum tests do not
open a socket and therefore do not need this privilege.

## `IPPROTO` means IP protocol

The IPv4 header has an 8-bit Protocol field identifying the content carried
inside the IP packet. Names beginning with `IPPROTO_` represent these protocol
numbers in the socket API.

Examples include:

- `IPPROTO_TCP`, whose protocol number is 6;
- `IPPROTO_UDP`, whose protocol number is 17;
- `IPPROTO_ICMP`, whose protocol number is 1;
- `IPPROTO_IP`, used as the socket-option level for IPv4 options.

For an IPv4 raw TCP socket, this call:

```c
socket(AF_INET, SOCK_RAW, IPPROTO_TCP)
```

can be read as:

> Create an IPv4-family socket, give me raw protocol access, and use TCP as
> the protocol carried by IPv4.

This call alone does not yet say that our buffer contains an IPv4 header. That
is what `IP_HDRINCL` controls.

## `IP_HDRINCL` means IP header included

`HDR` abbreviates **header**, and `INCL` abbreviates **included**. Therefore,
`IP_HDRINCL` reads as **IP header included**.

It is an option set on an IPv4 raw socket:

```c
int enabled = 1;
setsockopt(fd, IPPROTO_IP, IP_HDRINCL, &enabled, sizeof(enabled));
```

The arguments say:

- `fd`: change this socket;
- `IPPROTO_IP`: the option belongs to the IPv4 layer;
- `IP_HDRINCL`: our outgoing data already includes an IPv4 header;
- `enabled`: turn the option on.

Without this option, the kernel normally creates the IPv4 header. With it,
our outgoing buffer begins with the IPv4 header we prepared, followed by the
TCP header. Linux still fills or changes a few IPv4 fields on transmission, as
listed in `raw(7)`.

`IP_HDRINCL` applies to `AF_INET` raw sockets. It is unnecessary for
`AF_PACKET/SOCK_RAW`, because an `AF_PACKET` frame already begins below the IP
layer with its Ethernet header.

## `ETH_P_IP` identifies IPv4 inside Ethernet

The prefix `ETH_P_` names an **Ethernet protocol**, which in this context means
an EtherType value. `ETH_P_IP` represents EtherType `0x0800`, identifying IPv4
as the Ethernet payload.

A packet-socket call commonly includes:

```c
socket(AF_PACKET, SOCK_RAW, htons(ETH_P_IP))
```

Read it as:

> Create a network-device-level socket, include the raw link-layer header, and
> select Ethernet frames whose payload protocol is IPv4.

`htons` means **host to network short**. It converts a 16-bit value from the
computer's native byte order to network byte order. The `packet(7)` interface
expects this protocol argument in network byte order.

Using `ETH_P_IP` as the socket argument does not insert `0x0800` into our
Ethernet header. When sending with `AF_PACKET/SOCK_RAW`, our serializer must
still put those two bytes in the header itself.

## The address-structure names

Socket APIs pass addresses through structures whose names reflect their
family:

| Name | Meaning in this project |
|---|---|
| `sockaddr` | Generic socket-address shape used by the API |
| `sockaddr_in` | IPv4 socket address; `in` refers to Internet |
| `sockaddr_ll` | Packet-socket address; `ll` means link layer |

For `AF_INET`, an address normally includes an IPv4 address. Normal TCP and
UDP sockets also use a port in `sockaddr_in`. For `AF_PACKET`, `sockaddr_ll`
can identify a network interface by its interface index and describe
link-layer addressing.

These structures tell Linux where or through which interface to send. They are
not automatically copied into our packet bytes. Our serializer separately
writes the required IP addresses, ports, and MAC addresses into their protocol
headers.

## How to read our two candidate designs

### IPv4 raw-socket design

```c
socket(AF_INET, SOCK_RAW, IPPROTO_TCP)
setsockopt(fd, IPPROTO_IP, IP_HDRINCL, ...)
```

Plain-language reading:

> Use IPv4 addressing. Give the program raw access to TCP carried by IPv4.
> The program's outgoing buffer already contains the IPv4 header.

Our buffer contains the IPv4 and TCP headers. Linux handles link-layer
delivery and constructs the Ethernet header.

### Ethernet packet-socket design

```c
socket(AF_PACKET, SOCK_RAW, htons(ETH_P_IP))
```

Plain-language reading:

> Work at the network-interface level. The program supplies the raw Ethernet
> frame. The frame carries IPv4.

Our buffer contains the Ethernet, IPv4, and TCP headers. Linux transfers it
through the selected interface but does not create those three headers for us.

## Naming traps to avoid

- `AF_INET` means IPv4, not permission to use the Internet.
- `SOCK_RAW` describes access style; it does not specify where the buffer
  begins without an address family and relevant options.
- `IPPROTO_TCP` identifies TCP as an IP payload; it does not construct a TCP
  header.
- `IP_HDRINCL` says an IPv4 header is present; it does not apply to a normal
  TCP stream socket.
- `AF_PACKET` is named for packet access, but a raw Ethernet buffer is commonly
  called a frame. Networking terminology and API naming do not always use the
  same word consistently.
- `htons` changes byte order, not the numeric meaning of an EtherType or port.

## Quick self-check

1. Which part of `socket(AF_INET, SOCK_RAW, IPPROTO_TCP)` selects IPv4?
2. Which part requests raw access?
3. Which part identifies TCP?
4. What additional fact does `IP_HDRINCL` tell Linux?
5. Why does `AF_PACKET/SOCK_RAW` require an Ethernet header from us?
6. Does `AF_INET` imply that traffic must leave the computer?
7. Does `ETH_P_IP` automatically write the EtherType bytes into our frame?

## Primary documentation

- [Linux socket(2)](https://man7.org/linux/man-pages/man2/socket.2.html)
- [Linux raw(7)](https://man7.org/linux/man-pages/man7/raw.7.html)
- [Linux packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html)
- [Linux ip(7)](https://man7.org/linux/man-pages/man7/ip.7.html)
- [Linux byteorder(3)](https://man7.org/linux/man-pages/man3/byteorder.3.html)
