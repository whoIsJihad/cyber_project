# How to run everything Report/report.tex needs

This is the one checklist to follow to produce every screenshot, CSV, and
table cell the report references. It assumes the **3-laptop hotspot setup**:
one laptop is the **Server** (nginx + `server/monitor.py`, and `defense.py`
when needed), one is the **Attacker** (`client/generator.py`), and one is the
**Monitor** (a separate laptop that only sends plain HTTP requests, standing
in for a real user). Server is `10.42.0.81`, attacker is `10.42.0.157`,
spoofed sources come from `10.42.0.192/26` — all already hardcoded in
`client/generator.py`. The Monitor laptop's IP is whatever the hotspot gives
it; substitute your real value everywhere `<MONITOR_IP>` appears below.

Do the trials in this order. Each one maps to a specific figure/table cell in
the report, noted under "Report needs" below its heading.

## 0. One-time setup (all three laptops)

1. Turn on the phone/router hotspot, connect all three laptops to it.
2. On each laptop, find its real IP:
   ```bash
   ip -brief address
   ```
   Server must be `10.42.0.81`, attacker must be `10.42.0.157` (if your
   hotspot assigned different addresses, edit `client/generator.py` — lines
   ~26-31: `SOURCE_NETWORK`, `DESTINATION_IP_BYTES`, `DESTINATION_IP_TEXT`).
   Note the Monitor's IP — that's your `<MONITOR_IP>`.
3. Check the access point doesn't isolate clients (from the attacker and from
   the monitor, both pinging the server):
   ```bash
   ping -c 3 10.42.0.81
   ```
   Must succeed from both — if it doesn't, turn off "AP/client isolation" on
   the hotspot device.
4. On the **server**: nginx installed and running, listening on port 80:
   ```bash
   sudo apt install -y nginx
   sudo systemctl enable --now nginx
   systemctl is-active nginx        # expect: active
   ss -ltn 'sport = :80'            # expect: a LISTEN row
   ```
5. On the **server**, shrink nginx's listen backlog so the flood can actually
   overflow it (see `notes/WHAT_WAS_WRONG_AND_HOW_WE_FIXED_IT.md` for why this
   step is required — the kernel sysctl alone does nothing on a running
   nginx):
   ```bash
   sudo cp /etc/nginx/sites-available/default /tmp/nginx-default.bak
   sudo sed -i -E 's/ ?backlog=[0-9]+//g; s/(listen [^;]*80[^;]*);/\1 backlog=8;/' /etc/nginx/sites-available/default
   grep -n listen /etc/nginx/sites-available/default   # confirm backlog=8 shows up
   sudo nginx -t
   sudo systemctl restart nginx
   ss -ltn 'sport = :80'
   ```
   The `grep` only proves the *config file* says `backlog=8` — it doesn't prove
   the *running* nginx actually picked it up (that's the exact mistake from
   before: `reload` silently keeps the old queue size). The `ss -ltn` line
   after the restart is the real proof: for a LISTEN socket, its `Send-Q`
   column **is** the configured backlog. If it doesn't read `8`, the restart
   didn't take — stop and fix this before running any trial, or every result
   after it is invalid.
