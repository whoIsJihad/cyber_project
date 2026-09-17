# Project State

Read this file first. It is the short handoff for the next teammate.

## Main goal

Build and demonstrate a controlled TCP SYN-flood experiment only inside this
isolated lab:

```text
syn-sender (192.168.150.10)  →  syn-receiver (192.168.150.20:80)
```

The receiver runs Nginx. The final report must separate three claims:

1. We generated and delivered SYN packets.
2. The receiver held half-open TCP connections.
3. The normal HTTP service did, or did not, show a measurable effect.

Do not use this code against any target outside the isolated lab.

## Current verified state — 2026-09-16

- `syn-sender` and `syn-receiver` exist and use the isolated
  `192.168.150.0/24` network.
- The local test suite passes: **32 passed**.
- `client/generator.py` builds complete 40-byte IPv4/TCP SYN packets and sends
  them with a raw IPv4 socket.
- The receiver is fixed at `192.168.150.20:80`.
- The generator currently rotates through synthetic source addresses in the
  lab-only pool `192.168.150.128/25`.
- It uses source ports `1024` through `65535` for one source IP, then advances
  to the next IP. This keeps connection identities distinct without scattering
  duplicated hardcoded limits through the project.
- The generator accepts either `--count` or a bounded `--duration`, plus a
  rate. It prints the actual sent count and elapsed time.
- `client/normal_web_client.py` performs ordinary HTTP requests and writes a
  CSV of success, latency, status, and error evidence.
- `server/monitor.py` samples Nginx state, port-80 listening state, TCP
  states, load, and available memory into a CSV file.
- Both VMs were checked: neither owns `192.168.150.99`, and it did not answer
  ping.

## What has been proved live

### First run: real sender source address

When packets used the sender's real address, `192.168.150.10`, the receiver
capture showed this pattern:

```text
sender SYN  →  receiver SYN-ACK  →  sender kernel RST
```

The sender's normal Linux TCP stack created the RST because the raw-socket
program had not created a normal TCP connection. Those RST packets quickly
removed the receiver's half-open entries.

### Current run: dummy source address

With source address `192.168.150.99`, receiver-side `ss` output showed entries
like this:

```text
0  0  192.168.150.20:80  192.168.150.99:20000
```

Every row shown by this command is a half-open connection in `SYN-RECV`:

```bash
ss -Hnt state syn-recv
```

Ten separate entries with source ports `20000` through `20009` were observed.
This proves that the receiver accepted the custom SYNs and kept distinct
half-open TCP entries until their normal timeout.

The receiver's TCP-only capture shows incoming SYN packets from `.99`. It may
not show SYN-ACK packets because no host owns `.99`; the receiver cannot resolve
an Ethernet/MAC address for that reply. That is expected for this approach.

## What is not yet proved

- No controlled measurement has yet shown a slowdown, failure, or other impact
  on normal HTTP access to Nginx.
- Do not claim that the receiver was throttled or that Nginx was unavailable.
- The effect of the receiver's TCP protections, including SYN cookies, has not
  yet been measured.

## Safe next work

1. Record a baseline normal HTTP result before a test.
2. Run one bounded sender test while saving a receiver capture and observing
   `SYN-RECV`.
3. Run the same normal HTTP check during or immediately after the controlled
   test.
4. Compare the result with the baseline. Increase the bounded count only after
   recording the earlier result.
5. Report the actual observation, even if the service remains fully reachable.

## Important commands

Refresh sender code from the main computer. The sender's old copy is normally
deleted first to avoid accidentally making `~/client/client`:

```bash
# On syn-sender
rm -rf ~/client

# On the main computer, inside this project folder
scp -r client snd@192.168.150.10:~/
```

Run the sender:

```bash
# On syn-sender
cd ~
sudo python3 -m client.generator --count 10 --rate 10
```

Save a receiver capture:

```bash
# On syn-receiver
sudo tcpdump -ni ens3 -c 20 -w ~/syn-lab-server/results/dummy-source-syn.pcap 'tcp port 80'
```

Watch half-open entries. `TERM=xterm` works around the receiver VM not knowing
the `xterm-kitty` terminal type:

```bash
# On syn-receiver
TERM=xterm watch -n 0.5 'ss -Hnt state syn-recv'
```

## Important files

```text
notes/COMMANDS_USED_IN_THE_LAB.md      Beginner explanation of every command
notes/RST_AND_HALF_OPEN_CONNECTIONS.md Why the original sender caused RST
notes/READING_FIRST_SYN_CAPTURE.md     How to read the first packet capture
notes/HANDOFF_CONTEXT.md                Older VM and lab setup context
client/                                 Packet builder and raw-socket generator
client/normal_web_client.py             Normal HTTP latency/success CSV tool
server/monitor.py                       Receiver-health and TCP-state CSV tool
tests/                                  Local verification
```
