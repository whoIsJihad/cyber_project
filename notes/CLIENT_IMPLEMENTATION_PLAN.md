# Client Implementation Plan: the Sender VM

This is the one note for the **sender/client side** of the project. It matches `SERVER_IMPLEMENTATION_PLAN.md`, but focuses on what runs from the sender VM.

The sender VM is `192.168.150.10`. The receiver VM is `192.168.150.20`, and its normal web service is Nginx on TCP port `80`.

You will create two different client programs. Do not confuse them.

```text
Normal web client
    makes ordinary HTTP requests
    measures whether a real user can still reach the web page

Bounded TCP-SYN lab generator
    creates carefully limited TCP connection-start packets
    exists only to create controlled, isolated lab traffic
```

The normal client is evidence of user impact. The bounded generator is the condition being tested.

## 1. What the sender side should prove

The sender side answers two separate questions:

```text
Question 1: Is the receiver healthy during normal use?
    Answer: make normal web requests and record success and time.

Question 2: Under one controlled amount of incoming connection-start traffic,
what happens to the receiver and to normal web requests?
    Answer: run the short bounded generator while the normal web client continues.
```

The goal is not to make the receiver unusable. The goal is to collect a clear before-and-after comparison with a fixed cap and a recorded rate.

## 2. Sender-side mental model

### Normal connection

When a normal client opens a web page, the operating system does the TCP connection work:

```text
sender Linux -> SYN -> receiver Linux
sender Linux <- SYN-ACK <- receiver Linux
sender Linux -> ACK -> receiver Linux
sender program -> HTTP request -> Nginx
```

Your normal web client does not build these packets itself. Python and the sender's operating system do it for you.

### Controlled unfinished connection attempt

The later lab generator builds a SYN packet itself and sends it to the receiver. It does not complete that connection. The receiver may hold an incomplete connection attempt briefly and show it as `SYN-RECV`.

That is why this program needs more care than a normal web request: it works below the usual HTTP layer.

### The layers

```text
Your generator code
    chooses values and produces bytes

TCP header
    identifies the sending port, destination port, flags, and checksum

IPv4 header
    identifies the sender and receiver IP addresses

Raw socket
    asks Linux to transmit the IPv4/TCP bytes

Isolated lab network
    carries them only from sender VM to receiver VM
```

There is no need to create Ethernet bytes for the first raw-socket version. Linux handles the Ethernet layer when it transmits the IP packet on `ens3`.

## 3. Vocabulary you need

### Byte and hexadecimal

A byte is a number from `0` through `255`. Network headers are transmitted as bytes. Hexadecimal is just a convenient way to display those bytes:

```text
decimal 80 = hexadecimal 0x50
```

When you print packet data while debugging, print both its byte length and a hexadecimal form. It makes field boundaries visible.

### Network byte order

Internet protocols write multi-byte numbers with the most important byte first. This is called **big-endian** or **network byte order**.

For example, TCP port 80 is two bytes:

```text
00 50
```

Python's `struct.pack()` will make these bytes when you give it an appropriate big-endian format string.

### Source and destination

Every test packet has both:

```text
source IP:       192.168.150.10   sender VM only
destination IP:  192.168.150.20   receiver VM only
destination port: 80              Nginx web service only
```

Do not implement source-address spoofing. A normal fixed sender address makes the experiment explainable and keeps it confined to the lab.

### TCP flags

TCP has small on/off values called flags.

- `SYN` means "I want to begin a TCP connection."
- `ACK` means "I acknowledge receiving something."

For the generator's deliberately incomplete test packet, `SYN` is on and the other usual control flags are off.

### Checksum

A checksum is a small value that helps a receiver notice corrupted packet data.

The TCP checksum covers:

```text
a pseudo-header made from IP information
the TCP header
the TCP payload, if there is one
```

For the first SYN packet there is no TCP payload. Even with no payload, the pseudo-header is required for the TCP checksum.

## 4. Safety rules built into your code

Do not rely only on remembering to be careful. Put the safety limits in code.

Your generator should refuse to run unless all of these are true:

