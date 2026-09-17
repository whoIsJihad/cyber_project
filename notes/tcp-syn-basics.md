# TCP SYN basics

## The one idea to understand first

A SYN flood is not primarily about sending a large file. It abuses the fact
that a TCP server normally remembers connection attempts before those
connections are fully established.

Suppose a server is listening on a TCP port. A client begins a connection by
sending a TCP segment with the SYN flag set. The server replies with a segment
whose SYN and ACK flags are set. At this point, the server has not yet received
the client's final ACK, but it generally retains temporary state for the
unfinished connection. This state is often described as a *half-open
connection*.

A SYN flood produces enough unfinished connection attempts that the server's
capacity for remembering them becomes constrained. Legitimate clients may
then be delayed or rejected. The relevant resource is therefore the server's
pending-connection state, commonly discussed as the SYN backlog, rather than
the payload bandwidth of one connection.

Our experiment must show the connection between the traffic we generate and
the harm a SYN flood is supposed to cause. We will measure four things during
each test:

- **Traffic sent:** the number and rate of initial SYN segments produced by
  our program.
- **Server state:** the number of connections waiting in the server's
  SYN-RECEIVED state.
- **Service impact:** whether a separate, legitimate client can still connect,
  and how long that connection takes.
- **Defense effect:** whether enabling a defense reduces the service impact
  under the same controlled workload.

These measurements form a causal story. Our program supplies a known input;
the server accumulates half-open connections; legitimate connection behavior
reveals whether service has degraded. Repeating the same test with a defense
enabled lets us compare results instead of merely claiming that the defense
works.

## Frame, packet, and segment are three nested units

These words identify data handled at different protocol layers.

### TCP segment

The TCP segment contains the TCP header and any application data. An initial
SYN normally carries no application payload. Its TCP header includes source
and destination ports, a sequence number, header length, flags, window size,
checksum, urgent pointer, and possibly TCP options.

For our first minimal SYN, the meaningful choices include:

- source and destination ports;
- an initial sequence number;
- the SYN flag;
- the TCP header length;
- a receive-window value;
- a valid TCP checksum.

The checksum is not calculated from the TCP header alone. It also covers a
small conceptual *pseudo-header* containing information from IP, including the
source address, destination address, protocol number, and TCP length. The
pseudo-header is used for calculation but is not transmitted as an extra
header.

### IPv4 packet

The IPv4 packet, also called an IP datagram, contains an IPv4 header followed
by the TCP segment. A minimal IPv4 header contains the version, header length,
service field, total length, identification, fragmentation fields, time to
live, protocol number, header checksum, source address, and destination
address.

For TCP, the IPv4 Protocol field is 6. IPv4 has its own checksum, which covers
only the IPv4 header. This is separate from the TCP checksum.

### Ethernet frame

Ethernet is responsible for delivering data across one local link. In our
isolated lab, that link will be the virtual Ethernet connection between two
network namespaces. To send an IPv4 packet across this link, the sender places
a 14-byte Ethernet header directly before the IPv4 packet. Together, that
header and its contents are called an Ethernet frame.

The basic Ethernet header contains three fields, in this exact order:

1. The first 6 bytes are the **destination MAC address**. They identify the
   interface that should receive the frame on the local link. In our simple
   two-namespace lab, this will be the MAC address of the server-side virtual
   Ethernet interface.
2. The next 6 bytes are the **source MAC address**. They identify the interface
   that transmitted the frame. This will be the MAC address of the
   sender-side virtual Ethernet interface.
3. The final 2 bytes are the **EtherType**. This value tells the receiver how
   to interpret the data immediately following the Ethernet header. EtherType
   `0x0800` means that the following data is an IPv4 packet.

MAC addresses and IP addresses serve different purposes. The Ethernet header
uses MAC addresses for delivery across the current local link. Inside that
frame, the IPv4 header uses IP addresses to identify the source and destination
at the network layer. In a routed network, the destination MAC address can
belong to a router while the destination IP address belongs to a remote host.
Our first lab avoids that extra complication by connecting the sender and
server directly through a virtual Ethernet pair.

When our program uses a Linux `AF_PACKET` socket with `SOCK_RAW`, it supplies
this Ethernet header itself. The complete byte buffer begins with the 14-byte
Ethernet header, and the serialized IPv4 packet follows immediately after it.
Because the IPv4 packet already contains the TCP segment, one buffer holds all
three protocol layers that the assignment asks us to understand.

The program does not construct every bit that appears on the physical wire.
The network interface and its driver normally handle details such as the
Ethernet preamble and frame check sequence. For this project, “construct the
Ethernet frame” means that our code creates the Ethernet header and its
IPv4/TCP contents before giving the byte buffer to the Linux packet socket.

The resulting byte buffer is laid out in this order:

1. Ethernet header
2. IPv4 header
3. TCP header
4. TCP options or payload, if the experiment deliberately includes them

## What the assignment phrase probably means

“Craft your own frame / packet / segment” means that our code should create
protocol headers instead of asking Linux to create all of them through a
normal TCP connection.

For example, the number 8080 is a destination port. It cannot be placed in the
outgoing buffer as the four text characters `8`, `0`, `8`, `0`. A TCP port is
a 16-bit field, so our code must encode 8080 as the two bytes `1f 90` in the
correct position in the TCP header. The same idea applies to sequence numbers,
flags, addresses, lengths, and checksums.

This process is called **serialization**: converting meaningful field values
in the program into the exact ordered bytes required by a protocol. It is not
usually about manually turning strings into individual bits. We will store
values as integers or address values, encode them into bytes, combine those
bytes into headers, and combine the headers into one buffer.

A normal TCP socket is too high-level for this assignment. If our program
calls `connect()` on a `SOCK_STREAM` socket, we provide only an address and
port. Linux chooses the TCP sequence number, creates the TCP header, creates
the IP header, calculates the checksums, and handles the handshake. We would
be using TCP, but we would not be demonstrating how to construct a TCP
segment.

## Choosing our level of control

The socket interface determines where our work stops and the kernel's work
begins.

If names such as `AF_INET`, `SOCK_RAW`, and `IP_HDRINCL` are unfamiliar, read
[Linux raw sockets](linux-raw-sockets.md). It explains
what each part of these names means and how to read a complete socket call.

| Interface | What our program creates | What Linux creates |
|---|---|---|
| Normal TCP socket | Application data only | TCP, IPv4, and Ethernet headers |
| IPv4 raw socket | TCP header and IPv4 header | Ethernet header and local-link delivery |
| Ethernet packet socket | Ethernet, IPv4, and TCP headers | No protocol header in our 54-byte buffer |

The last row does not mean the kernel and hardware do nothing. They still move
the buffer through the chosen interface and handle lower-level transmission
details. The table describes responsibility for the three headers relevant to
our assignment.

### Choice 1: IPv4 raw socket

The Linux API is an `AF_INET` socket of type `SOCK_RAW`. With the
`IP_HDRINCL` option, our program passes Linux this buffer:

1. An IPv4 header written by us
2. A TCP header written by us

We are working at the **IP layer**. We decide the TCP and IPv4 field values and
calculate the TCP checksum. Linux performs routing, determines how to reach
the next device on the local link, and creates the Ethernet header.

There is one complication: Linux still fills the IPv4 Total Length and IPv4
Header Checksum fields when sending with `IP_HDRINCL`. It can also fill a zero
source address and a zero Identification field. We can write and test all the
IPv4 fields ourselves, but the bytes actually transmitted are not completely
untouched by the kernel.

This choice is appropriate if the instructor requires an original **TCP
segment and IPv4 packet**, but does not require an Ethernet header. It is the
simpler live-sending interface.

### Choice 2: Ethernet packet socket

The Linux API is an `AF_PACKET` socket of type `SOCK_RAW`. Our program passes
Linux this buffer:

1. An Ethernet header written by us
2. An IPv4 header written by us
3. A TCP header written by us

We are working at the **Ethernet link layer**. Our program must know which
network interface to use and the destination interface's MAC address. Linux
does not add an Ethernet, IPv4, or TCP header to the buffer. It hands our frame
to the selected network-interface driver.

The driver and network interface still handle details below our useful level,
including the Ethernet preamble and usually the frame check sequence. Those
are physical transmission details, not fields in the 54-byte buffer described
in this project.

This choice is appropriate if the instructor expects an original **Ethernet
frame as well as the IPv4 packet and TCP segment**. It exposes the most header
construction and gives the clearest demonstration, but it also requires us to
handle MAC addresses and select an interface.

## What is required, and what should we choose?

The slashes in “frame / packet / segment” could mean examples of the three
terms, or they could mean that the instructor expects all three layers. Only
the instructor can settle that wording. We should show this precise question
in the implementation plan:

> Do we need to create all three headers ourselves: Ethernet, IPv4, and TCP?

Until we receive an answer, the strongest plan is to construct all three
headers and use `AF_PACKET/SOCK_RAW` for the final lab demonstration. That
clearly satisfies the broader interpretation. We can keep the transmitting
part small because the important work happens before the socket call.

Our code will explicitly create:

- the 14-byte Ethernet header;
- the 20-byte IPv4 header;
- the 20-byte TCP header with only the SYN flag set;
- the IPv4 header checksum;
- the TCP checksum, including its calculation-only pseudo-header;
- the final 54-byte buffer containing those three headers.

We will not try to create the Ethernet preamble, inter-packet gap, or physical
electrical signals. Linux and the network interface handle those. They are not
normally supplied through a packet socket and are not a sensible requirement
for a C or Python packet-crafting assignment.

