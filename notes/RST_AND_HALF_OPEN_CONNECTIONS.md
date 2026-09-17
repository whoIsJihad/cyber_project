# RST, the Sender Kernel, and the Missing Half-Open Connections

## The short answer

Your Python program successfully created and sent ten SYN packets. The receiver
accepted them as valid TCP connection requests and replied with SYN-ACK packets.

Then the normal Linux TCP stack on the sender VM sent RST packets. Those resets
told the receiver: "I do not have this connection; discard it." The receiver
therefore removed each half-open connection almost immediately.

The current program is not broken. It proves that we can construct and transmit
a valid IPv4/TCP SYN packet. But it cannot yet demonstrate lasting half-open
connections, because the sender operating system cleans them up for us.

## First principles: what TCP is trying to do

TCP is a conversation between two operating systems. Before data can be sent,
both sides must agree to create a connection.

```text
client                              server
  |                                    |
  | -------- SYN --------------------> |  "May we start a connection?"
  | <------ SYN-ACK ------------------ |  "Yes. I am ready too."
  | -------- ACK --------------------> |  "I received your reply."
  |                                    |
  | ===== HTTP request / response ==== |
```

The three opening messages are the three-way handshake.

After receiving the first SYN, the server has done some work. It records a
temporary connection entry and waits for the final ACK. At that point it is in
the TCP state called `SYN-RECV` (SYN received). The connection is half-open:
the server is waiting, but the client has not completed the handshake.

```text
server receives SYN
        |
        v
server keeps a temporary SYN-RECV entry
        |
        +-- receives final ACK --> connection becomes established
        |
        +-- waits too long ------> temporary entry expires
```

The point of a SYN-flood experiment is not merely to send SYN-shaped packets.
It is to make the receiver hold many temporary `SYN-RECV` entries long enough
that they consume a limited TCP resource. Whether that causes a visible service
effect is a separate measurement, not something to assume.

## What our Python program did

The sender used a raw IPv4 socket. Python supplied complete packet bytes,
including the IPv4 header and TCP header.

```text
source:       192.168.150.10:12345
destination:  192.168.150.20:80
flags:        SYN
```

The receiver saw this as a normal request to start a TCP connection. It replied
with a SYN-ACK:

```text
source:       192.168.150.20:80
destination:  192.168.150.10:12345
flags:        SYN + ACK
```

The SYN-ACK reached the sender VM. Two separate pieces of sender software now
matter:

```text
Python raw-socket program       normal Linux TCP stack
-------------------------       ----------------------
creates the SYN packet          receives the SYN-ACK reply
does not create a TCP socket    looks for a matching TCP connection
```

Your Python program did not use a normal TCP client socket such as one created
by `connect()`. The sender's Linux TCP stack therefore had no matching
connection entry for the incoming SYN-ACK. Linux treated the reply as
unexpected and sent an RST.

## What RST means

RST means reset. It is TCP's immediate "this conversation does not exist"
message.

It is different from a polite close. A normal finished connection uses `FIN`.
RST is used when a host receives a packet for a connection it does not know
about, or when it wants to end one immediately.

In this capture, the reset is not a failure message printed by Python. It is a
real packet created automatically by the sender VM's operating system.

```text
our Python program                 sender Linux kernel
------------------                 -------------------
sent custom SYN                     received SYN-ACK
did not send RST                    found no matching connection
                                   -> sent RST automatically
```

## Reading the packet sequence we captured

```text
192.168.150.10.12345 > 192.168.150.20.80: Flags [S]
192.168.150.20.80 > 192.168.150.10.12345: Flags [S.]
192.168.150.10.12345 > 192.168.150.20.80: Flags [R]
```

Read it as a short story:

1. The raw-socket program said: "Receiver, start a connection with me."
2. The receiver said: "Okay, I am waiting for your final acknowledgement."
3. The sender kernel said: "I do not know this connection. Cancel it."

The receiver does not keep each entry until its normal timeout because the RST
ends it early.

## Does this mean the project fails?

No. The first live run achieved an important proof:

- The packet bytes were accepted by the receiver as a TCP SYN.
- The receiver returned a correctly related SYN-ACK.
- The capture revealed the exact operating-system behavior that prevents the
  intended half-open state from lasting.

However, it would be inaccurate to call the current result a completed SYN
flood demonstration. It is currently a bounded raw SYN generator and a
successful packet-delivery test. To test half-open connection pressure, the lab
must prevent the sender's automatic RST replies from reaching the receiver
during the short, measured run.

## The selected workaround: an unused lab-only source address

The required change is not "make Python stop sending RST." Python never sent
the RST. The selected solution is an unused source address inside the isolated
lab network.

The generator uses `192.168.150.99` as its packet source. Both lab VMs were
checked: neither owns that address, and it did not reply to ping. Each generated
packet also uses a different source port, so it is a distinct TCP connection
attempt rather than a retransmission of one attempt.

The expected flow is:

```text
sender raw program                 receiver                    unused .99 host
------------------                 --------                    ----------------
SYN -----------------------------> keeps SYN-RECV entry
             <------------------- SYN-ACK
                                              receiver cannot resolve .99's MAC
```

The receiver creates its temporary entry before it tries to send the SYN-ACK.
Because `.99` has no Ethernet address, the SYN-ACK may not appear in a TCP-only
capture: the receiver cannot transmit it after ARP resolution fails. The
important evidence for this approach is therefore the receiver's `SYN-RECV`
state, observed while the bounded test is running.

This still does not guarantee that Nginx becomes unavailable. Modern Linux can
use protections such as SYN cookies, and the VM may have enough capacity for a
small bounded test. Measurement decides the result.

## A safe next experiment design

1. Confirm both VMs are still only on `192.168.150.0/24` with no forwarding.
2. Record receiver baseline: Nginx status, normal HTTP response, and current
   `SYN-RECV` count.
3. Capture on the receiver and send a small bounded number first.
4. Observe `SYN-RECV` while the entries exist.
5. Check the normal HTTP service separately.
6. Keep `.99` unassigned for the duration of the experiment.

Do not increase packet counts until each earlier measurement is understood.

## What evidence would show success at each stage

| Claim | Required evidence |
|---|---|
| The generator works | Sender reports its bounded send count. |
| The receiver receives valid SYN packets | Receiver capture shows distinct `[S]` packets from `.99`. |
| The workaround works | Sender `.10` does not appear as a source of `[R]` packets. |
| Half-open entries persist | Receiver observation shows `SYN-RECV` entries during the test. |
| The web service is affected | A normal HTTP measurement shows a measurable change. |

Keep these claims separate in the report. A packet capture alone proves packet
delivery; it does not prove service impact.
