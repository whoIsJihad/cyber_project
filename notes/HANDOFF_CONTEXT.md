# SYN Flood Project — Codex Extension Handoff

Last verified locally: **2026-09-16**.

Open this folder in VS Code/Codex:

```text
/mnt/Data/4-1/syn-flood-dos-project
```

Read this file before changing code. The project notes are all inside `notes/`.

## Main goal

Demonstrate a TCP SYN-flood attempt only inside the isolated two-VM university
lab, capture the traffic on the receiver, and measure whether the normal Nginx
service remains reachable. The final report must distinguish packet-generation
proof from proof of actual receiver-side impact.

## Lab layout

```text
syn-sender    192.168.150.10    user: snd
syn-receiver  192.168.150.20    user: recv
```

The receiver runs Nginx on TCP port 80. The lab network is
`syn-lab-isolated` on `192.168.150.0/24` with no forwarding to the internet.

The goal is to construct a SYN packet ourselves, send it only to the receiver,
capture it, and measure the receiver separately. Do not use this code against
any other address or network.

## Current code status

The offline packet-building stage is complete and tested.

```text
client/checksum.py    Internet checksum
client/tcp.py         20-byte TCP SYN header, pseudo-header, TCP checksum
client/ipv4.py        20-byte IPv4 header and IPv4 checksum
client/packet.py      Joins IPv4 + TCP into one 40-byte packet
client/dry_run.py     Prints the packet; sends nothing
client/generator.py   Raw-socket sender for the fixed isolated receiver

tests/                pytest checks for every component above
```

The generated no-options packet is:

```text
20-byte IPv4 header + 20-byte TCP SYN header = 40 bytes
```

No Ethernet header is built by our code. The raw IPv4 socket hands the packet
to Linux; Linux handles the local Ethernet frame, ARP, and interface choice.

## Verified local commands

Run these in the project folder:

```bash
python3 -m pytest -q
python3 client/dry_run.py
```

Latest result:

```text
24 passed
```

The dry run prints the 40 packet bytes and explicitly sends nothing.

## What has not been verified

`client/generator.py` has unit tests with a fake socket, but it has **not**
been executed with a real raw socket on `syn-sender`. No custom SYN packet has
yet been captured on `syn-receiver`.

Do not claim the receiver queue filled until a receiver-side capture and TCP
state observation prove it. A manually built SYN with source address
`192.168.150.10` may receive a SYN-ACK that the sender's normal TCP stack
answers with RST; the first real capture must show what actually happens.

## First live verification sequence

Do these one at a time. Stop after each expected result and inspect it.

### 1. Confirm local code before copying

On the main computer, from the project folder:

```bash
python3 -m pytest -q
python3 client/dry_run.py
```

Expected: all tests pass and the dry run shows a 40-byte packet.

### 2. Copy only the sender code

On the main computer:

```bash
scp -r client snd@192.168.150.10:~/syn-lab-client/
```

This copies the local `client/` folder to the sender VM.

### 3. Start a short receiver capture

Inside `syn-receiver`:

```bash
mkdir -p ~/syn-lab-server/results
sudo tcpdump -ni ens3 -c 20 -w ~/syn-lab-server/results/first-syn.pcap 'tcp port 80'
```

Expected: tcpdump waits for up to 20 TCP/80 packets, then stops itself.

### 4. Send one small first run

Inside `syn-sender`:

```bash
sudo python3 ~/syn-lab-client/client/generator.py --count 10 --rate 10
```

Expected: the generator prints how many SYN packets it sent. The receiver
capture should contain traffic toward port 80. Check the capture before trying
larger settings.

## Important generator facts

`client/generator.py` is deliberately fixed to this lab:

```text
source address:       192.168.150.10
destination address:  192.168.150.20
destination TCP port: 80
```

It uses Python's built-in `socket` library. It needs `sudo` only on the sender
VM because raw sockets require administrator permission.

The sender has tests that use a fake socket. Those tests prove packet assembly,
the send-loop calls, rate waits, destination choice, and socket close without
placing packets on a real network. They do not prove that the VM sends or the
receiver accepts the packets.

## Where to read when confused

```text
notes/TESTING_GUIDE.md               What pytest is and what every test checks
notes/CLIENT_IMPLEMENTATION_PLAN.md  Full sender-side plan
notes/SERVER_IMPLEMENTATION_PLAN.md  Receiver monitoring and evidence plan
notes/tcp-syn-basics.md              TCP handshake and SYN basics
notes/packet-bytes-and-checksums.md  Packet-byte concepts
notes/linux-raw-sockets.md           Why raw sockets are needed
sessions/SESSION_LOG.md              Previous questions and decisions
```

## Instructions for the next Codex extension session

Start with this request:

> Read `notes/HANDOFF_CONTEXT.md`, inspect the current source and tests, run
> `python3 -m pytest -q`, and do not change code until you report the result.

Keep explanations slow and concrete. Prefer direct functions and obvious names.
Avoid adding abstractions, nested functions, lambdas, or new dependencies unless
they are genuinely required.
