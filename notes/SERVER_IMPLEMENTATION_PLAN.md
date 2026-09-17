# Server Implementation Plan: the Receiver VM

This is the one note for the **server side** of the project. Work through it in order. Do not jump to the traffic experiment until the earlier checks work.

The lab is already isolated: the sender VM is `192.168.150.10` and the receiver VM is `192.168.150.20`. The receiver has Nginx, a web server, on TCP port `80`.

## 1. What we are actually building

We are **not** building a vulnerable web page or a program with a security bug.

We are using a normal web server and studying a temporary, controlled TCP availability weakness: too many connection attempts that never finish can fill the receiver's waiting area.

The finished receiver side has four parts:

```text
Linux TCP stack
    receives the first TCP connection messages
    keeps unfinished connection attempts in a short waiting queue
    applies or does not apply SYN-cookie protection

Nginx
    receives only completed connections
    serves a small, known web page on port 80

Our monitor program
    samples TCP states and machine health at regular times
    saves rows of evidence in a CSV file

Our baseline checker
    makes normal web requests and records whether they succeed and how long they take
```

The important separation is:

```text
TCP SYN arrives        -> Linux handles it
TCP handshake finishes -> Linux gives a connection to Nginx
HTTP request arrives   -> Nginx answers it
```

That means Nginx is the **healthy service we test**, but Linux is the part whose incomplete-connection queue we observe.

## 2. Tiny vocabulary you need first

### IP address

An IP address identifies a computer on a network.

- Sender VM: `192.168.150.10`
- Receiver VM: `192.168.150.20`

They are private addresses on this lab only. There is no route from these VMs to the internet.

### Port

One computer can run many network programs. A **port** identifies which program should receive traffic.

- Port `80` is the normal HTTP/web port.
- Nginx is waiting on port `80`.

The receiver address plus port is written as:

```text
192.168.150.20:80
```

### TCP handshake

A normal TCP connection begins with three messages:

```text
1. Client -> receiver: SYN        "May I connect?"
2. Receiver -> client: SYN-ACK    "Yes. Confirm it."
3. Client -> receiver: ACK        "Confirmed."
```

Only after message 3 can an ordinary web request reach Nginx.

### Half-open connection

If message 3 does not arrive, the receiver has a connection attempt that is **not finished**. Linux often shows this as `SYN-RECV`.

One or two such attempts are normal. A growing number is the signal this project studies.

### Backlog / waiting queue

The receiver cannot keep an unlimited number of unfinished attempts. It has a limited waiting area called a **backlog**. The exact Linux behavior is more complicated than one simple queue, but this mental model is good enough:

```text
SYN arrives -> waiting area -> handshake completes -> Nginx gets a connection
                         |
                         +-> unfinished attempts stay here temporarily
```

### SYN cookies

SYN cookies are a Linux defense. When queue pressure is high, Linux can avoid storing normal connection state for every incoming SYN. That helps legitimate clients still connect.

This project compares a controlled test condition with the defense disabled against the same condition with it enabled. It is not a permanent server setting.

## 3. The safety boundary

Do all experiments only when these facts are true:

- You are using `syn-sender` and `syn-receiver`.
- The target address is exactly `192.168.150.20`.
- The target port is exactly `80`.
- Each VM has only its isolated-network NIC.
- The sender program has a rate limit, a short duration, and a hard packet cap.
- You record the receiver's original settings before changing anything.
- You restore the original settings after every test session.

Never copy the experiment code to a public server, a home router, a campus system, or any target you do not own and isolate.

## 4. What code you will write locally first

Write and test the code in this project folder first. Do not begin by editing files inside the VM.

Create this small layout when you are ready:

```text
server/
  monitor.py
  baseline_client.py
  README.md
tests/
  test_monitor.py
  test_baseline_client.py
```

The names are intentional:

- `monitor.py` runs on the **receiver** and records its state.
- `baseline_client.py` runs on the **sender** and makes ordinary HTTP requests.
- `tests/` proves the parsing and CSV-writing logic without needing either VM.

You do not need a new web-server program. Nginx is already the web-server program.

## 5. Design `monitor.py` before writing it

Your monitor should answer one question repeatedly:

> At this moment, is Nginx healthy and how many TCP connection attempts are unfinished?

Each sample should make one CSV row with these columns:

```text
timestamp_utc,
nginx_active,
port_80_listening,
syn_recv_count,
established_count,
load_1m,
mem_available_kib
```

Plain meanings:

- `timestamp_utc`: when the sample was taken. UTC avoids time-zone confusion later.
- `nginx_active`: whether the Nginx service reports `active`.
- `port_80_listening`: whether something is waiting for new TCP connections on port 80.
- `syn_recv_count`: count of incomplete TCP handshakes visible at that instant.
- `established_count`: count of fully connected TCP connections visible at that instant.
- `load_1m`: a short recent measure of work Linux is handling. It is context, not proof by itself.
- `mem_available_kib`: memory that Linux says is available, measured in KiB.

### Suggested small functions

Keep each function responsible for one clear job. Do not make one giant function.

```text
run_command(command_parts) -> text
is_nginx_active(command_output) -> bool
is_port_80_listening(command_output) -> bool
count_syn_recv(command_output) -> int
count_established(command_output) -> int
read_load_1m(text_from_proc_loadavg) -> float
read_mem_available_kib(text_from_proc_meminfo) -> int
make_sample(...) -> dictionary
append_csv_row(csv_path, sample) -> nothing
```

`run_command` should use Python's `subprocess.run()` with a list of command parts, not a string passed through a shell. For example, the Python idea is a list such as `['ss', '-ant', 'state', 'syn-recv']`. That avoids shell quoting problems and makes tests easier.

### Monitor program flow

Write the top-level flow in this order:

```text
read command-line choices: output file and interval in seconds
create the output CSV and write its column names if it is new
repeat until the user stops the program:
    ask Linux whether Nginx is active
    ask Linux whether port 80 is listening
    ask Linux for SYN-RECV connections
    ask Linux for ESTABLISHED connections
    read load and memory from /proc
    build one sample dictionary
    append exactly one CSV row
    wait for the chosen interval
```

Start with an interval of one second. One row every second is easy to understand and usually enough for a small class experiment.

### Do not hide errors

If a command fails, save a clear value such as `error` or stop with a readable message. Never silently replace an error with `0`; zero unfinished connections and "could not measure" mean different things.

## 6. Design `baseline_client.py` before writing it

This is a normal client, not the SYN generator. Its job is to answer:

> Can a normal user still get the receiver's web page, and how long did that take?

For every request, save a CSV row:

```text
timestamp_utc,
request_number,
success,
latency_ms,
http_status,
error
```

Use Python's standard library `urllib.request` so your first version needs no downloaded packages.

Required behavior:

1. Accept a URL, number of requests, pause between requests, and timeout.
2. Measure time with `time.perf_counter()` before and after each request.
3. Treat a successful HTTP response as success and store its status, normally `200`.
4. Catch timeout and connection exceptions; record them as failures rather than crashing.
5. Always continue to the next request after one failure.

Start with a five-second timeout and one request every second. Those are baseline choices, not flood settings.

## 7. Tests to write before using a VM

You are finished with the first coding stage only when the following tests pass locally.

### Monitor tests

Feed saved example text into your parsing functions. Do not need a live Linux command for these tests.

Test that:

```text
an active service response becomes True
an inactive service response becomes False
a listening port-80 line becomes True
two SYN-RECV lines become 2
no SYN-RECV lines become 0
a malformed or error response does not pretend to be 0
one sample writes one CSV row with every required column
```

### Baseline-client tests

Do not make real web calls in unit tests. Replace the request operation with a fake success, fake HTTP error, and fake timeout.

Test that:

```text
a success row records True and a non-negative latency
a timeout row records False and the error text
one failure does not stop later requests
the CSV column names are correct
```

### Mental checkpoint

You should be able to explain this sentence before moving on:

> A unit test checks our code's choices with made-up input; a VM test checks whether Linux and the network behave as expected.

## 8. First receiver checks: no changes yet

Run these inside the **receiver VM** after you log in. Every command below reads information only unless the note explicitly says it creates a file.

### Check that Nginx is running

```bash
systemctl is-active nginx
```

- `systemctl` asks Linux about services.
- `is-active` asks whether a service is currently running.
- `nginx` is the name of the web-server service.

Expected result: `active`.

### Check what is waiting on TCP port 80

```bash
sudo ss -ltnp
```

- `sudo` runs this read-only inspection with administrator permission so the owning program can be shown.
- `ss` asks Linux to show sockets: network endpoints used by programs.
- `-l` means show only sockets waiting for new connections (listening sockets).
- `-t` means show TCP sockets only.
- `-n` means keep addresses and ports as numbers, such as `80`.
- `-p` means include the owning program, such as Nginx.

Expected result: a line containing `:80` and an Nginx process. This proves a program is waiting for web connections.

### Inspect the current SYN-cookie setting

```bash
sysctl net.ipv4.tcp_syncookies
```

- `sysctl` reads or changes certain running Linux-kernel settings.
- `net.ipv4.tcp_syncookies` is the exact setting name for IPv4 TCP SYN cookies.

Expected result: the setting name followed by `= 0` or `= 1`. This command only reads it.

### Inspect the incomplete-handshake limit

```bash
sysctl net.ipv4.tcp_max_syn_backlog
```

- `sysctl` reads the kernel setting.
- `net.ipv4.tcp_max_syn_backlog` is the maximum number of queued incomplete IPv4 TCP handshakes Linux will normally track.

Expected result: the setting name followed by a number. This command only reads it.

### See incomplete connections directly

```bash
ss -ant state syn-recv
```

- `ss` shows network sockets.
- `-a` means include all sockets, not only listening ones.
- `-n` keeps addresses and ports numeric.
- `-t` limits the view to TCP.
- `state` says the next word is a TCP state to filter by.
- `syn-recv` means incomplete handshakes where the receiver has sent SYN-ACK and awaits the final ACK.

Expected baseline result: normally only the heading line, or very few entries. This command only reads information.

## 9. Baseline experiment: prove the server is healthy

Do this before any TCP setting change and before running any traffic generator.

1. Start your receiver monitor. Let it write a file named something clear, for example `baseline-receiver.csv`.
2. On the sender VM, run your normal baseline client for 30 requests, one per second.
3. Stop the monitor after the client finishes.
4. Check the two CSV files.

Your expected baseline story is:

```text
Nginx stays active
port 80 stays listening
normal web requests mostly or all succeed
latency is fairly steady
SYN-RECV is usually zero or very small
```

If this is not true, stop here and fix the normal service. A broken baseline cannot prove an experiment result.

## 10. Copy code to the receiver VM with SCP

You will write and test code in this project folder, then copy only the receiver-side monitor to the receiver VM.

### Make a destination folder on the receiver

Run this inside the **receiver VM**. It creates folders inside your own home folder; it does not affect Nginx or system configuration.

```bash
mkdir -p ~/syn-lab-server/results
```

- `mkdir` means "make directory."
- `-p` means create missing parent folders too, and do not complain if the folders already exist.
- `~` means the current user's home folder; for user `recv`, that is normally `/home/recv`.
- `syn-lab-server` is the folder for your receiver-side project files.
- `results` is a child folder where CSV evidence will go.

### Copy the monitor from your main project folder

Run this on your **main computer**, inside this project folder. It copies one file; it does not delete or replace anything except a same-named destination file.

```bash
scp server/monitor.py recv@192.168.150.20:~/syn-lab-server/
```