```text
target IP is exactly 192.168.150.20
target port is exactly 80
source IP is exactly 192.168.150.10
rate is positive and no higher than the small approved lab ceiling
duration is positive and no longer than the approved lab ceiling
packet cap is positive and no higher than the approved lab ceiling
dry-run is the default mode
```

Start with conservative choices such as:

```text
rate:        5 packets per second
duration:    5 seconds
packet cap:  25 packets
```

These are a first correctness check, not settings intended to cause a large effect. Increase only after a full baseline, with the receiver monitor running, and only one value at a time.

Also build these rules in:

- No hostnames: accept only the fixed numeric receiver address.
- No scanning: one destination address and one destination port.
- No unlimited mode.
- No command-line option that removes the hard cap.
- Print the final planned packet count before sending.
- Stop cleanly on `Ctrl+C` and report how many packets were actually sent.
- Record settings in a CSV or JSON evidence file next to each run.

## 5. Local project layout

Write and test all code in this project folder first. A clear first layout is:

```text
client/
  config.py
  checksum.py
  ipv4.py
  tcp.py
  packet.py
  dry_run.py
  generator.py
  normal_web_client.py
  README.md
tests/
  test_checksum.py
  test_ipv4.py
  test_tcp.py
  test_packet.py
  test_normal_web_client.py
```

Each file has one job:

- `config.py`: fixed lab address, port, and limits; checks that choices are safe.
- `checksum.py`: pure checksum calculation with no networking.
- `ipv4.py`: produces IPv4 header bytes.
- `tcp.py`: produces TCP header bytes and TCP-checksum input bytes.
- `packet.py`: joins a valid IPv4 header and valid TCP header into one IPv4 packet.
- `dry_run.py`: builds and displays a packet but never sends it.
- `generator.py`: only after dry-run tests pass, sends the already-built bytes with a hard cap.
- `normal_web_client.py`: makes ordinary web requests and measures them.

Do not start with `generator.py`. A wrong raw packet is hard to understand; a wrong byte string printed locally is easy to inspect.

## 6. Implement in this exact order

## Stage A: checksum only

Write one pure function:

```text
internet_checksum(data: bytes) -> int
```

Its job:

1. If `data` has an odd number of bytes, append one zero byte for the calculation only.
2. Read the bytes as 16-bit big-endian words.
3. Add the words.
4. Fold carry bits back into the low 16 bits until there is no carry.
5. Invert every bit and return the resulting 16-bit number.

It should not print, read a file, use a socket, or know anything about IP addresses. That makes it simple to test.

### Checkpoint A

You can explain:

> The checksum function turns bytes into one 16-bit value. It does not send a packet.

## Stage B: TCP header bytes, with checksum field initially zero

Write a function with clear input values:

```text
build_tcp_header_without_checksum(
    source_port,
    destination_port,
    sequence_number,
    window_size
) -> bytes
```

For the first version:

- source port: choose one non-privileged local port and keep it fixed while debugging;
- destination port: `80`;
- sequence number: use a documented test value while debugging;
- acknowledgement number: `0` because this is a SYN;
- data offset: `5`, meaning a 20-byte TCP header with no options;
- flags: SYN only;
- window size: choose a documented fixed value;
- urgent pointer: `0`;
- checksum: temporary zero until it is calculated.

The base TCP header without options is exactly 20 bytes. Assert that length in your code.

### Checkpoint B

Print the result in hexadecimal and identify, on paper, where the two destination-port bytes `00 50` appear.

## Stage C: IPv4 header bytes

Write a separate function:

```text
build_ipv4_header(
    source_ip,
    destination_ip,
    payload_length,
    identification
) -> bytes
```

For a first SYN packet:

- IP version: `4`;
- IHL: `5`, meaning 20 bytes and no IP options;
- total length: IPv4-header length plus TCP-header length;
- TTL: a fixed normal test value such as `64`;
- protocol: TCP, which is protocol number `6`;
- source IP: `192.168.150.10`;
- destination IP: `192.168.150.20`.

Set the IPv4 checksum field to zero, calculate the checksum of the IPv4 header, then write the real checksum into the header.

The base IPv4 header without options is exactly 20 bytes. Assert that length too.

### Checkpoint C

You can explain:

> IPv4 tells Linux where the packet goes. TCP tells the receiving computer which port and what kind of connection message it is.

