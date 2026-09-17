# Internet checksums

The checksum function will be our first piece of code.

It will not create a packet.

It will not open a socket.

It will only calculate one number from some bytes.

## What goes into the function?

The input is a sequence of bytes.

Here is a small example:

```text
00 01 00 02
```

## What comes out?

The output is one 16-bit number.

For the example above, the answer is:

```text
ff fc
```

We usually write this as `0xfffc`.

## Why do we need this function?

The IPv4 header has a checksum field.

The TCP header also has a checksum field.

Both checksums use the same calculation. They use different input bytes.

We can therefore write one checksum function and use it twice:

1. Give it the IPv4 header bytes to calculate the IPv4 checksum.
2. Give it the TCP checksum input to calculate the TCP checksum.

## Step 1: read two bytes at a time

The calculation works with 16-bit numbers. A 16-bit number contains 2 bytes.

Suppose the input is:

```text
00 01 00 02
```

Split it into two groups:

```text
00 01
00 02
```

The groups represent these numbers:

```text
0x0001
0x0002
```

## Step 2: add the numbers

Add the 16-bit numbers:

```text
0x0001 + 0x0002 = 0x0003
```

## Step 3: handle overflow

A 16-bit result can contain only four hexadecimal digits.

Sometimes addition produces an extra digit. For example:

```text
0xffff + 0x0001 = 0x10000
```

The extra `1` on the left is called the **carry**.

Move that carry back into the 16-bit result:

```text
low 16 bits: 0x0000
carry:       0x0001
result:      0x0001
```

This step is sometimes called **folding the carry**.

If another carry appears, fold it again.

## Step 4: invert the bits

The last step changes every `0` bit to `1` and every `1` bit to `0`.

Our first example produced this sum:

```text
0x0003
```

After inverting its bits, we get:

```text
0xfffc
```

That is the checksum.

In C, bitwise inversion uses `~`.

In Python, it also uses `~`, but we must keep only the lowest 16 bits. We will
deal with that detail when we write the code.

## What if the input has an odd number of bytes?

The function reads 2 bytes at a time. An odd-length input leaves one byte at
the end.

For example:

```text
12 34 56
```

For the calculation, treat it like this:

```text
12 34 56 00
```

The extra zero is temporary. Do not add it to the real packet.

Our first IPv4 and TCP headers are both 20 bytes, so they are already even.
The function should still handle odd input correctly.

## The whole calculation

The checksum function does this:

1. Start with a sum of zero.
2. Read 2 input bytes as one 16-bit number.
3. Add that number to the sum.
4. Repeat until all input bytes are used.
5. Fold any carry back into the low 16 bits.
6. Invert the low 16 bits.
7. Return the result.

## Simple pseudocode

This is not C or Python. It only describes the logic:

```text
checksum(bytes):
    if the number of bytes is odd:
        temporarily add one zero byte

    sum = 0

    for each pair of bytes:
        read the pair as one 16-bit number
        add that number to sum

    while sum has a carry:
        add the carry to the low 16 bits

    invert the low 16 bits
    return the result
```

## Tests to write first
![[Pasted image 20260903204103.png]]

We should test the function with small inputs whose answers are easy to check.

| Input bytes | Expected checksum | What it tests |
|---|---:|---|
| `00 00` | `0xffff` | Basic inversion |
| `00 01 00 02` | `0xfffc` | Adding two values |
| `ff ff 00 01` | `0xfffe` | Folding a carry |
| `12 34 56` | `0x97cb` | Odd number of bytes |

After those tests pass, use the IPv4 header from Note 2. Its checksum field
must first contain zero. The expected checksum is `0xa47d`.

## Calculating versus checking

To **calculate** a checksum, set its field to zero and run the function.

To **check** a completed header, leave its checksum in place and run the same
function over all covered bytes.

A correct completed header produces `0x0000`.

This gives us a useful test:

1. Build a header with a zero checksum field.
2. Calculate the checksum.
3. Put the result into the header.
4. Run the checksum function over the completed header.
5. Confirm that the answer is zero.

## What we are not doing yet

We are not building the Ethernet header.
We are not building the IPv4 header.
We are not building the TCP header.
We are not sending packets.
First, we make this one small function correct.

## Check your understanding

1. Why does the function read 2 bytes at a time?
2. What is a carry?
3. What does folding the carry mean?
4. What does inverting the bits mean?
5. What temporary byte is used for odd-length input?
6. What result should a correct completed header produce?

## Primary reference

- [RFC 1071: Computing the Internet checksum](https://www.rfc-editor.org/rfc/rfc1071.html)

## Next step

Next, read [Building headers](building-headers.md).
It explains why the TCP checksum uses IP values and how that affects the order
in which we build the headers.