## The project model we will use

We will build the program as several small, visible steps:

1. Write a checksum function and test it with known bytes.
2. Write the TCP header fields into a 20-byte buffer.
3. Write the IPv4 header fields into another 20-byte buffer.
4. Write the Ethernet fields into a 14-byte buffer.
5. Join those buffers and confirm that the result is exactly 54 bytes.
6. Inspect and validate the buffer without sending it.
7. Only then, pass one validated frame to an `AF_PACKET` socket inside the lab.

The first six steps need no raw-socket privilege and cannot flood a network.
They also contain most of what we need to understand for the assignment.

## What “virtual Ethernet” means

A Linux network namespace is a separate copy of networking state inside one
computer. It can have its own interfaces, IP addresses, routes, firewall
rules, and listening ports. A program running in one namespace sees that
namespace's network environment instead of the host's normal environment.

A virtual Ethernet pair, usually called a `veth` pair, consists of two
software-created network interfaces. Anything transmitted through one
interface is received by the other. It behaves like a short Ethernet cable
connecting two interfaces, except the entire connection exists inside the
Linux kernel and no physical cable or second computer is required.

For our lab, one endpoint belongs to a sender namespace and the other belongs
to a server namespace. Each endpoint has its own MAC address and IPv4 address.
The server can run a normal listening program, while our project runs in the
sender namespace. We will not connect either endpoint to the host's physical
network interface, a bridge, or an external route. This keeps the generated
frames inside the computer.

The `veth` pair does not construct packets for us. It only provides the closed
path over which our completed Ethernet frames can travel.

## Who is responsible for each part in our planned design?

| Part | Responsible component |
|---|---|
| Choose TCP field values | Our program |
| Encode the TCP header | Our program |
| Calculate the TCP checksum | Our program |
| Choose IPv4 field values | Our program |
| Encode the IPv4 header | Our program |
| Calculate the IPv4 checksum | Our program |
| Choose source and destination MAC addresses | Our program or fixed lab configuration |
| Encode the Ethernet header | Our program |
| Combine the three headers into 54 bytes | Our program |
| Select the virtual interface and submit the buffer | Our program using the socket API |
| Transfer the frame between the two `veth` endpoints | Linux kernel |
| Process the received IPv4 and TCP headers | Server namespace's Linux kernel |
| Add physical-wire details | Driver or hardware; absent from a purely virtual link |

This boundary lets us truthfully say that our own code crafted the frame,
packet, and segment, while still using Linux to deliver the bytes. Using a
socket to submit bytes does not defeat the assignment; asking a normal TCP
socket to invent the headers would.

## What not to learn yet

We do not need TCP congestion control, application protocols, IP routing
protocols, IPv6 extension headers, high-performance packet I/O, or evasion
techniques for the first implementation. We also do not need TCP payloads.

Our first programming problem is much smaller: correctly represent one
minimal Ethernet/IPv4/TCP SYN frame as bytes and prove that it is correct.

## Checks for understanding

Before writing code, you should be able to answer these in your own words:

1. Why does a server retain state after receiving an initial SYN?
2. Why is that connection described as half-open?
3. Which header contains port numbers?
4. Which header contains MAC addresses?
5. Why are the IPv4 and TCP checksums two different calculations?
6. Why is the TCP pseudo-header calculated but not transmitted?
7. What headers would our program write when using an IPv4 raw socket?
8. What additional header would it write when using an Ethernet packet socket?
9. What does a `veth` pair provide, and what does it not construct for us?
10. Why does using a packet socket still count as crafting our own frame?

If any answer is unclear, that is the next concept to discuss. There is no
reason to start the sender until these seven points feel ordinary.

## Primary reading, in this order

1. [RFC 9293, section 3.1: TCP header format](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.1)
2. [RFC 9293, section 3.5: connection establishment](https://www.rfc-editor.org/rfc/rfc9293.html#section-3.5)
3. [RFC 791, section 3.1: IPv4 header format](https://www.rfc-editor.org/rfc/rfc791.html#section-3.1)
4. [Linux packet(7)](https://man7.org/linux/man-pages/man7/packet.7.html)
5. [Linux raw(7)](https://man7.org/linux/man-pages/man7/raw.7.html)
6. [RFC 4987: SYN flooding and common mitigations](https://www.rfc-editor.org/rfc/rfc4987.html)
7. [Linux network_namespaces(7)](https://man7.org/linux/man-pages/man7/network_namespaces.7.html)

Do not try to memorize the RFCs. For now, read the named sections to connect
the field names in the standards to the mental model above.

## Next small step

Note 2 explains byte order, exact header sizes, field offsets, and checksums
using one fixed, non-transmitted example. After understanding that example, we
can implement only the checksum function and its tests. We will still not open
a raw socket at that stage.
