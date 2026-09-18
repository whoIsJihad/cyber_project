# Moving From the 2-VM Lab to the 3-Device Hotspot Evaluation

This guide adapts the existing isolated 2-VM lab (`syn-sender` 192.168.150.10 /
`syn-receiver` 192.168.150.20) to the supervisor's final evaluation setup:
three physical devices on one shared Wi-Fi hotspot, one per role.

## 0. Roles → devices

| Role | What runs there |
|---|---|
| **Server** | nginx + `server/monitor.py` (local TCP-state/health sampler) |
| **Attacker** | `client/generator.py` (needs root, raw socket) |
| **Monitor** | `client/normal_web_client.py` / `sustained_http_load.py` (simulates real users) + pulls the server's evidence + prints the verdict |

## 1. Build the hotspot and find real addresses

1. Turn on the phone's hotspot, join it from the server and attacker laptops.
2. On **each** of the 3 devices, in its own terminal:
   ```bash
   ip -brief address
   ```
   Record each device's real IP (phone hotspots are usually `192.168.43.0/24`
   on Android, but read the actual value — don't assume).
3. **Check for AP client isolation** before anything else — this silently
   breaks everything if it's on. From the attacker:
   ```bash
   ping -c 3 <server-ip>
   ```
   From the server:
   ```bash
   ping -c 3 <attacker-ip>
   ping -c 3 <monitor-ip>
   ```
   All must succeed. Most personal phone hotspots allow client-to-client
   traffic by default, but some Android versions have an "isolate clients"
   toggle — turn it off if pings fail.
4. Check the phone's "connected devices" list and confirm it's exactly your
   3 devices — nobody else should be on this network while spoofed-source
   traffic is flowing.

## 2. Install prerequisites (native Linux, both server and attacker)

**SERVER:**
```bash
sudo apt update
sudo apt install nginx python3 iproute2 iputils-ping tcpdump openssh-server sysstat
sudo systemctl enable --now nginx
sudo ufw allow 80/tcp
sudo ufw allow OpenSSH
```
`nstat` (used by the comparison script) comes from `iproute2`, already
included.

**ATTACKER:**
```bash
sudo apt update
sudo apt install python3 iproute2 openssh-server
```
Check no firewall is dropping the raw egress traffic (unlikely to matter for
outbound spoofed packets, but confirm nothing unusual):
```bash
sudo ufw status
```

**MONITOR:**
```bash
sudo apt install python3 openssh-client
```

## 3. Edit the hardcoded lab addresses

Hand-edit these constants before the demo — using `<SERVER_IP>` for the
server's real hotspot address and `<HOTSPOT_SUBNET>` for its `/24` (e.g.
`192.168.43.0/24`):

**`client/generator.py`**
- Line 24 — `SOURCE_NETWORK = ipaddress.ip_network("192.168.150.128/25")` →
  pick an unused half of the real hotspot subnet, e.g.
  `ipaddress.ip_network("192.168.43.128/25")`. Confirm via the phone's
  connected-devices list and a quick `arp -a` on the server that nothing
  already lives in that range.