## Stage D: TCP pseudo-header and real TCP checksum

The TCP checksum requires extra IP information, but the pseudo-header is **not** sent as part of the packet.

Make a function:

```text
build_tcp_pseudo_header(source_ip, destination_ip, tcp_length) -> bytes
```

It contains, in order:

```text
source IPv4 address:      4 bytes
destination IPv4 address: 4 bytes
zero byte:                1 byte
TCP protocol number:      1 byte (6)
TCP length:               2 bytes
```

Then calculate:

```text
internet_checksum(pseudo_header + tcp_header_with_zero_checksum)
```

Finally, rebuild or patch the TCP header with that checksum value. Do not calculate the checksum over the header containing its old checksum.

### Checkpoint D

You can explain:

> The pseudo-header is used only while calculating the TCP checksum. It does not become extra packet bytes.

## Stage E: one complete offline packet

Join the 20-byte IPv4 header and 20-byte TCP header:

```text
complete_packet = ipv4_header + tcp_header
```

The first packet should be 40 bytes in total:

```text
20-byte IPv4 header + 20-byte TCP header + 0-byte payload = 40 bytes
```

Do not send it yet. Make `dry_run.py` print:

```text
target IP and port
packet byte length
IPv4 header length
TCP header length
hexadecimal packet bytes
IPv4 checksum
TCP checksum
planned rate, duration, and hard cap
mode: DRY RUN -- nothing sent
```

### Checkpoint E

You can point to every field in your displayed bytes and explain why the packet is 40 bytes.

## Stage F: only then add bounded transmission

`generator.py` must call the same proven packet-building functions. It must not have a separate copy of header-building logic.

The sending loop idea is:

```text
validate fixed lab target and safety limits
build one correct SYN packet
calculate the time between packets from the rate
for each allowed packet number:
    stop if the duration has ended
    send exactly one packet
    count it only after send succeeds
    wait until the next scheduled time
write settings and actual count to an evidence file
```

Use a monotonic timer such as Python's `time.monotonic()` or `time.perf_counter()` for duration and timing. A wall-clock change should not accidentally lengthen a run.

The sender program will need elevated permission on the sender VM for a raw socket. Do not solve that by making everything run as administrator all the time. Run only the final bounded sender command with `sudo`, after dry-run and normal-client checks pass.

## 7. Tests you should have before a VM run

These tests should run on your main computer and should never send a packet.

### Checksum tests

Test:

```text
empty bytes return the expected checksum
an even-length known byte sequence returns its known checksum
an odd-length sequence is padded for calculation correctly
changing one input byte changes the checksum
```

Use a known checksum example from `notes/internet-checksums.md` rather than inventing an expected result.

### TCP-header tests

Test:

```text
header length is 20 bytes
destination port becomes bytes 00 50
SYN is the chosen flag
checksum is zero before calculation
checksum is nonzero after calculation for normal test data
```

### IPv4-header tests

Test:

```text
header length is 20 bytes
first byte means IPv4 plus 20-byte header
protocol field says TCP
source and destination bytes match the two lab IP addresses
total length is 40 for an empty-payload SYN
the header checksum validates
```

### Full-packet tests

Test:

```text
one no-payload packet is 40 bytes
packet begins with the IPv4 header
the TCP header begins at byte 20
unsafe destination address is rejected
unsafe destination port is rejected
rate, duration, or packet cap over the hard limits is rejected
dry-run never calls the send function
```

### Normal-web-client tests

Use fake request functions, not the real receiver VM, and test:

```text
a success makes a success CSV row
a timeout makes a failure row with an error message
one failure does not stop later requests
latency is recorded in milliseconds
```

## 8. First checks on the sender VM: information only

You know how to log into the sender VM. Run these commands **inside the sender VM**. They only inspect information.

### Check the sender's private address

```bash
ip -brief address show ens3
```

- `ip` is Linux's network-information program.
- `-brief` asks for a short, readable form of the result.
- `address` means show network addresses.
- `show` means display information; it does not change anything.
- `ens3` is the sender VM's network interface name.

Expected result: an IPv4 address containing `192.168.150.10`.

### Check the receiver can be reached normally

```bash
ping -c 3 192.168.150.20
```

