# Wireshark, later

You do not need Wireshark yet. `tcpdump` already proved that Nginx, the fixed
addresses, and normal TCP traffic work.

Wireshark becomes useful when you want to click through one packet and see its
Ethernet, IPv4, and TCP fields separately. It is a viewer, not another server.

## Do you need another VM?

No. The physical host can see the private virtual switch, so Wireshark can run
on the host. A third VM is not needed.

Two easy choices:

1. Capture on receiver with tcpdump, save a `.pcap` file, then open that file
   in Wireshark on the host.
2. Run Wireshark on the host and capture the host-side private bridge
   `virbr150`.

For now, choose the first option. It is simpler: capture only the small test
you mean to study, then open it later.

## When to use which tool

| Tool | Best for now |
|---|---|
| `tcpdump` | Quick proof: did packets arrive, did the handshake happen, did HTTP return `200 OK`? |
| Wireshark | Slow inspection: what exact value is in this packet field? |

Do not install or add another VM just for viewing packets. First build a small
`.pcap` from normal `curl` traffic. When packet-building code exists, compare
its packets against this normal baseline in Wireshark.
