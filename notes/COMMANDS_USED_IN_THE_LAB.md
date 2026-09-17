# The Commands Used in This Lab, in Plain English

This note explains the commands we have used so far. It is intentionally about
the basic actions first: copying files, sending packets, watching the receiver,
and reading a saved capture.

There are three computers involved:

```text
Main computer     where this project folder exists
syn-sender        the VM that runs the Python generator
syn-receiver      the VM that runs Nginx and observes incoming traffic
```

Always notice the prompt before running a command:

```text
jihad$                 main computer
snd@syn-sender:~$      sender VM
recv@syn-receiver:~$   receiver VM
```

## 1. Copy the current code to the sender VM

Run this on the **main computer**, inside the project folder:

```bash
scp -r client snd@192.168.150.10:~/
```
f
Read it from left to right:

| Part | Meaning |
|---|---|
| `scp` | Secure copy. It copies files through the same encrypted connection as SSH. |
| `-r` | Recursive. It copies the whole folder and everything inside it. |
| `client` | The local folder to copy, relative to the project folder. |
| `snd@192.168.150.10:` | Log in as user `snd` on the sender VM. The colon means the path after it is on that remote VM. |
| `~/` | The sender user's home folder. The copy becomes `~/client`. |

It asks for the password of `snd` because it is logging into the sender VM.
v
### Why you delete the old `client` folder first

If `~/client` already exists, copying the whole `client` folder into `~/` can
create a nested folder such as `~/client/client`. That is not what we want.

Your current refresh method is correct. Run this on **syn-sender** first:

```bash
rm -rf ~/client
```

Then run the `scp` command above on the **main computer**.

`rm` means remove. `-r` means remove a folder and its contents recursively.
`-f` means do not ask questions. This command is destructive, but here its
target is exactly the disposable sender copy at `~/client`.

After copying, verify the result on **syn-sender**:

```bash
ls ~/client
```

Expected: files such as `generator.py`, `packet.py`, and `__init__.py`.

## 2. Run the generator

Run this on **syn-sender**:

```bash
cd ~
sudo python3 -m client.generator --count 10 --rate 10
```

| Part | Meaning |
|---|---|
| `cd ~` | Move to the sender user's home folder. This makes the `client` folder visible as a Python package. |
| `sudo` | Run the following command with administrator permission. Raw sockets need this permission. |
| `python3` | Start Python 3. |
| `-m client.generator` | Run `generator.py` as part of the `client` package. This preserves the code's imports. |
| `--count 10` | Build and send ten SYN packets. |
| `--rate 10` | Send at ten packets per second. |

The current lab generator uses:

```text
fake source IP:       192.168.150.99
receiver IP and port: 192.168.150.20:80
source ports:         20000 upward, one different port per packet
```

Different source ports matter. TCP identifies a connection using source IP,
source port, destination IP, and destination port. Changing the source port
makes each generated SYN a separate connection attempt.

## 3. Capture packets with tcpdump

Run this on **syn-receiver** before sending packets:

```bash
sudo tcpdump -ni ens3 -c 20 -w ~/syn-lab-server/results/dummy-source-syn.pcap 'tcp port 80'
```

| Part | Meaning |
|---|---|
| `sudo` | Packet capture needs administrator permission. |
| `tcpdump` | Program that watches packets crossing a network interface. |
| `-n` | Keep IP addresses and ports as numbers. Do not replace them with names. |
| `-i ens3` | Watch the receiver VM's private-network card, named `ens3`. |
| `-c 20` | Stop automatically after saving 20 matching packets. It counts all packets matching the filter, not just packets from Python. |
| `-w file.pcap` | Save packet bytes into a `.pcap` file instead of printing each one live. |
| `'tcp port 80'` | Capture only TCP traffic involving Nginx's web port 80. Quotes make the whole filter one argument. |

When tcpdump says `listening on ens3`, it is ready. It looks like it is frozen,
but it is waiting for packets.

With the dummy source `.99`, tcpdump should show the incoming SYN packets. It
may not show SYN-ACK replies because the receiver cannot find an Ethernet/MAC
address for `.99` and cannot transmit the reply. That is expected in this
specific test.

Press `Ctrl+C` if you want to stop a capture before it reaches its limit.

### Read a saved capture

Run this on **syn-receiver**:

```bash
tcpdump -nn -r ~/syn-lab-server/results/dummy-source-syn.pcap
```

| Part | Meaning |
|---|---|
| `-r file.pcap` | Read a capture file instead of listening live. |
| `-nn` | Keep both addresses and ports numeric. |

Example line:

```text
IP 192.168.150.99.20004 > 192.168.150.20.80: Flags [S], length 0
```

It means the fake client `.99`, using port `20004`, asked the receiver's web
port 80 to begin a TCP connection. `[S]` means SYN. `length 0` means the packet
contains no web-page data; it is only the connection-start request.

## 4. Watch half-open connections with `ss`

Run this on **syn-receiver**:

```bash
TERM=xterm watch -n 0.5 'ss -Hnt state syn-recv'
```

| Part | Meaning |
|---|---|
| `TERM=xterm` | Work around the VM not knowing the `xterm-kitty` terminal type. |
| `watch` | Re-run a command and redraw the screen repeatedly. |
| `-n 0.5` | Refresh every half second. |
| `ss` | Linux program that displays socket and TCP connection state. |
| `-H` | Hide the column headings. |
| `-n` | Keep addresses and ports numeric. |
| `-t` | Show TCP entries. |
| `state syn-recv` | Show only server entries waiting for the final TCP ACK. |

Press `Ctrl+C` to stop `watch`.

An entry looks like this:

```text
0  0  192.168.150.20:80  192.168.150.99:20004
```

It means:

```text
receiver web service        fake client that has not finished TCP setup
192.168.150.20:80     <--   192.168.150.99:20004
```

The first two zeroes are receive and send queue data counters. They are zero
because this is not an established web connection carrying data. The important
fact is that the line exists: it is one temporary, half-open TCP connection.

The rows disappear after a while because Linux times out unanswered connection
attempts. That cleanup is normal.

## One small, understandable run

Use three terminals:

1. **Receiver terminal A:** start the tcpdump capture.
2. **Receiver terminal B:** start the `ss` watch command.
3. **Sender terminal:** run the generator once.

Then read the result in this order:

```text
sender says it sent N SYN packets
        ↓
tcpdump shows N incoming SYN packets
        ↓
ss shows temporary SYN-RECV entries
        ↓
Linux eventually removes them after timeout
```

For the first test, stop after understanding those four facts. Do not increase
the count merely because a command prints many lines.