- `ping` sends small reachability checks and waits for replies.
- `-c 3` means send exactly three checks, then stop. It prevents an endless command.
- `192.168.150.20` is the receiver VM's fixed lab address.

Expected result: three replies and a small summary. This sends only three normal diagnostic packets; it does not change configuration.

### Check normal HTTP before writing generator code

```bash
curl -I --connect-timeout 5 http://192.168.150.20
```

- `curl` makes a network request.
- `-I` asks only for HTTP response headers, not the entire web-page body.
- `--connect-timeout 5` gives the connection at most five seconds, so the check cannot wait forever.
- `http://` selects normal HTTP.
- `192.168.150.20` is the receiver VM.

Expected result: a line such as `HTTP/1.1 200 OK`. This makes one normal web request and does not change server configuration.

### Check which Python version exists

```bash
python3 --version
```

- `python3` starts or inspects Python 3.
- `--version` asks it to print the installed version then exit.

Expected result: a Python 3 version number. This command only reads information.

## 9. Copy code to the sender VM with SCP

### Make sender-side folders

Run this inside the **sender VM**. It creates folders inside your own home folder; it does not change the system or network.

```bash
mkdir -p ~/syn-lab-client/results
```

- `mkdir` means make directory.
- `-p` means make missing parent folders too and do not complain if they already exist.
- `~` means the home folder of the currently logged-in user, normally `/home/snd` on this VM.
- `syn-lab-client` is the folder for sender-side project files.
- `results` holds your evidence files.

### Copy sender code from the main project folder

Run this on your **main computer**, inside this project folder. It sends the local `client` folder to the sender VM.

```bash
scp -r client snd@192.168.150.10:~/syn-lab-client/
```

- `scp` means secure copy: it transfers files over an SSH-style secure connection.
- `-r` means copy a directory and everything inside it recursively.
- `client` is the local sender-code directory in this project folder.
- `snd` is the username on the sender VM.
- `@` separates the username from the VM address.
- `192.168.150.10` is the sender VM's isolated address.
- `:` separates the remote computer from the remote destination path.
- `~/syn-lab-client/` is the destination directory on the sender VM.

This can replace files with the same names at the destination. Use `git diff` and local tests before copying so you know exactly what version you are transferring.

### Run the dry-run on the sender first

Run this inside the **sender VM**. It should build and print packet bytes but must not send any packet.

```bash
python3 ~/syn-lab-client/client/dry_run.py
```

- `python3` runs Python 3.
- `~/syn-lab-client/client/dry_run.py` is the dry-run program copied to the sender.

Expected result: target, packet length, checksums, hexadecimal bytes, safety limits, and a clear message that nothing was sent. This command should not need `sudo` because it does not use a raw socket.

### Run the normal web client before any lab traffic test

Run this inside the **sender VM**. Your program should make ordinary web requests and create a result CSV.

```bash
python3 ~/syn-lab-client/client/normal_web_client.py --url http://192.168.150.20 --count 30 --interval 1 --timeout 5 --output ~/syn-lab-client/results/baseline-client.csv
```

- `python3` runs the program with Python 3.
- `~/syn-lab-client/client/normal_web_client.py` is your ordinary HTTP measurement program.
- `--url` is a named choice your code must implement.
- `http://192.168.150.20` is the receiver's normal web address. Port 80 is implied by `http`.
- `--count 30` means make 30 normal requests.
- `--interval 1` means wait one second between requests.
- `--timeout 5` means let each request wait at most five seconds before recording failure.
- `--output` names the CSV file your program creates.
- `~/syn-lab-client/results/baseline-client.csv` is that result file.

This sends ordinary TCP and HTTP requests. It should not need `sudo`.

### Copy results back to the main computer

First, on your **main computer** in the project folder, create a local evidence folder if it does not exist:

```bash
mkdir -p results
```

- `mkdir` creates a folder.
- `-p` makes it safe to run repeatedly.
- `results` is the local project folder for copied evidence.

Then copy the normal-client CSV:

```bash
scp snd@192.168.150.10:~/syn-lab-client/results/baseline-client.csv results/
```

