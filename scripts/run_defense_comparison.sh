#!/usr/bin/env bash

# WHAT THIS SCRIPT DOES (in order)
# 1. Saves the receiver's current SYN-cookie and queue-limit settings.
# 2. Copies the current client/server code to the two isolated lab VMs.
# 3. Repeats baseline, protected, and unprotected conditions five times each.
# 4. Rotates their order so time alone cannot favour one condition.
# 5. Uses the same small half-open queue limit for every comparison trial.
# 6. Starts the receiver monitor for each trial.
# 7. Each SYN trial requests 750,000 SYNs: 10,000/second for 75 seconds.
# 8. Waits up to 20 seconds for a cookie/drop counter to prove pressure.
# 9. Runs HTTP for 30 seconds: 20 workers, no pause, request count varies.
# 10. Saves HTTP, monitor, generator, and TCP-counter evidence per trial.
# 11. Writes every trial to comparison.csv and median results to summary.txt.
# 12. Expected total time is about 30–35 minutes, including VM overhead.
# 13. Restores the receiver's original kernel settings before exiting.
# A missed pressure check is recorded; it does not cancel the remaining trials.

# Compare no-SYN, SYN-cookie, and no-cookie conditions in the isolated lab.
# Run from the project root. This script changes only running receiver kernel
# settings and restores their original values when it exits.
set -euo pipefail

sender="snd@192.168.150.10"
receiver="recv@192.168.150.20"
# Lab-only convenience credentials supplied by the lab owner. They are used
# solely to answer sudo prompts on the isolated VMs; do not reuse this script
# outside this coursework network or commit these values to a shared repository.
sender_sudo_password="1234"
receiver_sudo_password="12345678"
sender_results="/home/snd/results"
receiver_results="/home/recv/syn-lab-server/results"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
local_results="results/defense-comparison-$run_id"

# One HTTP shape, repeated rather than many short concurrent profiles.
trials_per_condition=2 #5 default
http_duration_seconds=20 #30 default
http_concurrency=20
http_timeout_seconds=2

# Same SYN workload in protected and unprotected trials.
syn_duration_seconds=7 #75 default  
syn_rate=100000 #10000 default 
pressure_gate_timeout_seconds=20
generator_finish_timeout_seconds=180

# A small queue makes the defense choice observable. It is restored on exit.
comparison_syn_backlog=16

original_syncookies=""
original_syn_backlog=""
current_monitor_pid=""
current_generator_pid=""

mkdir -p "$local_results"

read_sysctl() {
    ssh "$receiver" "/usr/sbin/sysctl -n $1"
}

read_counter() {
    ssh "$receiver" "nstat -az | awk '\$1 == \"$1\" { print \$2; exit }'"
}

sudo_receiver() {
    ssh "$receiver" "printf '%s\\n' '$receiver_sudo_password' | sudo -S -p '' $1"
}

stop_trial_processes() {
    if [[ -n "$current_monitor_pid" ]]; then
        ssh "$receiver" "kill $current_monitor_pid 2>/dev/null || true" || true
        current_monitor_pid=""
    fi
    if [[ -n "$current_generator_pid" ]]; then
        ssh "$sender" "kill $current_generator_pid 2>/dev/null || true" || true
        current_generator_pid=""
    fi
}

wait_for_generator() {
    local deadline=$((SECONDS + generator_finish_timeout_seconds))
    while ssh "$sender" "kill -0 $current_generator_pid 2>/dev/null"; do
        if (( SECONDS >= deadline )); then
            echo "Generator did not finish within ${generator_finish_timeout_seconds}s." >&2
            return 1
        fi
        sleep 1
    done
    current_generator_pid=""
}

restore_kernel_settings() {
    if [[ -n "$original_syncookies" && -n "$original_syn_backlog" ]]; then
        echo "Restoring receiver kernel settings..."
        sudo_receiver "/usr/sbin/sysctl -w net.ipv4.tcp_syncookies=$original_syncookies net.ipv4.tcp_max_syn_backlog=$original_syn_backlog" || true
    fi
}