- `scp` means secure copy. It transfers files through the same secure connection idea as SSH.
- `server/monitor.py` is the local file you are sending. It is relative to this project folder.
- `recv` is the username on the receiver VM.
- `@` separates the username from the VM address.
- `192.168.150.20` is the receiver VM's isolated address.
- `:` separates the remote computer from the destination path on it.
- `~/syn-lab-server/` is the receiver's destination folder. The trailing `/` means "put the file inside this directory."

### Run the monitor on the receiver

Run this inside the **receiver VM**. The exact command-line choices are your implementation's responsibility, but this is a good final shape:

```bash
python3 ~/syn-lab-server/monitor.py --output ~/syn-lab-server/results/baseline-receiver.csv --interval 1
```

- `python3` starts Python version 3.
- `~/syn-lab-server/monitor.py` is your monitor program on the receiver.
- `--output` is a named choice your program should implement.
- `~/syn-lab-server/results/baseline-receiver.csv` is where your program will create or append measurement rows.
- `--interval` is another named choice your program should implement.
- `1` means wait one second between samples.

Unlike earlier inspection commands, this command creates or changes the stated CSV file. Stop it with `Ctrl+C` after the test; your program should close the CSV cleanly when stopped.

### Copy evidence back to the main computer

Run this on your **main computer** in the project folder. It copies the result file from the receiver to a local folder you create for evidence.

```bash
scp recv@192.168.150.20:~/syn-lab-server/results/baseline-receiver.csv results/
```

- `scp` means secure copy.
- `recv@192.168.150.20:` identifies the source computer and begins its remote path.
- `~/syn-lab-server/results/baseline-receiver.csv` is the file on the receiver.
- `results/` is the local destination folder in the current project folder.

Create `results/` locally first if it does not exist. This is the local command:

```bash
mkdir -p results
```

- `mkdir` creates a folder.
- `-p` makes it safe to run again: it does not fail if `results` already exists.
- `results` is the new folder in the current project folder.

## 11. Packet capture: evidence of a normal handshake

Packet capture is optional while writing the programs, but it is strong evidence for the final report.

Run this inside the **receiver VM** while the sender makes a few normal web requests. It creates a `.pcap` capture file in your receiver results folder and stops automatically after 30 packets.

```bash
sudo tcpdump -ni ens3 -c 30 -w ~/syn-lab-server/results/normal-http.pcap 'tcp port 80'
```

- `sudo` gives the capture tool permission to read network packets.
- `tcpdump` is a packet-capture program.
- `-n` keeps addresses and port numbers numeric rather than trying to turn them into names.
- `-i ens3` chooses the receiver's network interface named `ens3`.
- `-c 30` stops after capturing 30 packets. This gives the capture a hard bound.
- `-w` means write packet data to a file rather than printing every packet to the screen.
- `~/syn-lab-server/results/normal-http.pcap` is the file it creates.
- `'tcp port 80'` is a filter: capture only TCP packets involving port 80. The quotes keep the whole filter together.

Expected evidence: a SYN, SYN-ACK, ACK, an HTTP request, and an HTTP response. Copy this file back with `scp` exactly as you copied the CSV, changing only the file name.

## 12. The controlled weak test condition: only after baseline works

This is not something to make permanent. The goal is a repeatable comparison:

```text
Condition A: controlled lower tolerance, SYN cookies off
Condition B: same test load, SYN cookies on
```

Before any change, record the original values in a plain-text file. Run this inside the **receiver VM**. It creates one evidence file in your own folder.

```bash
sysctl net.ipv4.tcp_syncookies net.ipv4.tcp_max_syn_backlog | tee ~/syn-lab-server/results/kernel-before.txt
```

- `sysctl` reads the two named kernel settings.
- `net.ipv4.tcp_syncookies` is the SYN-cookie setting.
- `net.ipv4.tcp_max_syn_backlog` is the incomplete-handshake queue setting.
- `|` passes the text printed by the command on its left into the command on its right. This is called a pipe.
- `tee` copies incoming text both to the screen and to a file.
- `~/syn-lab-server/results/kernel-before.txt` is the evidence file it creates.

