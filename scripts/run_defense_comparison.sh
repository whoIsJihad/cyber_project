#!/usr/bin/env bash

# Runs two trials per condition with the same HTTP workload and SYN rate.
# Starts continuous SYN sending before HTTP and stops it after measurement.
# No queue-drain waits; later trials can contain leftover connections.
# Saves overlap checks and rejects a trial if sending finishes before HTTP.
# Restores the original receiver kernel settings on exit.

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
trials_per_condition=2
http_duration_seconds=20
http_concurrency=20
http_timeout_seconds=2

# Same SYN workload in protected and unprotected trials.
syn_rate=1000
# One raw-socket process tops out around 800-1000 pkt/s; several processes are
# needed to actually push the requested rate and put real pressure on the queue.
syn_workers=8
pressure_gate_timeout_seconds=20
# A small queue makes the defense choice observable. It is restored on exit.
# On this kernel, net.ipv4.tcp_max_syn_backlog does NOT bound the real queue
# any more (verified by hand: even at sysctl value 16, nginx's own listen()
# backlog of 511 stayed the effective limit). The only thing that actually
# shrinks the queue is nginx's own `listen ... backlog=N`. 8 was picked by
# testing: with this backlog, syncookies=1 kept every request succeeding and
# syncookies=0 timed out every request — a clean, real difference.
comparison_syn_backlog=8
nginx_site_conf="/etc/nginx/sites-available/default"
nginx_conf_backup="/tmp/syn-lab-nginx-default-$$.bak"

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
        ssh "$sender" "printf '%s\\n' '$sender_sudo_password' | sudo -S -p '' kill $current_generator_pid 2>/dev/null || true" || true
        for attempt in {1..50}; do
            if ! ssh "$sender" "ps -p $current_generator_pid -o stat= | grep -q '^[^Z]'"; then
                current_generator_pid=""
                break
            fi
            sleep 0.1
        done
        if [[ -n "$current_generator_pid" ]]; then
            echo "Generator did not stop; check sender PID $current_generator_pid." >&2
            return 1
        fi
    fi
}

wait_for_nginx_ready() {
    local deadline=$((SECONDS + 10))
    while (( SECONDS < deadline )); do
        if ssh "$receiver" "systemctl is-active --quiet nginx && ss -H -ltn 'sport = :80' | grep -q LISTEN"; then
            return 0
        fi
        sleep 0.5
    done
    echo "nginx did not come back up on port 80 after restart." >&2
    return 1
}

restore_kernel_settings() {
    if [[ -n "$original_syncookies" && -n "$original_syn_backlog" ]]; then
        echo "Restoring receiver kernel settings and nginx config..."
        sudo_receiver "/usr/sbin/sysctl -w net.ipv4.tcp_syncookies=$original_syncookies net.ipv4.tcp_max_syn_backlog=$original_syn_backlog" || true
        sudo_receiver "cp $nginx_conf_backup $nginx_site_conf" || true
        sudo_receiver "rm -f $nginx_conf_backup" || true
        sudo_receiver "systemctl restart nginx" || true
        wait_for_nginx_ready || true
    fi
}