- Line 27 — `DESTINATION_IP_BYTES = b"\xC0\xA8\x96\x14"` → the packed bytes of
  `<SERVER_IP>` (e.g. for `192.168.43.20` that's `b"\xC0\xA8\x2B\x14"`).
- Line 29 — `DESTINATION_IP_TEXT = "192.168.150.20"` → `"<SERVER_IP>"`.
- Everywhere `192.168.150.20`/`80` appears in print strings (lines 182,
  216) — cosmetic, update for clarity.

**`client/normal_web_client.py`**
- Line 13 — `DEFAULT_URL = "http://192.168.150.20/"` → `"http://<SERVER_IP>/"`.

**`scripts/run_defense_comparison.sh`** — only if you use it (see step 8):
- Lines 14–15 — `sender="snd@192.168.150.10"` /
  `receiver="recv@192.168.150.20"` → the real users/IPs on your Linux
  laptops.
- Lines 19–20 — the hardcoded sudo passwords → your real ones.
- Line 46 — `nginx_site_conf` path — confirm it matches your nginx install
  (Debian/Ubuntu default is correct as-is).

No other code needs source-IP/host changes — `server/monitor.py` only calls
local commands (`systemctl`, `ss`, `/proc`), so it's location-independent.

## 4. Baseline first, always

On **MONITOR**:
```bash
python3 -m client.normal_web_client --url http://<SERVER_IP>/ --count 100 --pause 0.05 --concurrency 5 --output results/baseline-http.csv
```
Confirm 100/100 succeed with low, stable latency before touching the
attacker. This is your "before" evidence.

## 5. Run one attack trial, three terminals at once

**SERVER** — start the health sampler:
```bash
mkdir -p ~/syn-lab-server/results
python3 -m server.monitor --interval 0.2 --output ~/syn-lab-server/results/monitor-trial1.csv
```
(leave running; `Ctrl+C` stops it later)

Optional, same terminal or a second one on the server, for packet-level
proof:
```bash
sudo tcpdump -ni <iface> -w ~/syn-lab-server/results/trial1.pcap 'tcp port 80'
```

**ATTACKER** — start conservative, in its own terminal (don't wrap this in
SSH — type it directly):
```bash
sudo python3 -m client.generator --duration 20 --rate 50 --workers 2
```
Watch the printed actual send rate. Only scale up (`--rate 200`, more
`--workers`) once you've confirmed packets are arriving (check the server's
tcpdump/`ss` output) — Wi-Fi adds latency and a phone hotspot has real
bandwidth limits, so don't jump straight to the lab's
`--rate 1000 --workers 8`.

**MONITOR** — during the attack window, run the same HTTP probe as your
baseline:
```bash
python3 -m client.normal_web_client --url http://<SERVER_IP>/ --count 100 --pause 0.05 --concurrency 5 --output results/attack-http.csv
```

Also useful, typed directly into MONITOR's own terminal (a live SSH session
you're driving by hand, not scripted automation):
```bash
ssh <server-user>@<SERVER_IP> 'TERM=xterm watch -n0.5 "ss -Hnt state syn-recv | wc -l"'
```

## 6. Stop and collect evidence

- `Ctrl+C` the attacker, then the server's `monitor.py` and `tcpdump`.
- Pull the server's CSV/pcap onto the monitor device:
  ```bash
  scp <server-user>@<SERVER_IP>:~/syn-lab-server/results/monitor-trial1.csv results/
  ```

## 7. The monitor's verdict — what "successful SYN flood" means here

On MONITOR, compare `baseline-http.csv` vs `attack-http.csv`, and inspect
`monitor-trial1.csv`'s `syn_recv_count` column. Call it a **confirmed SYN
flood effect** only if you see the combination:

- `syn_recv_count` spikes and stays near nginx's listen backlog during the
  attack window, **and**
- either HTTP latency/failure rate rises in `attack-http.csv` (service
  degraded) **or**, if it doesn't, `nstat`'s `TcpExtSyncookiesSent` /
  `TcpExtListenDrops` counters rise sharply (packets arrived and were
  handled/dropped even though the defense kept HTTP healthy — this is the
  "attack landed, defense worked" story your existing `results-backup` runs
  already demonstrate).

Don't claim impact from packet generation alone — `STATE.md` already flags
this distinction as the thing not to skip.

## 8. Optional: reuse the automated comparison script

`scripts/run_defense_comparison.sh` still works as a coordinator (run it from
the monitor device, SSH'd into attacker+server) once you've made the edits in
step 3 above, to reproduce the baseline/protected/unprotected three-way
comparison automatically instead of by hand. Given the preference for typing
directly into each machine, treat it as optional/backup rather than the
primary demo path.

**One safety note:** keep the spoofed-source pool and target strictly
confined to your own 3 devices' subnet, and don't leave the attack running
unattended on a shared hotspot — stop it as soon as evidence is captured.
