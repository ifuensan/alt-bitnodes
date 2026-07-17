# Scale onion crawling with multiple Tor instances

## Why

The dashboard plateaus at ~4.2k reachable nodes while bitnodes-style trackers
report ~20k. The gap is almost entirely `.onion`: our latest stable snapshot
has 12 onion nodes out of an estimated ~15k reachable. This is self-inflicted:
after the 2026-05-12 Tor saturation incident on the old t4g.medium (2 vCPU),
`onion_peers_sampling_rate` was cut to 25 and the crawler was left with a
single single-threaded Tor daemon at ~90% CPU that drops most circuit
requests. The host is now a c7g.2xlarge (8 vCPU, load ~1.5) with idle
headroom — the mitigation outlived the machine it was written for.

## What Changes

- `install.sh` provisions N additional Tor instances (`tor@bitnodes1..N`,
  distinct SocksPorts) alongside the existing `tor@default`, idempotently.
- The crawler config sed lists all Tor SocksPorts in `tor_proxies`; the
  crawler already load-balances across the list (`random.choice` in
  `crawl.py`).
- `onion_peers_sampling_rate` returns from 25 to 100.
- Rollout is verified against explicit health checks (host load, Tor
  circuit-drop rate, snapshot onion counts) with a documented single-commit
  rollback.

## Capabilities

### New Capabilities
- `onion-crawling`: the deployment's contract for `.onion` node coverage —
  multiple Tor daemons provisioned by the installer, crawler configured to
  spread onion dials across all of them, full onion peer sampling, and
  saturation guardrails (what to check, how to roll back).

### Modified Capabilities

<!-- none: crawler-systemd-units only covers the absence of the pcap
pipeline; no existing spec's requirements change -->

## Impact

- `deploy/install.sh` — new Tor provisioning step + changed sed values
  (`tor_proxies`, `onion_peers_sampling_rate`).
- Production EC2 — 5 new `tor@bitnodesN` systemd services; expected load
  increase from ~1.5 toward ~5–7 of 8 vCPUs once onion coverage ramps.
- Snapshot payloads grow (potentially 4k → 10k+ nodes, ~2–3 MB per export
  JSON); disk impact is bounded by the new 90-day export retention.
- No dashboard/API/MCP code changes; they render whatever the snapshots
  contain.
- Risk: repeating the 2026-05-12 saturation — mitigated by per-instance Tor
  (each bounded at ~1 core), health checks after deploy, and one-commit
  rollback (revert restores sampling 25 + single proxy; extra instances are
  harmless idle).
