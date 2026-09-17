# Run the SYN lab

Run this one command from the project folder:

```bash
scripts/run_defense_comparison.sh
```

When it finishes, open only `results/defense-comparison-TIMESTAMP/RESULT.txt`.
Ignore CSV files unless something fails.

## What the three names mean

- **Baseline**: normal website, no fake SYN packets.
- **Protected**: fake SYN packets + SYN cookies on. Linux can answer extra SYNs without storing them.
- **Unprotected**: fake SYN packets + SYN cookies off. Linux drops extra SYNs after the waiting queue fills.

## Settings to change

At the top of `scripts/run_defense_comparison.sh`:

| Want | Change these values |
|---|---|
| Quick check, about 2–4 minutes | `trials_per_condition=1`, `syn_duration_seconds=10`, `syn_rate=1000`, `http_duration_seconds=10` |
| Full comparison, about 30–35 minutes | Leave the current values alone: `5`, `75`, `10000`, `30` |
| Gentler/slower SYN traffic | Lower `syn_rate`, for example `1000` packets/second. |
| More SYN pressure | Increase `syn_rate` or `syn_duration_seconds`; change only one at a time. |
| More normal users | Increase `http_concurrency`; keep it the same for every condition. |

`syn_rate` is fake SYN packets requested each second. `http_concurrency` is the number of normal HTTP requests allowed at once. Each normal HTTP request sends `Connection: close`, so it establishes its own TCP connection rather than reusing an earlier one.

## Kernel settings: where they come from

The script reads these from the **receiver VM** using `/usr/sbin/sysctl` before it changes anything:

| Setting | Plain meaning |
|---|---|
| `net.ipv4.tcp_syncookies` | `1`: use SYN cookies when the half-open waiting queue fills. `0`: drop extra SYNs instead. |
| `net.ipv4.tcp_max_syn_backlog` | The receiver's configured limit for ordinary unfinished TCP handshakes. |

For the comparison, the script temporarily uses `tcp_max_syn_backlog=16` and changes only `tcp_syncookies` between protected and unprotected. At the end it restores the original receiver values automatically.

## Read the result

`RESULT.txt` answers only these questions:

1. Did normal HTTP requests fail or time out?
2. Did latency become meaningfully worse?
3. Did Linux use cookies or drop excess SYNs?

If all HTTP requests succeed and latency stays close to baseline, the honest result is: **the SYN traffic reached Linux, but it did not visibly slow the website in this VM.**

Linux does not know which SYN is “fake.” The fake SYNs and normal user SYNs look normal to it. SYN cookies or drops are queue-handling rules, not fake-packet detection.
