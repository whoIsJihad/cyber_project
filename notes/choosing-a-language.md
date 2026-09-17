# Choosing a language

The assignment allows C, C++, or Python. All three can create the exact packet
bytes we need. The language does not decide whether the packet is “our own.”
What matters is whether our code builds the headers and checksums itself.

For this project, the real choice is between C and Python. C++ would work, but
it does not give us a useful advantage for a program this small.

## What both versions must do

No matter which language we choose, our program must:

- store MAC addresses, IP addresses, ports, and other field values;
- write those values in network byte order;
- build the Ethernet, IPv4, and TCP headers;
- calculate the IPv4 checksum;
- build the temporary TCP pseudo-header;
- calculate the TCP checksum;
- combine the three headers into a 54-byte frame;
- test the result before sending it;
- eventually give the completed frame to an `AF_PACKET/SOCK_RAW` socket.

Both languages use the same Linux socket interface. Both require the same
raw-socket permission when we begin transmitting. The protocol work is also
the same.

## Using Python

Python has a built-in `bytes` type for raw bytes. Its standard `struct` module
can convert integers into bytes of a chosen size and byte order.

For example, this expression represents port 8080 as a two-byte network-order
value:

```python
struct.pack("!H", 8080)
```

The result contains these bytes:

```text
1f 90
```

The `!` selects network byte order. The `H` means one unsigned 16-bit integer.

This is still packet construction. `struct.pack` does not know that 8080 is a
TCP destination port. Our code chooses the value, chooses the field size,
chooses the byte order, and places the result in the correct header position.

Python's standard `socket` module can open an `AF_PACKET/SOCK_RAW` socket. We
do not need Scapy, libnet, or another packet-generation library.

### Advantages of Python

- The code is shorter.
- Byte buffers are easy to print and compare in tests.
- We can focus on protocol fields instead of memory management.
- Unit tests are quick to write and run.
- It is easier to explain one header-building function at a time.

### Disadvantages of Python

- `struct.pack` format strings need explanation.
- Python hides memory allocation and some machine-level details.
- A poorly structured program can join byte strings in confusing ways.
- It is slower than C, although speed is not important for our controlled lab.

## Using C

C gives us direct control over memory. We can create a byte array and place
each field at a known offset.

For example, the complete frame could be stored in:

```c
uint8_t frame[54];
```

Our code would then fill its Ethernet, IPv4, and TCP sections.

C provides `htons` and `htonl` for converting 16-bit and 32-bit integers to
network byte order. It also provides the socket API directly through Linux
system headers.

### Advantages of C

- The relationship between memory and transmitted bytes is very direct.
- Buffer sizes and field offsets are visible.
- It matches the language used by the Linux socket documentation.
- It demonstrates low-level systems programming clearly.

### Disadvantages of C

- Buffer mistakes can read or write outside valid memory.
- We must pay attention to buffer sizes and byte order.
- More support code can distract from the networking concepts.
- Tests require more setup than simple Python tests.

## Two ways to build a header in C

We can use a structure or a byte array. Both can satisfy the assignment because
our code still chooses and writes the header fields.

### Using a structure

Linux provides `struct iphdr` for IPv4 and `struct tcphdr` for TCP. These
structures give names to the header fields. For example:

```c
struct tcphdr tcp = {0};
tcp.source = htons(40000);
tcp.dest = htons(8080);
```

This sets the source port to 40000 and the destination port to 8080.
`htons` puts each port in network byte order.

These Linux structures are designed to represent the headers. They are a
valid choice; using them does not mean Linux builds the packet for us. We
still fill the fields and calculate the checksums.

### Using a byte array

Instead of named fields, we can write directly to numbered byte positions:

```c
unsigned char tcp[20] = {0};
tcp[2] = 0x1f;
tcp[3] = 0x90;
```

Bytes 2 and 3 contain the destination port. Together, `1f 90` represents 8080.

Later, we could write a small helper to do those two assignments:

```c
write_u16(tcp, 2, 8080);
```

That helper would mean: write 8080 as a two-byte number starting at position 2,
in network byte order. It would be our own function, not a built-in C function.

Structures make field names easy to read. Byte arrays make byte positions
easy to see. Either way, we can test the output against the bytes in Note 2.

## Does Python violate the assignment?

No. Python's standard library provides byte handling and access to Linux
sockets. It does not automatically create our Ethernet, IPv4, or TCP headers.

A Python solution would violate the spirit of the assignment if it delegated
packet creation to a library such as Scapy. Using `bytes`, `bytearray`,
`struct`, and `socket` is different: our code still defines and builds every
required field.

The same rule applies to C. Writing C does not automatically make the work our
own if the program calls a packet-generation library to build the headers.

## Performance is not our deciding factor

C can generate packets faster than a simple Python program. That is not useful
for our project.

Our lab sender will deliberately have a low rate limit and a maximum packet
count. We need enough traffic to observe controlled server behavior, not the
highest possible packet rate. Readability, correctness, and testability matter
more than speed.

## Recommendation

Use **Python for the first complete version**.

Python gives us the shortest path from the protocol description to readable,
testable code. We can build each header ourselves without introducing memory
safety problems. During evaluation, we can print the field values and final
bytes, then explain exactly how they match Notes 2 and 5.

Use only Python's standard library:

- `struct` for fixed-size integers and network byte order;
- `socket` for address conversion and, later, the packet socket;
- `unittest` for tests;
- `argparse` later, when the program needs safe command-line options.

Do not use Scapy or any packet-building package.

If the instructor strongly prefers C, we can port the tested design afterward.
The header fields, offsets, construction order, and checksum tests will remain
the same. We would be changing the language, not redesigning the protocol.

## Planned files

We do not need many files at the beginning:

```text
src/
    checksum.py

tests/
    test_checksum.py
```

`checksum.py` will contain only the Internet-checksum function.
`test_checksum.py` will contain the small examples from Note 4 and the IPv4
example from Note 2.

We will not add packet classes, configuration objects, command-line parsing,
or socket code yet.

## What we should be able to defend in evaluation

We should be able to explain that:

- Python is one of the languages allowed by the assignment;
- our code chooses and serializes every header field;
- the standard library does not design the packet for us;
- our checksum code follows the protocol algorithm;
- our tests compare the output with fixed expected bytes;
- raw-socket access will be added only after offline construction is correct.

## Next step

The next step is small: create `src/checksum.py` and
`tests/test_checksum.py`. Implement only the checksum function and verify the
known examples from Note 4.