- `scp` securely copies a file.
- `snd@192.168.150.10:` identifies the sender VM and begins the remote path.
- `~/syn-lab-client/results/baseline-client.csv` is the source file on the sender.
- `results/` is the local destination directory.

## 10. First bounded transmission: only after all earlier stages pass

Before this stage, confirm all of the following:

```text
The normal sender-to-receiver web check works.
The receiver monitor is running and writing its own CSV.
The normal web client is running and writing its own CSV.
The local checksum/header/full-packet tests all pass.
The dry-run packet length is 40 bytes and its fields are understood.
The generator validates its fixed lab target and hard limits.
```

For a very first implementation check, use the generator's lowest safe settings. The command shape should look like this, run inside the **sender VM**:

```bash
sudo python3 ~/syn-lab-client/client/generator.py --rate 5 --duration 5 --max-packets 25 --output ~/syn-lab-client/results/first-bounded-run.json
```

- `sudo` gives permission only for this command to create a raw network socket. A raw socket is needed because the program sends its own IPv4/TCP bytes.
- `python3` runs Python 3.
- `~/syn-lab-client/client/generator.py` is your already-tested, bounded sender program.
- `--rate 5` means plan at most five generated packets per second.
- `--duration 5` means stop after at most five seconds.
- `--max-packets 25` is an independent hard count limit. The program must stop when either the time or count limit is reached.
- `--output` names the evidence file.
- `~/syn-lab-client/results/first-bounded-run.json` is the result file it creates.

This is the only command in this note that intentionally generates custom TCP SYN traffic. Use it only on the isolated lab target and only after the checks above. The code must reject any different target or port.

After it exits, copy the evidence file back with the same SCP pattern as the baseline CSV. Then first verify normal HTTP works again before considering another run.

## 11. Evidence the sender must save

Each bounded run must save enough facts that someone else can reproduce and judge it:

```text
timestamp_utc
source IP
destination IP
destination port
rate limit
duration limit
packet cap
actual packets sent
actual elapsed seconds
stop reason: duration, cap, interrupt, or error
program version or Git commit, if available
```

The normal-web-client CSV should save:

```text
timestamp_utc
request number
success or failure
latency in milliseconds
HTTP status, when received
error message, when failed
```

You need both files for each experiment: the generator explains what was attempted; the normal-client data explains what a real user experienced.

## 12. Experiment sequence from the sender's point of view

For one test level, follow this exact order:

```text
1. Confirm the receiver's normal page responds to curl.
2. Start the receiver monitor.
3. Start normal_web_client.py for a fixed number of requests.
4. Wait for a few normal requests to succeed.
5. Run generator.py once with its fixed cap.
6. Let normal_web_client.py finish.
7. Check normal HTTP one more time.
8. Copy generator result and normal-client CSV back to the project.
9. Write one experiment-table row before changing any setting.
```

Change only one value between runs. For example, if you later compare rates, keep duration and the packet cap policy documented. If you compare SYN-cookie behavior, use exactly the same sender settings in both conditions.

## 13. What done looks like

You are done with the sender/client part when:

- You can explain the difference between the normal web client and the bounded generator.
- Your checksum and header functions have passing local tests.
- Dry-run prints a 40-byte IPv4/TCP SYN packet and sends nothing.
- The generator has fixed target validation, rate limit, duration limit, and a hard packet cap.
- The normal web client records success/failure and latency in a CSV.
- Every bounded run produces an evidence file with the actual packet count and stop reason.
- You can copy the two kinds of result file to and from the sender VM with SCP.
- You have verified normal web access again after each test.

## 14. If something breaks, stop in this order

```text
Dry-run bytes look wrong?
    Do not send them.
    Return to the checksum or header tests.

Normal HTTP fails before any generator run?
    Stop. This is a lab-service baseline problem.

Generator rejects your settings?
    Read the rejection message. It is a safety guard, not an error to remove.

Generator ends early?
    Read its stop reason and actual packet count in the evidence file.

Receiver seems unhealthy after a run?
    Stop all sender activity.
    Check normal HTTP again.
    Have the receiver side restore its original TCP settings before another run.
```

The guiding rule is: **build bytes offline, prove them with tests, dry-run them, run normal requests, then make one tiny bounded lab run while measuring both sides.**
