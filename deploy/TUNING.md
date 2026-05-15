# Crawler tuning

How to size the upstream `bitnodes` crawler for a given host without
saturating Tor or under-filling the snapshot. Numbers below are calibrated
for the current production EC2 (**c7g.2xlarge, 8 vCPU, 16 GB RAM**)
running `crawl + ping + resolve + export + seeder + cache_inv` plus
Redis, Tor and nginx on the same box. Earlier calibration data from
the previous t4g.medium (2 vCPU, 4 GB) is preserved in the tables
below for reference.

If you move to a larger or smaller instance, rescale **`workers`**
proportionally to vCPU count (≈150 crawl workers per vCPU) and verify
with the diagnostic commands at the bottom.

## Knobs

All settings live in `~/bitnodes/conf/crawl.f9beb4d9.conf` (and
`ping.f9beb4d9.conf`) on the EC2, and are persisted in
`deploy/install.sh` so a re-run keeps them.

### `workers` (in each `.conf`)

Concurrent socket pool the crawler/pinger spawns. Each worker keeps a few
sockets in flight (connecting, handshaking, established). At steady state
`open:*` keys in Redis ≈ `crawl.workers × ~3` until handshake-completion
becomes the bottleneck (see _Ceiling_ below).

On a **c7g.2xlarge (8 vCPU)** — current production:

| Crawl workers | Approx. open sockets | Comments |
|---|---|---|
| 500 | ~1700 | Linear scaling phase. |
| 1000 | ~3200 | Tor still healthy, plenty of CPU left. |
| **1200** | **~3700–4000** | **Sweet spot in production today.** |
| 1500+ | not yet measured | Probably gains more before Tor saturates. |

On a **t4g.medium (2 vCPU)** — earlier calibration, kept for reference:

| Crawl workers | Approx. open sockets | Comments |
|---|---|---|
| 200 | ~900 | Low, fine if you only care about ping coverage. |
| 300 | ~1380 | Sweet spot for snapshot count vs. load on 2 vCPU. |
| 500 | ~1390 | Marginal gain; handshake CPU ceiling kicks in. |
| 700 (upstream default) | unstable | Saturates Tor; oscillates wildly. |

**Rule of thumb**: ~150 crawl workers per vCPU. The 2-vCPU host
plateaued at ~1390 simultaneous sockets because every handshake
costs CPU (Bitcoin `version` decode + crypto); on 8 vCPU the same
ceiling moves up roughly proportionally.

### `ping.workers`

Same shape as crawl workers but lower priority. Each one opens a brief
connection to probe peer liveness. Keep around the same value as crawl
workers unless you have a specific reason; the upstream default of 2000
is **always wrong** on a small instance.

### `socket_timeout`

How long a worker waits for a peer to respond before giving up. Affects
both crawl and ping.

- **30 s** — aggressive, drops slow-but-reachable peers. Saves Tor when
  it's saturated. Use temporarily.
- **60 s** — upstream default. Catches more slow peers. Higher Tor load.

Bump to 60 only after `workers` is calibrated; otherwise more workers ×
more time blocked = more open sockets in handshake purgatory.

### `onion_peers_sampling_rate` (crawl only)

Percentage of `.onion` peers in the address pool the crawler actually
tries. Each onion lookup goes through Tor, and Tor is single-threaded.

- **100** (upstream default) — DDoSes your own Tor on small hosts.
- **25** — production today. Onion coverage is ~3% of `open:*`, but Tor
  stays at ~95% CPU instead of dropping >1M circuit requests per 10 min.
- **0** — drop onion entirely. Lose visibility of onion-only nodes
  (typically 5–10% of reachable network globally).

### `snapshot_delay` (crawl only)

How often the crawler master "freezes" its current open set into a
snapshot for `export.py` to write to disk.

- **600 s** (upstream default) — works only if a full sweep fits in
  10 min, which on a small instance with `workers ≤ 300` it does not.
  Snapshots become "what was open at the freeze moment", which can be
  far less than the eventual reachable count.
- **900 s** (production today) — gives the sweep more time to fill up
  before being captured. Eliminates the oscillation we used to see
  (`55 → 1384 → 95 → …`).

Don't set this absurdly high (e.g. > 3600). The dashboard polls for new
snapshots and a stale snapshot defeats the whole point.

### Slave count (in `deploy/run-bitnodes.sh`)

Number of `crawl.py slave` and `ping.py slave` processes launched in
parallel. Slaves share work with the master via Redis.

| Role | Count | Notes |
|---|---|---|
| crawl slaves | 2 | Was 4 upstream; 4 contends too much CPU on 2 vCPU. |
| ping slaves | 6 | Was 15 upstream; 15 was murderous. |

Don't go below 1 of each — the master needs help.

## Ceiling: the CPU wall and how the resize moved it

On the earlier **t4g.medium (2 vCPU)** the snapshot count plateaued
at ~1390 even with `workers=500`. Forensic check at the time:

- `redis-cli --scan --pattern 'open:*' | wc -l` ≈ 1390
- `ss -s | grep estab` ≈ 5400

