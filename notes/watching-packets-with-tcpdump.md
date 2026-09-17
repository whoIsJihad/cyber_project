# Watching packets with tcpdump

`tcpdump` prints packets that pass through a network card. Run it on receiver
to see traffic arriving at `ens3`.

## The one command to start with

On `syn-receiver`:

```bash
sudo tcpdump -ni ens3 tcp port 80
```

Leave it running. On sender, run:

```bash
curl -I http://192.168.150.20
```

Back on receiver, stop tcpdump with `Ctrl+C`.

## Read the command

| Part | Meaning |
|---|---|
| `sudo` | Packet capture needs administrator permission. |
| `tcpdump` | The packet-viewing program. |
| `-i ens3` | Watch receiver's private-network card. |
| `-n` | Show numbers such as IP addresses and ports; do not replace them with names. |
| `tcp` | Show only TCP packets. |
| `port 80` | Show only web-server traffic. |

## Read the normal web request

You already captured this normal sequence:

```text
sender > receiver: Flags [S]
receiver > sender: Flags [S.]
sender > receiver: Flags [.]
sender > receiver: HTTP: HEAD / HTTP/1.1
receiver > sender: HTTP/1.1 200 OK
```

`[S]` is the first TCP SYN. `[S.]` means SYN plus ACK. `[.]` is the final ACK.
Those first three packets are the TCP handshake. Only then does `curl` send
the HTTP request and Nginx reply.

## Save a capture for Wireshark

Text is good for quick learning. A capture file is better when you want to
open the same packets later in Wireshark:

```bash
sudo tcpdump -ni ens3 -w receiver-web-test.pcap tcp port 80
```

Run one `curl` request, then press `Ctrl+C`. The `.pcap` file contains the
captured packets. Do not run a broad capture for a long time; start it only
for a short test with a clear filter.