The exact queue value for the controlled test should be chosen only after you have your baseline, monitor, and sender-side cap working. Start with a modest, documented value such as `16`; do not use this to chase the most disruption possible.

For the controlled condition, these commands change **running** kernel settings until the VM reboots or you restore them. Run them only inside the receiver VM and only during an agreed lab run:

```bash
sudo sysctl -w net.ipv4.tcp_syncookies=0
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=16
```

First command:

- `sudo` runs the setting change with administrator permission.
- `sysctl` controls a running kernel setting.
- `-w` means write/change the value rather than merely read it.
- `net.ipv4.tcp_syncookies=0` turns SYN-cookie protection off temporarily.

Second command:

- `sudo` grants permission to change the setting.
- `sysctl -w` changes a live kernel setting.
- `net.ipv4.tcp_max_syn_backlog=16` sets the incomplete-handshake queue limit to 16 for the controlled test.

Do not put these into `/etc/sysctl.conf`. We want an easy-to-undo experiment, not a permanently weakened VM.

### Restore immediately after the test

Read the two original numbers from `kernel-before.txt`. Then use those exact original numbers in these two command shapes:

```bash
sudo sysctl -w net.ipv4.tcp_syncookies=ORIGINAL_VALUE
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=ORIGINAL_VALUE
```

Here `ORIGINAL_VALUE` is a placeholder, not text to type literally. For example, if `kernel-before.txt` says `net.ipv4.tcp_syncookies = 1`, replace the first placeholder with `1`.

Finally, prove restoration by re-running the two read-only `sysctl` commands from section 8 and saving the output with your experiment evidence.

## 13. Experiment order once the sender tool exists

Use this same sequence for every rate level. Change only one thing at a time.

```text
1. Confirm Nginx is active.
2. Record current TCP settings.
3. Start receiver monitor.
4. Start normal baseline client on sender.
5. Start the sender's bounded, isolated-lab traffic test.
6. Keep the baseline client running during the short test.
7. Stop the traffic test at its planned cap or duration.
8. Stop monitor and collect CSV/PCAP evidence.
9. Restore settings immediately.
10. Verify normal web requests work again.
```

Record a row per run:

```text
run name,
SYN-cookie setting,
backlog setting,
sender rate limit,
sender packet cap,
duration,
maximum SYN-RECV seen,
normal requests attempted,
normal requests succeeded,
average latency,
notes
```

The result you are looking for is not "the server crashed." A good result is an understandable comparison: what changed in the receiver's observed TCP state and what happened to ordinary requests under the same bounded load.

## 14. What done looks like

You are done with the receiver/server part when all of this is true:

- Nginx is active and listens on port 80.
- Normal HTTP requests from sender work before and after every experiment.
- `monitor.py` has local unit tests and writes understandable CSV rows on the VM.
- `baseline_client.py` records normal success/failure and latency.
- You have one baseline CSV and one normal-handshake `.pcap`.
- Every test records its settings and sender cap.
- The controlled test setting is restored after every run.
- You can explain why a `SYN-RECV` entry belongs to Linux TCP, not to Nginx.

## 15. If something is wrong, use this order

Do not start changing many things at once.

```text
Cannot reach the page?
    Check Nginx says active.
    Check port 80 is listening.
    Check sender can ping receiver.

Monitor says zero all the time?
    Run the raw ss SYN-RECV command by hand.
    Save the exact output.
    Test the parser against that saved output locally.

Normal requests fail before the traffic test?
    Stop. This is a baseline problem, not an experiment result.

Experiment ends?
    Restore original TCP settings first.
    Then check Nginx and normal HTTP again.
```

Keep this principle throughout: **first make the normal case visible; then make one controlled change; then compare the evidence.**