cleanup() {
    stop_trial_processes
    restore_kernel_settings
}
trap cleanup EXIT INT TERM

wait_for_pressure() {
    local condition="$1"
    local before_counter="$2"
    local counter_name
    local deadline=$((SECONDS + pressure_gate_timeout_seconds))

    if [[ "$condition" == "protected" ]]; then
        counter_name="TcpExtSyncookiesSent"
    else
        counter_name="TcpExtListenDrops"
    fi

    local last_counter="$before_counter"
    while (( SECONDS < deadline )); do
        local now_counter
        now_counter="$(read_counter "$counter_name")"
        last_counter="$now_counter"
        if [[ "$now_counter" =~ ^[0-9]+$ ]] && (( now_counter > before_counter )); then
            echo "Pressure gate passed: $counter_name rose from $before_counter to $now_counter."
            return 0
        fi
        sleep 1
    done

    echo "Pressure gate did not pass for $condition within ${pressure_gate_timeout_seconds}s; $counter_name stayed at $last_counter. Continuing and recording this trial." >&2
    return 1
}

summarize_trial() {
    local trial_dir="$1"
    python3 - "$trial_dir" <<'PY'
import csv
import math
from pathlib import Path
import statistics
import sys

trial_dir = Path(sys.argv[1])
rows = list(csv.DictReader((trial_dir / "http.csv").open(encoding="utf-8", newline="")))
latencies = sorted(float(row["latency_ms"]) for row in rows)
successes = sum(row["success"] == "True" for row in rows)
timeouts = sum("timeout" in row["error"].lower() or "timed out" in row["error"].lower() for row in rows)
p95 = latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else 0
peak_syn_recv = max((int(row["syn_recv_count"]) for row in csv.DictReader((trial_dir / "monitor.csv").open(encoding="utf-8", newline=""))), default=0)
before = {}
after = {}
for path, target in ((trial_dir / "nstat-before.txt", before), (trial_dir / "nstat-after.txt", after)):
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            target[parts[0]] = int(parts[1])
cookie_change = after.get("TcpExtSyncookiesSent", 0) - before.get("TcpExtSyncookiesSent", 0)
drop_change = after.get("TcpExtListenDrops", 0) - before.get("TcpExtListenDrops", 0)
print(f"{len(rows)},{successes},{len(rows)-successes},{timeouts},{statistics.median(latencies) if latencies else 0:.2f},{p95:.2f},{peak_syn_recv},{cookie_change},{drop_change}")
PY
}

original_syncookies="$(read_sysctl net.ipv4.tcp_syncookies)"
original_syn_backlog="$(read_sysctl net.ipv4.tcp_max_syn_backlog)"
printf 'original_syncookies=%s\noriginal_syn_backlog=%s\ncomparison_syn_backlog=%s\n' "$original_syncookies" "$original_syn_backlog" "$comparison_syn_backlog" > "$local_results/kernel-settings.txt"
printf 'condition,trial,pressure_gate,total,success,failed,timeouts,median_ms,p95_ms,peak_syn_recv,syncookies_sent,listen_drops\n' > "$local_results/comparison.csv"

echo "Refreshing current client and server code on both isolated VMs..."
ssh "$sender" 'rm -rf ~/client; mkdir -p ~/results'
ssh "$receiver" "pkill -f '[s]erver.monitor' 2>/dev/null || true; rm -rf ~/server; mkdir -p $receiver_results"
scp -r client "$sender:/home/snd/"
scp -r server "$receiver:/home/recv/"

