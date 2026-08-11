#!/usr/bin/env bash
#
# Sample the Tor pool for the MaxCircuitDirtiness A/B.
#
# One CSV row per instance per sample:
#
#   ts,instance,arm,dirtiness,egress_bytes,ingress_bytes,socks_conns,onion_total
#
# egress/ingress come from systemd's per-unit IP accounting (exact, no
# sampling loss); socks_conns counts the crawler streams that instance is
# currently carrying, which is the load to normalise by — the comparison is
# bytes per carried connection, never raw bytes, because the two arms never
# carry exactly the same load. onion_total is the global snapshot figure,
# repeated on every row, as the guard that the treated arm is not quietly
# degrading the thing we are trying to make cheaper.
#
# Counters are cumulative since each unit started, so analysis works on
# differences between two rows, and any interval containing a restart must be
# discarded (a restart zeroes the counter and the daemon's circuits).
#
# Usage:  tor-experiment-sample.sh [output.csv] [interval_seconds]
set -euo pipefail

OUT="${1:-/var/log/alt-bitnodes/tor-experiment.csv}"
INTERVAL="${2:-60}"
POOL_SIZE="${TOR_POOL_SIZE:-8}"
ARM="${TOR_DIRTINESS_ARM:-}"
DIRTINESS="${TOR_DIRTINESS_VALUE:-3600}"
EXPORT_DIR="${BITNODES_EXPORT_DIR:-/home/ubuntu/bitnodes/data/export/f9beb4d9}"

mkdir -p "$(dirname "${OUT}")"
[[ -s "${OUT}" ]] || echo "ts,instance,arm,dirtiness,egress_bytes,ingress_bytes,socks_conns,onion_total" >> "${OUT}"

# Onion count of the newest snapshot. Cheap enough at this interval and it
# keeps the outcome variable in the same file as the cost variables.
onion_total() {
  local latest
  # Snapshots are named <unix-timestamp>.json, so a version sort picks the
  # newest without trusting mtime.
  latest="$(ls -1 "${EXPORT_DIR}"/*.json 2>/dev/null | sort -V | tail -1)" || true
  [[ -n "${latest}" ]] || { echo ""; return; }
  python3 - "${latest}" <<'PY' 2>/dev/null || echo ""
import json, sys
rows = json.load(open(sys.argv[1]))
print(sum(1 for r in rows if str(r[0]).endswith(".onion")))
PY
}

unit_counter() {  # unit, property
  local v
  v="$(systemctl show "$1" -p "$2" --value 2>/dev/null || true)"
  # "[not set]" when the unit predates the accounting drop-in.
  [[ "${v}" =~ ^[0-9]+$ ]] && echo "${v}" || echo ""
}

while true; do
  ts="$(date -u +%s)"
  total="$(onion_total)"
  for i in $(seq 1 "${POOL_SIZE}"); do
    unit="tor@bitnodes${i}.service"
    port=$((9050 + i))
    if [[ " ${ARM} " == *" ${i} "* ]]; then arm="treated"; d="${DIRTINESS}"; else arm="control"; d="600"; fi
    conns="$(ss -tnH state established "( sport = :${port} )" 2>/dev/null | wc -l)"
    printf '%s,bitnodes%s,%s,%s,%s,%s,%s,%s\n' \
      "${ts}" "${i}" "${arm}" "${d}" \
      "$(unit_counter "${unit}" IPEgressBytes)" \
      "$(unit_counter "${unit}" IPIngressBytes)" \
      "${conns}" "${total}" >> "${OUT}"
  done
  sleep "${INTERVAL}"
done
