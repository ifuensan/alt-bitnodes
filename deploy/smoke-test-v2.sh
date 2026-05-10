#!/usr/bin/env bash
# Smoke-test the phase-2 RTT endpoints. Exits non-zero on any failure.
# Usage: ./smoke-test-v2.sh [BASE_URL]   (default http://127.0.0.1:8000)
set -euo pipefail

BASE="${1:-http://127.0.0.1:8000}"

req() {
  local method=$1 path=$2 expect=${3:-200}
  local code
  code=$(curl -s -o /tmp/smoke.body -w '%{http_code}' "$BASE$path")
  if [[ "$code" != "$expect" ]]; then
    echo "FAIL $method $path: got $code, expected $expect"
    cat /tmp/smoke.body; echo
    return 1
  fi
  echo "ok   $method $path -> $code"
}

req GET /api/v1/leaderboard/
req GET '/api/v1/leaderboard/?limit=5'
req GET '/api/v1/leaderboard/?country=US'
req GET '/api/v1/rankings/countries/'
req GET '/api/v1/rankings/asns/'
req GET '/api/v1/rankings/user-agents/'
req GET '/api/v1/groups/by-ip/'
req GET '/api/v1/groups/by-ip/198.51.100.42/' 404
req GET '/api/v1/leaderboard/?limit=0' 422

NODE_ID=$(curl -s "$BASE/api/v1/snapshots/latest/" | python3 -c 'import sys,json;
d=json.load(sys.stdin); k=next(iter(d["nodes"])); print(k.replace(":","-"))')
echo "picked node: $NODE_ID"
req GET "/api/v1/nodes/$NODE_ID/latency/"
req GET "/api/v1/nodes/$NODE_ID/latency/?hours=1"
req GET "/api/v1/nodes/$NODE_ID/latency/?hours=200" 422
req GET '/api/v1/nodes/0.0.0.0-1/latency/' 404

echo "v1 phase-2 smoke checks passed"
