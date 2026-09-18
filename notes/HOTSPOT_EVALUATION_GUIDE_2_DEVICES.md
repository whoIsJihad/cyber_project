# Moving From the 3-Device Hotspot Evaluation to a 2-Device Version

This adapts `HOTSPOT_EVALUATION_GUIDE.md` (server / attacker / monitor, three
physical devices) down to **two** physical devices on one shared Wi-Fi
hotspot: the server absorbs the monitor role and evaluates itself.

Read the 3-device guide first if you haven't — this file only calls out what
changes. Everything it doesn't mention (checking client isolation, editing
hardcoded lab addresses, the safety note about the spoofed-IP pool) still
applies exactly as written there.

## 0. Roles → devices

| Role | What runs there |
|---|---|
| **Server** (also acts as monitor) | nginx, `server/monitor.py`, optionally `server/defense.py`, **and** the HTTP probe (`client/normal_web_client.py` / `sustained_http_load.py`) that used to run on a separate monitor device |
| **Attacker** | `client/generator.py` (needs root, raw socket) |

The only real change from the 3-device setup: the HTTP probe that
represents "a real user" now runs *on the server itself*, addressed at the
server's own hotspot IP (not `localhost`/`127.0.0.1`) so the request still
goes out through the real network interface and back in, rather than taking
a loopback shortcut that could hide effects you want to observe. Everything
else about the probe (what it measures, how to read it) is unchanged.

**Trade-off to note in your write-up:** because the "user" and the "server"
are the same physical machine, the HTTP probe's CPU/network load competes
with nginx and the monitor/defense scripts for the same machine's resources.
Keep the probe's `--concurrency` modest (see step 4) so the probe itself
isn't the reason latency rises — you want the *attack* to be the cause, not
contention with your own measurement tooling.

## 1. Build the hotspot and find real addresses

Same as the 3-device guide, just for 2 devices:

1. Turn on the phone's hotspot, join it from both laptops.
2. On **each** device:
   ```bash
   ip -brief address
   ```
   Record the server's real hotspot IP (`<SERVER_IP>`).
3. Check for AP client isolation:
   ```bash
   # from the attacker
   ping -c 3 <SERVER_IP>
   ```
   Must succeed. Turn off "isolate clients" on the phone if it fails.
4. Confirm the phone's connected-devices list shows exactly these 2 devices.

## 2. Install prerequisites

**SERVER** (needs everything the old server *and* monitor devices needed,
since it now does both jobs):
```bash
sudo apt update
sudo apt install nginx python3 iproute2 iputils-ping tcpdump openssh-server sysstat
sudo systemctl enable --now nginx
sudo ufw allow 80/tcp
sudo ufw allow OpenSSH
```

**ATTACKER** — unchanged from the 3-device guide:
```bash
sudo apt update
sudo apt install python3 iproute2 openssh-server
sudo ufw status
```

## 3. Edit the hardcoded lab addresses

Same edits as the 3-device guide's step 3, with one simplification: skip the
`normal_web_client.py` `DEFAULT_URL` edit if you're always passing `--url`
explicitly (recommended, since you'll run it locally on the server — see
step 4).

**`client/generator.py`** (on the attacker's copy):
- Line 24 — `SOURCE_NETWORK` → an unused half of the real hotspot subnet.
- Line 27 — `DESTINATION_IP_BYTES` → packed bytes of `<SERVER_IP>`.
- Line 29 — `DESTINATION_IP_TEXT` → `"<SERVER_IP>"`.

`scripts/run_defense_comparison.sh` is **not** used in this 2-device setup —
it's built around two separate SSH hosts (`sender`/`receiver`). Run the steps
below by hand instead; see the note at the end if you want to adapt it.

## 4. Baseline first, always

Run this **on the server itself**, addressed at its own hotspot IP:
```bash
python3 -m client.normal_web_client --url http://<SERVER_IP>/ --count 100 --pause 0.05 --concurrency 5 --output results/baseline-http.csv
```
Confirm 100/100 succeed with low, stable latency before touching the
attacker. Keep `--concurrency` at 5 here — this is a baseline, not a load
test of your own machine.

## 5. Run one attack trial — two terminals on the server, one on the attacker

**SERVER, terminal 1** — health sampler:
```bash
mkdir -p results
python3 -m server.monitor --interval 0.2 --output results/monitor-trial1.csv
```
(leave running; `Ctrl+C` stops it later)

**SERVER, terminal 2** — optional packet capture:
```bash
sudo tcpdump -ni <iface> -w results/trial1.pcap 'tcp port 80'
```

**ATTACKER** — its own terminal, typed directly (not through SSH):
```bash
sudo python3 -m client.generator --duration 20 --rate 50 --workers 2
```
Start conservative and only scale up (`--rate 200`, more `--workers`) once
you've confirmed packets are landing (watch `ss -Hnt state syn-recv` output
in a spare server terminal) — a phone hotspot has real bandwidth limits.