conditions=(baseline protected unprotected)
for trial in $(seq 1 "$trials_per_condition"); do
    # Rotate the order. Time-related VM variation therefore cannot always
    # favour one condition merely because it ran first or last.
    for offset in 0 1 2; do
        condition="${conditions[$(((trial - 1 + offset) % 3))]}"
        trial_dir="$local_results/$condition-trial-$trial"
        mkdir -p "$trial_dir"
        echo "Running $condition trial $trial of $trials_per_condition..."

        # Baseline and protected both use the same small backlog. The only
        # defense difference between protected and unprotected is syncookies.
        syncookies=1
        [[ "$condition" == "unprotected" ]] && syncookies=0
        sudo_receiver "/usr/sbin/sysctl -w net.ipv4.tcp_syncookies=$syncookies net.ipv4.tcp_max_syn_backlog=$comparison_syn_backlog"
        ssh "$receiver" "nstat -az >$receiver_results/nstat-before-$run_id-$condition-$trial.txt"

        current_monitor_pid="$(ssh "$receiver" "cd ~; nohup python3 -m server.monitor --interval 0.1 --output $receiver_results/monitor-$run_id-$condition-$trial.csv </dev/null >/tmp/monitor-$run_id-$condition-$trial.log 2>&1 & echo \$!")"
        [[ "$current_monitor_pid" =~ ^[0-9]+$ ]] || { echo "Receiver monitor did not start." >&2; exit 1; }
        sleep 1

        pressure_gate="not-required"
        if [[ "$condition" != "baseline" ]]; then
            if [[ "$condition" == "protected" ]]; then
                gate_counter="$(read_counter TcpExtSyncookiesSent)"
            else
                gate_counter="$(read_counter TcpExtListenDrops)"
            fi
            current_generator_pid="$(ssh "$sender" "printf '%s\\n' '$sender_sudo_password' | sudo -S -p '' sh -c 'cd /home/snd && exec nohup python3 -m client.generator --duration $syn_duration_seconds --rate $syn_rate >/tmp/generator-$run_id-$condition-$trial.log 2>&1' & echo \$!")"
            [[ "$current_generator_pid" =~ ^[0-9]+$ ]] || { echo "SYN generator did not start." >&2; exit 1; }
            if wait_for_pressure "$condition" "$gate_counter"; then
                pressure_gate="passed"
            else
                pressure_gate="not-observed"
            fi
        fi

        ssh "$sender" "cd ~; python3 -m client.sustained_http_load --duration $http_duration_seconds --timeout $http_timeout_seconds --concurrency $http_concurrency --output $sender_results/http-$run_id-$condition-$trial.csv"
        if [[ "$condition" != "baseline" ]]; then
            wait_for_generator
        fi
        stop_trial_processes
        ssh "$receiver" "nstat -az >$receiver_results/nstat-after-$run_id-$condition-$trial.txt"

        scp "$sender:$sender_results/http-$run_id-$condition-$trial.csv" "$trial_dir/http.csv"
        scp "$receiver:$receiver_results/monitor-$run_id-$condition-$trial.csv" "$trial_dir/monitor.csv"
        scp "$receiver:$receiver_results/nstat-before-$run_id-$condition-$trial.txt" "$trial_dir/nstat-before.txt"
        scp "$receiver:$receiver_results/nstat-after-$run_id-$condition-$trial.txt" "$trial_dir/nstat-after.txt"
        if [[ "$condition" != "baseline" ]]; then
            scp "$sender:/tmp/generator-$run_id-$condition-$trial.log" "$trial_dir/generator.log"
        fi

        IFS=, read -r total success failed timeouts median p95 peak cookies drops <<< "$(summarize_trial "$trial_dir")"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$condition" "$trial" "$pressure_gate" "$total" "$success" "$failed" "$timeouts" "$median" "$p95" "$peak" "$cookies" "$drops" >> "$local_results/comparison.csv"
    done
done

python3 - "$local_results/comparison.csv" <<'PY' | tee "$local_results/RESULT.txt"
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
PY

echo "Evidence saved in $local_results"
echo "Read this one file: $local_results/RESULT.txt"

# Keep the result folder calm: RESULT.txt stays at the top, while raw CSVs and
# per-trial evidence remain available under details only if debugging is needed.
mkdir -p "$local_results/details"
mv "$local_results"/baseline-trial-* "$local_results"/protected-trial-* "$local_results"/unprotected-trial-* "$local_results/comparison.csv" "$local_results/kernel-settings.txt" "$local_results/details/"
