"""Print a report from an existing comparison CSV; no VM access."""

import csv
from collections import defaultdict
from pathlib import Path
import statistics
import sys

rows = list(csv.DictReader(Path(sys.argv[1]).open(encoding="utf-8", newline="")))
groups = defaultdict(list)
for row in rows:
    groups[row["condition"]].append(row)
print("SYN LAB RESULT")
print("These are typical results across the completed trials.")
print("No queue-drain waits: later trials may include leftover half-open connections.")
for condition in ("baseline", "protected", "unprotected"):
    group = groups[condition]
    values = lambda name: [float(row[name]) for row in group]
    total = statistics.median(values("total"))
    success = statistics.median(values("success"))
    failed = statistics.median(values("failed"))
    timeouts = statistics.median(values("timeouts"))
    median_ms = statistics.median(values("median_ms"))
    p95_ms = statistics.median(values("p95_ms"))
    peak = statistics.median(values("peak_syn_recv"))
    cookies = statistics.median(values("syncookies_sent"))
    drops = statistics.median(values("listen_drops"))
    print(f"\n{condition.upper()}")
    print(f"  Web requests: {success:.0f}/{total:.0f} succeeded; {failed:.0f} failed; {timeouts:.0f} timed out.")
    print(f"  Latency: usually {median_ms:.2f} ms; slower requests reached {p95_ms:.2f} ms.")
    if condition == "protected":
        print(f"  Linux kept about {peak:.0f} unfinished connections and sent about {cookies:.0f} SYN cookies.")
    elif condition == "unprotected":
        print(f"  Linux kept about {peak:.0f} unfinished connections and dropped about {drops:.0f} extra SYNs.")

protected_failures = statistics.median([float(row["failed"]) for row in groups["protected"]])
unprotected_failures = statistics.median([float(row["failed"]) for row in groups["unprotected"]])
print("\nPLAIN CONCLUSION")
if protected_failures == 0 and unprotected_failures == 0:
    print("Normal HTTP stayed available. Cookies handled excess SYNs when enabled; Linux dropped excess SYNs when disabled.")
else:
    print("At least one condition caused HTTP failures. Compare that condition with BASELINE above.")
print("Ignore comparison.csv unless you are debugging a failed or unusual run.")