6. On all three laptops, from the project root, make a results folder
   (skip if you're editing in place on each machine already):
   ```bash
   mkdir -p results
   ```
7. Save the server's original kernel settings so you can restore them at the
   very end (step 8):
   ```bash
   sysctl -n net.ipv4.tcp_syncookies > /tmp/original-syncookies.txt
   sysctl -n net.ipv4.tcp_max_syn_backlog > /tmp/original-syn-backlog.txt
   ```

**Report needs:** Figure "topology" (`figures/topology.png`) is just a
network diagram of this setup (server + attacker + monitor + spoofed-source
pool) — draw it by hand or in any diagram tool, it's not a captured
screenshot.

**Where files end up:** every `results/*-http.csv` file is written on the
**Monitor** laptop (that's where the probe runs); every `results/*-monitor.csv`
and `nstat`/`tcpdump` file is written on the **Server**. You'll need both sets
in one place before filling the report table or building the plot — that's
step 6 (collect) and step 7 (plot) below. `scp` between the laptops if you've
got SSH set up, otherwise a USB stick or `python3 -m http.server` + a browser
download both work fine for a handful of CSVs. Do this transfer once at the
end, not after every trial.

## 1. Baseline trial — no attack

**Server** (health sampler, leave running):
```bash
python3 -m server.monitor --interval 0.5 --output results/baseline-monitor.csv
```

**Monitor** (the "real user" probe, its own laptop, own IP):
```bash
python3 -m client.sustained_http_load --url http://10.42.0.81/ \
        --duration 20 --timeout 2 --concurrency 10 --output results/baseline-http.csv
```

When it finishes, `Ctrl+C` the Server's monitor.

**Report needs:** Table 1, row "Baseline" — open `results/baseline-http.csv`
and compute:
- success rate = count where `success` is `True`, out of total rows
- median latency = median of `latency_ms` column
- timeouts = count where `error` mentions "timed out" / "timeout"

## 2. Unprotected trial — attack, SYN cookies OFF

**Server, terminal 1** — disable cookies, then start monitoring:
```bash
sudo sysctl -w net.ipv4.tcp_syncookies=0
nstat -az > /tmp/unprotected-before.txt
python3 -m server.monitor --interval 0.5 --output results/attack-monitor.csv
```

**Server, terminal 2** — packet capture (find your interface name first with
`ip -brief address`, e.g. `wlan0`):
```bash
sudo tcpdump -ni <iface> 'tcp port 80 and tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0'
```
Screenshot this window a few seconds into the flood → **`server_tcpdump.png`**.

**Server, terminal 3** — live half-open count:
```bash
watch -n0.5 'ss -Hnt state syn-recv "( sport = :80 )" | wc -l'
```
Screenshot once it's climbing/near 8 → **`server_ss_synrecv.png`**.

**Attacker** — start the flood:
```bash
sudo python3 -m client.generator --continuous --rate 1000 --workers 8
```
Screenshot this terminal (it prints sent count, requested vs. actual rate) →
**`attacker_generator.png`**.

**Monitor** — once the flood has been running ~5 seconds, run the probe
*while the flood keeps running*:
```bash
python3 -m client.sustained_http_load --url http://10.42.0.81/ \
        --duration 20 --timeout 2 --concurrency 10 --output results/attack-http.csv
```
While this runs and shows failures/timeouts, screenshot it →
**`victim_http_fail.png`**.

**After the HTTP probe finishes:** `Ctrl+C` the attacker, then `Ctrl+C` the
Server's monitor (terminal 1) and `watch` (terminal 3), then on the Server:
```bash
nstat -az > /tmp/unprotected-after.txt
```

**Report needs:**
- Table 1, row "Unprotected (attack)" — same three numbers as step 1, computed
  from `results/attack-http.csv`.
- Section (b) fallback evidence — diff the two `nstat` snapshots for
  `TcpExtListenDrops`:
  ```bash
  diff /tmp/unprotected-before.txt /tmp/unprotected-after.txt | grep -E "ListenDrops|SyncookiesSent"
  ```

## 3. Protected trial — attack, SYN cookies ON

Same as step 2, but flip cookies on and use fresh output filenames:

**Server, terminal 1:**
```bash
sudo sysctl -w net.ipv4.tcp_syncookies=1
nstat -az > /tmp/protected-before.txt
python3 -m server.monitor --interval 0.5 --output results/protected-monitor.csv
```

**Attacker:**
```bash
sudo python3 -m client.generator --continuous --rate 1000 --workers 8
```

**Monitor**, after ~5 seconds:
```bash
python3 -m client.sustained_http_load --url http://10.42.0.81/ \
        --duration 20 --timeout 2 --concurrency 10 --output results/protected-http.csv
```

Stop the attacker, then the Server's monitor, then on the Server:
```bash
nstat -az > /tmp/protected-after.txt
diff /tmp/protected-before.txt /tmp/protected-after.txt | grep -E "SyncookiesSent|ListenDrops"
```
Screenshot the `nstat`/diff output showing `TcpExtSyncookiesSent` rising while
`attack-http`/`protected-http` succeeded → **`syncookies_nstat.png`**.

**Report needs:** Table 1, row "Protected: SYN cookies" — same three numbers,
from `results/protected-http.csv`.

## 4. `defense.py` demo — per-source blocking (and its collateral damage)

This is a **separate** trial from steps 2-3; run it with cookies in whatever
state you like (the report's point here is about blocking, not cookies), but
keep it consistent — cookies **on** is simplest so you're isolating the
`defense.py` effect:

**Server:**
```bash
sudo sysctl -w net.ipv4.tcp_syncookies=1
sudo python3 -m server.defense --interval 0.5 --threshold 5 \
     --block-seconds 30 --output results/defense-events.csv
```
Leave it running — it prints a line every time it blocks a source.

**Attacker:**
```bash
sudo python3 -m client.generator --continuous --rate 1000 --workers 8
```

Because the generator holds each spoofed IP for many packets before rotating
to the next, `defense.py` should start blocking spoofed addresses within a
few seconds — screenshot the Server terminal showing a `blocked <ip>` line →
**`defense_block.png`**.

**Monitor**, at the same time, run its normal probe against the server, same
as every other trial:
```bash
python3 -m client.sustained_http_load --url http://10.42.0.81/ \
        --duration 20 --timeout 2 --concurrency 10 --output results/defense-http.csv
```
This is your "legitimate user" during this trial. Because `defense.py` counts
half-open connections per source IP from `ss` — not by telling spoofed traffic
apart from real traffic — the Monitor's own IP can trip the same threshold if
its handshakes get delayed under load and pile up in `syn-recv`. Check
`results/defense-events.csv` (and the Server's terminal) for a block entry
whose IP matches the Monitor's real address — that's the "it also blocks
legitimate users" evidence the report needs. If it doesn't trigger at
`--threshold 5`, either lower the threshold or raise the Monitor's
`--concurrency` and re-run; don't fabricate the block if it genuinely didn't
happen — report a null result honestly if that's what you observe.

Stop the attacker, then `Ctrl+C` `defense.py`.

**Important cleanup:** `defense.py` only removes a block automatically when
its own `--block-seconds` cooldown elapses *while the script is still
running*. If you `Ctrl+C` it before that happens, any active `iptables` DROP
rules stay in place forever — including one against the Monitor's own IP if
it got blocked. Check and clear them before moving on:
```bash
sudo iptables -L INPUT -n --line-numbers | grep DROP
```
If any of your lab IPs show up, remove that rule by its line number:
```bash
sudo iptables -D INPUT <line-number>
```
Confirm the Monitor can reach the server again before continuing.

## 5. `syn_cookies.py` demo — the stateless mechanism itself

No attack traffic needed for this one — it's a self-contained demonstration,
runnable on either machine:
```bash
python3 -m server.syn_cookies --connections 1000
```
It prints: legitimate ACKs accepted, a forged cookie rejected, an expired
cookie rejected, and "half-open entries stored: 0". Screenshot the full
output → **`syncookies_demo.png`**.

## 6. Collect everything onto one machine

Before you can fill the report table or build the plot, gather every result
file onto whichever machine you're editing `Report/report.tex` on (this may
be a 4th personal laptop, or one of the three — doesn't matter, just pick one
and call it "host" below).

From the Monitor, copy the HTTP CSVs (`baseline-http.csv`, `attack-http.csv`,
`protected-http.csv`, `defense-http.csv`); from the Server, copy the monitor
CSVs (`baseline-monitor.csv`, `attack-monitor.csv`, `protected-monitor.csv`),
`defense-events.csv`, and the four `nstat` snapshot files. If SSH is set up
between the laptops:
```bash
scp <monitor-user>@<MONITOR_IP>:~/path/to/project/results/*-http.csv results/
scp <server-user>@10.42.0.81:~/path/to/project/results/{*-monitor.csv,defense-events.csv} results/
```
Otherwise a USB stick, or `python3 -m http.server 8000` on the source machine
and a `curl`/browser download from the host, both work fine for this many
small CSVs.

## 7. Build the plot

**Report needs:** `figures/monitor_csv_plot.png` — `syn_recv_count` over time,
baseline vs. attack. There's no existing plotting script for this, so once
`baseline-monitor.csv` and `attack-monitor.csv` are both in `results/` on the
host, run a short one-off:
```bash
python3 - <<'PY'
import csv
import matplotlib.pyplot as plt
from datetime import datetime

def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    t0 = datetime.fromisoformat(rows[0]["timestamp_utc"])
    xs = [(datetime.fromisoformat(r["timestamp_utc"]) - t0).total_seconds() for r in rows]
    ys = [int(r["syn_recv_count"]) for r in rows]
    return xs, ys

bx, by = load("results/baseline-monitor.csv")
ax, ay = load("results/attack-monitor.csv")

plt.plot(bx, by, label="baseline")
plt.plot(ax, ay, label="attack (unprotected)")
plt.xlabel("seconds")
plt.ylabel("syn_recv_count")
plt.title("Half-open connections over time")
plt.legend()
plt.tight_layout()
plt.savefig("Report/figures/monitor_csv_plot.png", dpi=150)
PY
```
(`pip install matplotlib` first if it's not already installed.)

## 8. Restore the server's settings

**Always do this last**, even if you stopped early:
```bash
sudo sysctl -w net.ipv4.tcp_syncookies="$(cat /tmp/original-syncookies.txt)" \
              net.ipv4.tcp_max_syn_backlog="$(cat /tmp/original-syn-backlog.txt)"
sudo cp /tmp/nginx-default.bak /etc/nginx/sites-available/default
sudo systemctl restart nginx
sysctl net.ipv4.tcp_syncookies net.ipv4.tcp_max_syn_backlog   # confirm restored
```
Confirm the site still serves normally:
```bash
python3 -m client.sustained_http_load --url http://10.42.0.81/ \
        --duration 5 --timeout 2 --concurrency 1 --output results/recovery-http.csv
```

## Checklist of what you now have

Screenshots (`Report/figures/`):
- [ ] `topology.png` (hand-drawn diagram, 3 laptops: server / attacker / monitor)
- [ ] `attacker_generator.png` (step 2)
- [ ] `server_tcpdump.png` (step 2)
- [ ] `server_ss_synrecv.png` (step 2)
- [ ] `victim_http_fail.png` (step 2, on the Monitor)
- [ ] `syncookies_nstat.png` (step 3)
- [ ] `defense_block.png` (step 4)
- [ ] `syncookies_demo.png` (step 5)
- [ ] `monitor_csv_plot.png` (step 7)

Data (`results/`, collected from Server + Monitor per step 6):
- [ ] `baseline-http.csv` (Monitor), `baseline-monitor.csv` (Server)
- [ ] `attack-http.csv` (Monitor), `attack-monitor.csv` (Server)
- [ ] `protected-http.csv` (Monitor), `protected-monitor.csv` (Server)
- [ ] `defense-http.csv` (Monitor), `defense-events.csv` (Server)
- [ ] Table 1's three rows filled in `Report/report.tex` from the CSVs above
- [ ] `nstat` before/after diffs for unprotected and protected trials, for the
      "why it succeeded / SyncookiesSent rose" claims in §(b) and §(d)

Then recompile:
```bash
cd Report && pdflatex report.tex && pdflatex report.tex
```
(run twice so the table of contents and figure references resolve).
