# TCP SYN Flood Lab

For the automatic run, read [RUN_THIS.md](RUN_THIS.md).

## Manual fallback: run each program in the foreground

Use these machine names throughout this guide:

| Machine | Where it is | What runs there |
|---|---|---|
| **Host** | Your laptop, in the project folder | Copy code and collect results |
| **Server** | Nginx VM, `recv@192.168.150.20` | Settings and monitoring |
| **Client — SYN terminal** | Client VM, `snd@192.168.150.10` | SYN generator |
| **Client — HTTP terminal** | The same client VM, in a second terminal | Normal HTTP requests |

The client needs **two separate terminals** because the SYN generator must keep
running while HTTP requests run. The server needs one terminal. Use the host
terminal only for the copying steps at the beginning and end.

Keep both VMs on the existing isolated lab network. Stop any automatic experiment
before starting. All traffic below targets `192.168.150.20:80`.
There are no background jobs in this procedure. A busy terminal is expected:
leave its program running and move to the next terminal.

### 1. Host — copy the current code

Run from the project folder on your host, before opening the three VM terminals:

```bash
cd /mnt/Data/4-1/syn-flood-dos-project
scp -r client snd@192.168.150.10:/home/snd/
scp -r server recv@192.168.150.20:/home/recv/
```

`scp -r` copies each directory and its contents to the matching VM. This updates
the VM copies of the code; it does not start the experiment.

### 2. Server — prepare Nginx and settings

On the **Server**, run:

```bash
cd ~
mkdir -p ~/syn-lab-server/results/manual
/usr/sbin/sysctl -n net.ipv4.tcp_syncookies > ~/syn-lab-server/results/manual/original-syncookies.txt
/usr/sbin/sysctl -n net.ipv4.tcp_max_syn_backlog > ~/syn-lab-server/results/manual/original-syn-backlog.txt
systemctl is-active nginx
ss -ltn 'sport = :80'
sudo /usr/sbin/sysctl -w net.ipv4.tcp_syncookies=1 net.ipv4.tcp_max_syn_backlog=16
```

Expect `active` and a `LISTEN` row on port 80. Stop here if either is missing.
`mkdir -p` creates the results directory if needed. `sysctl -n` reads a setting;
`>` saves it to a file. **Run the save commands once, before changing settings.**
For a later separate experiment, archive the `manual` directory first; otherwise
these commands and the HTTP outputs reuse existing filenames.

`sudo sysctl -w` temporarily changes the running server settings. The value
`16` reproduces the existing comparison script; it is not a promise that the
observed queue will contain exactly 16 entries. We restore both original values
at the end. No persistent kernel configuration is edited.

### 3. Client — prepare both terminals

In the **Client — HTTP terminal**, run:

```bash
cd ~
mkdir -p ~/results/manual
```

In the **Client — SYN terminal**, also run `cd ~`. Both client terminals
must be on `snd@192.168.150.10`, not on the server or host.
Python's `-m` runs the named module from the copied project directories.

### 4. Baseline — no SYN generator

**Server:** save the starting counters and start monitoring:

```bash
nstat -az > ~/syn-lab-server/results/manual/baseline-before.txt
python3 -m server.monitor --interval 0.5 --output ~/syn-lab-server/results/manual/baseline-monitor.csv
```

`nstat -az` reads absolute network counters, including zero-valued counters.
The monitor writes port-80 connection counts and server health to CSV about
every half second. Leave it running; it does not print each sample.

**Client — HTTP terminal:** measure normal HTTP access:

```bash
python3 -m client.sustained_http_load --url http://192.168.150.20:80/ --duration 20 --timeout 2 --concurrency 20 --output ~/results/manual/baseline-http.csv
```

This runs 20 HTTP workers for about 20 seconds, with a 2-second timeout per
request. Each request opens a new TCP connection. `--output` names the CSV file.
Wait for the success-count message and the shell prompt to return.

**Server:** press **Ctrl+C** to stop monitoring, then run:

```bash
nstat -az > ~/syn-lab-server/results/manual/baseline-after.txt
```

### 5. Protected trial — SYN cookies enabled

**Server:**

```bash
sudo /usr/sbin/sysctl -w net.ipv4.tcp_syncookies=1
nstat -az > ~/syn-lab-server/results/manual/protected-before.txt
python3 -m server.monitor --interval 0.5 --output ~/syn-lab-server/results/manual/protected-monitor.csv
```

**Client — SYN terminal:** start the SYN generator and leave it running:

```bash
sudo python3 -m client.generator --continuous --rate 1000
```

`sudo` permits raw-packet sending. `--continuous` keeps sending until you press
Ctrl+C in the client SYN terminal. `--rate 1000` requests 1,000 packets/second; actual speed
is printed when stopped. Leave the SYN generator running through the whole HTTP measurement.

**Client — HTTP terminal:** after roughly 5 seconds, while the client SYN generator is still running, run:

```bash
python3 -m client.sustained_http_load --url http://192.168.150.20:80/ --duration 20 --timeout 2 --concurrency 20 --output ~/results/manual/protected-http.csv
```

**Overlap check:** the client SYN generator must remain running from the start
to the end of the HTTP test. If the SYN generator has already printed its summary and returned to the prompt, this is not a
complete HTTP-under-flood measurement. Do not interpret it as one.

After the client HTTP test finishes, press **Ctrl+C in the Client — SYN terminal** to stop sending and print the summary.
Then press **Ctrl+C on the Server** and run:

```bash
nstat -az > ~/syn-lab-server/results/manual/protected-after.txt
```

There is no queue-drain wait in this workflow. Leftover half-open connections
can carry into subsequent trials, so they are not fully independent comparisons.

### 6. Unprotected trial — SYN cookies disabled

**Server:**

```bash
sudo /usr/sbin/sysctl -w net.ipv4.tcp_syncookies=0
nstat -az > ~/syn-lab-server/results/manual/unprotected-before.txt
python3 -m server.monitor --interval 0.5 --output ~/syn-lab-server/results/manual/unprotected-monitor.csv
```

**Client — SYN terminal:**

```bash
sudo python3 -m client.generator --continuous --rate 1000
```

**Client — HTTP terminal:** after roughly 5 seconds, while the client SYN generator is still running:

```bash
python3 -m client.sustained_http_load --url http://192.168.150.20:80/ --duration 20 --timeout 2 --concurrency 20 --output ~/results/manual/unprotected-http.csv
```

Again, leave the client SYN generator running for the whole HTTP measurement.
After the client HTTP test finishes, press **Ctrl+C in the Client — SYN terminal**,
then **Ctrl+C on the Server**, and run on the server:

```bash
nstat -az > ~/syn-lab-server/results/manual/unprotected-after.txt
```

### 7. Server — restore settings

Do this after the experiment, **including if you stop early**. If a program is
still running, stop it with Ctrl+C in its own terminal first.

```bash
sudo /usr/sbin/sysctl -w net.ipv4.tcp_syncookies="$(cat ~/syn-lab-server/results/manual/original-syncookies.txt)" net.ipv4.tcp_max_syn_backlog="$(cat ~/syn-lab-server/results/manual/original-syn-backlog.txt)"
/usr/sbin/sysctl net.ipv4.tcp_syncookies net.ipv4.tcp_max_syn_backlog
```

`$(cat ...)` inserts each saved original value. Check that the printed values
match the saved files. If either file is missing, stop and check your original
settings rather than guessing a replacement.

**Client — HTTP terminal:** confirm ordinary HTTP still works:

```bash
python3 -m client.sustained_http_load --url http://192.168.150.20:80/ --duration 5 --timeout 2 --concurrency 1 --output ~/results/manual/recovery-http.csv
```

### 8. Host — collect the evidence

Run from the project folder on your host:

```bash
manual_results="results/manual-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$manual_results/client" "$manual_results/server"
scp -r snd@192.168.150.10:/home/snd/results/manual/. "$manual_results/client/"
scp -r recv@192.168.150.20:/home/recv/syn-lab-server/results/manual/. "$manual_results/server/"
echo "$manual_results"
```

The timestamp creates a separate local results folder. Client HTTP CSVs contain
success, latency, HTTP status, and error fields. Server monitor CSVs contain
the port-80 `syn_recv_count`. Compare before/after `nstat` values, especially
`TcpExtSyncookiesSent` and `TcpExtListenDrops`; these counters are machine-wide,
not port-specific. This manual procedure does not generate `RESULT.txt`.

Completion checklist:

- Baseline, protected, and unprotected HTTP CSVs were saved.
- Both SYN trials visibly overlapped their entire HTTP measurement.
- SYN sending was stopped after each HTTP measurement.
- Server settings were restored and recovery HTTP succeeded.
- Client and server evidence was copied to the host.

A run with no HTTP failures or slowdown is still a valid result **if overlap
was verified**. Half-open connections or increased drop counters alone do not
prove HTTP service degradation.