cleanup() {
    stop_trial_processes || true
    restore_kernel_settings
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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

# The queue size that actually matters is nginx's own `listen ... backlog=N`,
# not net.ipv4.tcp_max_syn_backlog (verified by hand: that sysctl alone did
# nothing on this kernel; nginx's default backlog of 511 stayed in force
# through sysctl changes and even through `systemctl reload`). So back up the
# site config, inject a small backlog into it, and restart (reload does not
# recreate the listening socket, so it would not apply either) once, before
# any trial. It is restored from the backup on exit.
echo "Shrinking nginx's listen backlog to $comparison_syn_backlog so it takes effect..."
sudo_receiver "cp $nginx_site_conf $nginx_conf_backup"
sudo_receiver "sed -i -E 's/ ?backlog=[0-9]+//g; s/(listen [^;]*80[^;]*);/\\1 backlog=$comparison_syn_backlog;/' $nginx_site_conf"
ssh "$receiver" "grep -n listen $nginx_site_conf"
sudo_receiver "nginx -t"
sudo_receiver "systemctl restart nginx"
wait_for_nginx_ready

conditions=(baseline protected unprotected)
for trial in $(seq 1 "$trials_per_condition"); do
    # Rotate the order. Time-related VM variation therefore cannot always
    # favour one condition merely because it ran first or last.
    for offset in 0 1 2; do
        condition="${conditions[$(((trial - 1 + offset) % 3))]}"
        trial_dir="$local_results/$condition-trial-$trial"
        mkdir -p "$trial_dir"
        echo "Running $condition trial $trial of $trials_per_condition..."

        # Backlog is already baked into nginx's listening socket (set once,
        # above, before the loop). Only syncookies needs to change per trial,
        # and that sysctl is read live on every SYN, so no restart is needed.
        syncookies=1
        [[ "$condition" == "unprotected" ]] && syncookies=0
        sudo_receiver "/usr/sbin/sysctl -w net.ipv4.tcp_syncookies=$syncookies"
        ssh "$receiver" "nstat -az >$receiver_results/nstat-before-$run_id-$condition-$trial.txt"

        current_monitor_pid="$(ssh "$receiver" "cd ~; nohup python3 -m server.monitor --interval 0.1 --output $receiver_results/monitor-$run_id-$condition-$trial.csv </dev/null >/tmp/monitor-$run_id-$condition-$trial.log 2>&1 & echo \$!")"
        [[ "$current_monitor_pid" =~ ^[0-9]+$ ]] || { echo "Receiver monitor did not start." >&2; exit 1; }
        sleep 1

        overlap="not-required"
        pressure_gate="not-required"
        if [[ "$condition" != "baseline" ]]; then
            if [[ "$condition" == "protected" ]]; then
                gate_counter="$(read_counter TcpExtSyncookiesSent)"
            else
                gate_counter="$(read_counter TcpExtListenDrops)"
            fi
            # sudo runs the short launcher in the foreground. The root shell
            # detaches Python with all three streams redirected, then returns
            # its actual PID immediately; no sudo wrapper holds SSH open.
            current_generator_pid="$(ssh "$sender" "printf '%s\\n' '$sender_sudo_password' | sudo -S -p '' sh -c 'cd /home/snd || exit; nohup python3 -m client.generator --continuous --rate $syn_rate --workers $syn_workers </dev/null >/tmp/generator-$run_id-$condition-$trial.log 2>&1 & echo \$!'")"
            [[ "$current_generator_pid" =~ ^[0-9]+$ ]] || { echo "SYN generator did not start." >&2; exit 1; }
            if wait_for_pressure "$condition" "$gate_counter"; then
                pressure_gate="passed"
            else
                pressure_gate="not-observed"
            fi
            if ! ssh "$sender" "ps -p $current_generator_pid -o stat= | grep -q '^[^Z]'"; then
                echo "Generator ended before HTTP measurement; stopping this invalid comparison." >&2
                exit 1
            fi
            overlap="passed"
            printf 'generator_alive_before_http=true\n' > "$trial_dir/overlap.txt"
        fi

        ssh "$sender" "cd ~; python3 -m client.sustained_http_load --duration $http_duration_seconds --timeout $http_timeout_seconds --concurrency $http_concurrency --output $sender_results/http-$run_id-$condition-$trial.csv"
        if [[ "$condition" != "baseline" ]]; then
            if ssh "$sender" "ps -p $current_generator_pid -o stat= | grep -q '^[^Z]'"; then
                printf 'generator_alive_after_http=true\n' >> "$trial_dir/overlap.txt"
            else
                overlap="failed"
                printf 'generator_alive_after_http=false\n' >> "$trial_dir/overlap.txt"
            fi
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

        if [[ "$overlap" == "failed" ]]; then
            echo "Generator ended during HTTP measurement. Evidence saved in $trial_dir; comparison rejected." >&2
            exit 1
        fi

        IFS=, read -r total success failed timeouts median p95 peak cookies drops <<< "$(summarize_trial "$trial_dir")"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$condition" "$trial" "$pressure_gate" "$total" "$success" "$failed" "$timeouts" "$median" "$p95" "$peak" "$cookies" "$drops" >> "$local_results/comparison.csv"
    done
done

python3 scripts/summarize_comparison.py "$local_results/comparison.csv" | tee "$local_results/RESULT.txt"

echo "Evidence saved in $local_results"
echo "Read this one file: $local_results/RESULT.txt"

# Keep the result folder calm: RESULT.txt stays at the top, while raw CSVs and
# per-trial evidence remain available under details only if debugging is needed.
mkdir -p "$local_results/details"
mv "$local_results"/baseline-trial-* "$local_results"/protected-trial-* "$local_results"/unprotected-trial-* "$local_results/comparison.csv" "$local_results/kernel-settings.txt" "$local_results/details/"
