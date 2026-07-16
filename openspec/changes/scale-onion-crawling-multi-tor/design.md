# Design — scale-onion-crawling-multi-tor

## Context

The 2026-05-12 postmortem detuned onion crawling for a 2-vCPU t4g.medium:
`onion_peers_sampling_rate` 100→25 and a single Tor daemon at ~90% CPU. The
host is now a c7g.2xlarge (8 vCPU, load ~1.5) but the mitigation remains, so
snapshots carry ~12 onion nodes out of ~15k reachable. Tor is single-threaded;
one daemon cannot use the new headroom. The crawler already supports proxy
pools: `crawl.py` does `random.choice(CONF["tor_proxies"])` per onion dial.

Constraints discovered in the fork's code:

- `utils.txt_items` parses config lists **one item per line** (ConfigParser
  multi-line values with indented continuations). A space-separated
  `tor_proxies` one-liner would parse as a single bogus item.
- `install.sh` regenerates `crawl.f9beb4d9.conf` seds on every deploy, so any
  edit must be idempotent across re-runs.
- Tor comes from the Ubuntu `tor` package, which ships the `tor@.service`
  template and `tor-instance-create`.

## Goals / Non-Goals

**Goals:**
- Recover `.onion` coverage to the same order of magnitude as
  bitnodes-style trackers (10k+), bounded by host CPU.
- Keep the deploy path unchanged: one commit, CI deploy, `install.sh` does
  everything, idempotently.
- One-commit rollback.

**Non-Goals:**
- IPv6 enablement (separate AWS/VPC work, no repo change).
- I2P crawling (existing follow-up, own change).
- Crawler/ping worker retuning — only if onion growth saturates handshake
  capacity; follow-up, not this change.

## Decisions

1. **Pool of 5 extra instances (6 SocksPorts total, 9050–9055).**
   Postmortem math: one Tor at ~90% CPU served 25% sampling, so 100% needs
   roughly 4× the circuit capacity; 6 daemons run at ~60–70% each with
   headroom. 8 vCPU minus crawler load (~1.5) leaves ~6 cores.
   *Alternative — 3 extra*: each instance near saturation again, no margin.
   *Alternative — 7+*: starves the crawler's own handshake CPU as node count
   (and thus ping load) grows.

2. **Provision with `tor-instance-create` + the distro `tor@` template.**
   Gets per-instance user, DataDirectory (`/var/lib/tor-instances/<name>`),
   and a maintained systemd unit for free. Each instance torrc contains only
   `SocksPort 127.0.0.1:905N`.
   *Alternative — hand-rolled units in `deploy/`*: duplicates what the tor
   package already ships and adds placeholder substitution for no benefit.

3. **Multi-line `tor_proxies` written by an idempotent two-step sed.**
   Step 1 deletes any indented continuation lines following `tor_proxies =`
   (range `/^tor_proxies/,/^[^[:space:]]/` filtered to leading-whitespace
   lines); step 2 rewrites the key with `\n`-joined continuations. Re-running
   the installer therefore converges instead of accumulating lines.
   *Alternative — space-separated one-liner*: silently broken
   (`txt_items` is line-based; `ip_port_list` would crash or mis-parse).

4. **Sampling 25 → 100 in one step, not staged.**
   The failure mode being guarded against (Tor circuit overload) is now
   bounded per-instance, health checks run right after deploy, and rollback
   is a single revert. Staging (25→50→100) would cost multiple deploy+soak
   cycles for little added signal.

## Risks / Trade-offs

- [Repeat of Tor saturation] → post-deploy health checks (load average, Tor
  journal dropped-circuit volume, per-instance CPU) with a one-commit revert
  documented in the spec.
- [Ping stack becomes the next bottleneck] → expected: `open:*`/snapshot
  counts plateau below the onion population. Accept for this change; retune
  `ping.workers`/slaves as a follow-up with real data.
- [Bigger snapshots: ~2–3 MB JSON at 10k+ nodes] → disk bounded by the
  90-day export retention; API `latest` dump grows but sits behind
  CloudFront caching.
- [`tor-instance-create` missing on the host] → it ships with Ubuntu 24.04's
  `tor` package, which `install.sh` already installs; the provisioning step
  fails loudly if absent (set -e), which is the correct behaviour.

## Migration Plan

1. Single commit: `install.sh` provisioning function + sed changes.
2. Push → CI deploy runs installer; instances come up; crawler restarts with
   the new conf.
3. Health checks (~15 min and ~2 h after deploy):
   `systemctl is-active 'tor@bitnodes*'`, `ss -ltn` shows 9051–9055,
   load average vs 8 vCPUs, `journalctl -u 'tor@*'` for circuit-drop floods,
   onion share of new snapshots trending up.
4. Rollback: revert the commit; CI redeploys sampling 25 + single proxy.
   Idle pool instances are harmless and can be stopped manually later.

## Open Questions

- None blocking. Follow-up candidates: ping worker retune once onion volume
  is real; whether `MaxClientCircuitsPending`-style torrc tuning adds
  anything beyond horizontal instances.