**SERVER, terminal 3** — the "monitor" probe, run during the attack window:
```bash
python3 -m client.normal_web_client --url http://<SERVER_IP>/ --count 100 --pause 0.05 --concurrency 5 --output results/attack-http.csv
```

Optional, a spare server terminal, live view of the queue:
```bash
watch -n0.5 "ss -Hnt state syn-recv | wc -l"
```

## 6. Optional: exercise the active defense (`server/defense.py`)

The 3-device guide's comparison script only tests the kernel's
`tcp_syncookies`. If you want to demonstrate the app-level defense discussed
in `DEFENSE_EXPLAINED.md`, run it in a fourth server terminal **instead of**
(or alongside, on a different port setup) the plain `monitor.py` run above,
started before the attack:
```bash
python3 -m server.defense --interval 1 --port 80 --threshold 5 --block-seconds 30 --output results/defense-trial1.csv
```
Then repeat step 5's attacker command and step 4/5's HTTP probe. Because the
attack generator (see `client/generator.py`) holds each spoofed source IP for
tens of thousands of packets before rotating to the next one, the per-IP
threshold should trigger and block quickly — watch for `blocked <ip>` lines
in this terminal, and cross-check `results/defense-trial1.csv` afterwards.

Run this as a **separate trial** from the plain-monitor trial in step 5, not
at the same time — you want a clean "attack with no defense" trial to
compare against an "attack with defense" trial, the same way the 3-device
comparison script contrasts `unprotected` vs. `protected`.

## 7. Stop and collect evidence

- `Ctrl+C` the attacker, then the server's `monitor.py`/`defense.py` and
  `tcpdump`.
- No `scp` needed — everything is already local under `results/` on the
  server, since the server is also the monitor.

## 8. The verdict — what "successful SYN flood" (and "successful defense")
   means here

Same criteria as the 3-device guide: compare `baseline-http.csv` against
`attack-http.csv`, and inspect `monitor-trial1.csv`'s `syn_recv_count`
column. Call it a **confirmed SYN flood effect** only if `syn_recv_count`
spikes and stays near nginx's listen backlog **and** either HTTP
latency/failure rises, or `nstat`'s `TcpExtSyncookiesSent` /
`TcpExtListenDrops` counters rise sharply. Don't claim impact from packet
generation alone.

If you ran step 6, call it a **confirmed defense effect** if the
attack-with-defense trial's `attack-http.csv` stays close to baseline (low
latency, high success rate) while `defense-trial1.csv` shows `block` events
correlated with the attack window — i.e. HTTP stayed healthy *because* the
offending IPs got firewalled, not by coincidence.

## 9. Optional: adapting the automated comparison script

`scripts/run_defense_comparison.sh` assumes two remote hosts reachable over
SSH (`sender` sends the attack + HTTP load, `receiver` runs nginx/monitor).
To reuse it for a 2-device setup, you'd need to replace every
`ssh "$receiver" "..."` / `sudo_receiver "..."` call with a plain local
command (since the server is now both `$receiver` and the probe origin) —
this is a non-trivial rewrite, not a config edit, so treat manual testing
(steps 4-8 above) as the primary path and only invest in this if you need
repeated automated trials.

**Safety note**, unchanged from the 3-device guide: keep the spoofed-source
pool and target confined to your own 2 devices' subnet, and don't leave the
attack running unattended on a shared hotspot.
