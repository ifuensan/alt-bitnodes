#!/usr/bin/env bash
# Foreground supervisor for the bitnodes crawler stack.
# Replaces start.sh — keeps PID 1 alive so systemd can manage the cgroup.
# On SIGTERM/SIGINT, kill -- -$$ takes down all children.

set -u
cd "$(dirname "$0")"
source venv/bin/activate

trap 'kill -- -$$ 2>/dev/null; exit 0' SIGTERM SIGINT

mkdir -p log data

NICE="nice -n 19"

$NICE python -u crawl.py   conf/crawl.f9beb4d9.conf   master >> log/crawl.f9beb4d9.master.out 2>&1 &
for i in 1 2 3 4; do
  $NICE python -u crawl.py conf/crawl.f9beb4d9.conf   slave  >> "log/crawl.f9beb4d9.slave.${i}.out" 2>&1 &
done

$NICE python -u ping.py    conf/ping.f9beb4d9.conf    master >> log/ping.f9beb4d9.master.out 2>&1 &
for i in $(seq 1 15); do
  $NICE python -u ping.py  conf/ping.f9beb4d9.conf    slave  >> "log/ping.f9beb4d9.slave.${i}.out" 2>&1 &
done

$NICE python -u resolve.py conf/resolve.f9beb4d9.conf  >> log/resolve.f9beb4d9.out 2>&1 &
$NICE python -u export.py  conf/export.f9beb4d9.conf   >> log/export.f9beb4d9.out 2>&1 &
$NICE python -u seeder.py  conf/seeder.f9beb4d9.conf   >> log/seeder.f9beb4d9.out 2>&1 &

for i in 1 2 3; do
  $NICE python -u cache_inv.py conf/cache_inv.f9beb4d9.conf >> "log/cache_inv.f9beb4d9.${i}.out" 2>&1 &
done

wait