So the kernel had ~5400 TCP connections established, but only ~1390
ever completed the Bitcoin `version`/`verack` handshake and were
marked as `open` by the crawler. The other ~4000 were stuck in
handshake because the CPU was the bottleneck (decode `version` →
reply → parse `verack`).

**Resize to c7g.2xlarge (8 vCPU, May 2026) moved the wall up
~3× as expected**. With `workers=1200` we now see `open:*` ≈ 3700–4000
consistently, with load ~1.5 and Tor at ~92% (no longer saturating
the box). The exact new ceiling has not been measured — `workers=1500`
or higher may yield more before Tor (still single-threaded) becomes
the next bottleneck.

To break the c7g.2xlarge ceiling further you would need:

1. **A bigger instance** (`c7g.4xlarge` ≈ 16 vCPU, ~$392/mo), or
2. **Splitting Tor onto its own VM** so it stops competing with the
   crawler workers on the same box (see
   `docs/postmortems/2026-05-12-tor-saturation-and-public-edge.md`
   and the I2P research file in `_bmad-output/` for the architectural
   plan).

## When Tor is in trouble

Symptoms (`sudo journalctl -u tor@default --no-pager -n 50`):

- `We'd like to launch a circuit ... [N similar messages suppressed]` with
  `N` in the hundreds of thousands per 10 min.
- `Tried for 120 seconds to get a connection to [scrubbed]. Giving up.`
- Heartbeat shows many more open circuits than the host can sustain.

In order of bluntness:

1. Lower `onion_peers_sampling_rate` (e.g. 25 → 10).
2. Lower `crawl.workers` and `ping.workers` together.
3. Disable onion entirely: in both `.conf` files set `onion = False`,
   stop Tor (`sudo systemctl disable --now tor`). You'll need to revisit
   `deploy/install.sh` to keep this from being undone on next deploy.

## When snapshot counts oscillate

Symptoms: consecutive snapshot files alternate between e.g. 60 and 1400
nodes, with no clear pattern.

### Cause — `snapshot_delay` shorter than the sweep

The crawler takes a snapshot mid-sweep, capturing only what was already
in `open:*`. The fix is `snapshot_delay` ≥ 900s and `crawl.workers`
high enough that one sweep completes within a single interval.

> **Historical note (May 2026).** A second oscillation cause was a
> `tcpdump-pcap.service` running alongside the crawler: its `-s 0`
> snaplen + EBS I/O contention cut handshakes mid-flight. That entire
> pcap-capture subsystem (and the RTT data layer it fed) was removed in
> the `remove-rtt-pipeline` change, so it can no longer reintroduce
> oscillation on this deployment.

### Diagnose

```bash
ssh ... 'ls -t ~/bitnodes/data/export/f9beb4d9/*.json | head -6 \
  | while read f; do echo "$(basename $f): $(jq length $f) nodes"; done'
```

Stable snapshots vary by single-digit percent. Anything else means
the sweep isn't completing — see "Cause" above.

## Diagnostic snippets

### One-shot snapshot of crawler health

```bash
ssh ... '
  echo "=== load ==="
  uptime
  echo "=== tor ==="
  ps -o pcpu,pmem,cmd -p $(pgrep -x tor)
  echo "=== redis state ==="
  redis-cli --scan --pattern "open:*" | wc -l
  redis-cli --scan --pattern "open:*onion*" | wc -l
  echo "=== latest cron ==="
  tail -1 ~/bitnodes/log/crawl.f9beb4d9.log
  echo "=== last 3 snapshots ==="
  ls -t ~/bitnodes/data/export/f9beb4d9/*.json | head -3 \
    | while read f; do echo "$(basename $f): $(jq length $f) nodes"; done
'
```

### What's pinned to the system (CPU, sockets, ulimit)

```bash
ssh ... '
  echo "=== tcp sockets ==="; ss -s
  echo "=== conntrack ==="
  cat /proc/sys/net/netfilter/nf_conntrack_max
  cat /proc/sys/net/netfilter/nf_conntrack_count
  echo "=== master FDs ==="
  PID=$(pgrep -f "crawl.py.*master" | head -1)
  cat /proc/$PID/limits | grep "open files"
  ls /proc/$PID/fd | wc -l
'
```

### Tor heartbeat / suppressed-message rate

```bash
ssh ... 'sudo journalctl -u tor@default --since "10 min ago" --no-pager \
  | grep "similar messages suppressed" | tail -3'
```

The number in `[N similar messages suppressed in last X seconds]` tells
you Tor's stress level. Healthy is `<10k` per 10 min. Saturated is
`>100k`.

## How to apply a change

Hot-apply on the running EC2 (takes effect on next crawler tick or after
restart):

```bash
ssh ... "sudo sed -i 's|^workers = .*|workers = NEW|' \
  ~/bitnodes/conf/crawl.f9beb4d9.conf \
  && sudo systemctl restart bitnodes"
```

Persist it so the next CI deploy doesn't revert: edit the `sed` block in
`setup_crawler()` of `deploy/install.sh`, commit, push. The CI workflow
does `git fetch && git reset --hard origin/main` before invoking
`install.sh`, so the new value will be applied cleanly on the next deploy.

## Historical context

See `docs/postmortems/2026-05-12-tor-saturation-and-public-edge.md` for
the full narrative of how today's values were derived.
