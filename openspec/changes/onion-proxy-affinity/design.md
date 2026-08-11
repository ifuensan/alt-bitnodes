# Design — onion-proxy-affinity

## Context

The pool of nine Tor daemons exists because C Tor is single-threaded and one
daemon tops out at one core (stage 5). That reason is unchanged. What changes
is *how work is assigned to the pool*: today every dial rolls a die, which is
the cheapest possible balancing rule and also the one that guarantees no
locality. Every piece of per-onion state a Tor client builds — the descriptor,
the introduction circuit, the rendezvous circuit — is thrown away nine times
over.

## Decisions

**Stable hash, not `hash()`.**
Python salts `str.__hash__` per process (`PYTHONHASHSEED` is random by
default), so `hash(address) % len(proxies)` would send `crawl.py` and
`ping.py` to *different* daemons for the same onion, and would reshuffle the
whole assignment on every restart. The selection uses
`sha256(address.encode()).digest()` reduced to an integer instead:
identical across processes, across restarts, and across hosts.

Note in passing: the existing onion/I2P sampling code (`crawl.py:225`) uses
bare `hash()` for `hash(address) % 100 >= sampling_rate`. With a sampling rate
of 100 nothing is excluded, so it is inert today, but it is the same latent
bug — the sampled subset would differ per process and change on restart. Not
fixed here to keep this change to one idea; recorded in `docs/follow-ups.md`.

**A config flag, not a hardcoded behaviour.**
`tor_proxy_affinity` (default `True`) lets the experiment turn affinity off on
a live host by editing a conf, and lets us fall back instantly if affinity
turns out to hurt. A code change that can only be undone by another code
change is a bad thing to deploy in front of a measurement.

**Affinity for onion only.**
`ipv4_proxies` / `ipv6_proxies` exist to spread *source addresses* across
egress paths; pinning a destination to one of them would work against that.
I2P already has one persistent SAM session per process, so there is nothing to
pin.

**Plain modulo, not consistent hashing.**
Changing `TOR_POOL_SIZE` reshuffles every assignment. Consistent hashing would
avoid that, and it is not worth the code: the pool size changes about twice a
year, and the cost of a reshuffle is exactly one crawl cycle of circuit
rebuilds — the situation we are in permanently today.

## Risks / Trade-offs

- **A dead daemon blackholes its share.** Today a dial that picks a broken
  daemon fails and the next dial has an 8/9 chance of a healthy one; with
  affinity, one onion's dials always hit the same daemon, so if it is down
  that whole 1/9 of the onion set goes dark until systemd restarts it.
  Accepted: the units are `Restart=`-managed and a dead Tor is already
  visible in the onion count. If it bites, the mitigation is a one-line
  fallback to a random proxy on connection error, which we deliberately do
  not build before knowing we need it.
- **Uneven shares.** Onion addresses are uniformly distributed base32, so a
  modulo split over ~10k addresses is even to within a percent or two.
  Composition differs (some nodes are chattier), which is why the comparison
  normalises by carried connections rather than comparing raw byte totals.
- **Affinity and the experiment land together.** Strictly, the run measures
  "affinity + dirtiness" against "affinity + default dirtiness", which is the
  right comparison: affinity is the precondition, not the variable. What
  affinity *alone* is worth is a separate before/after against the archived
  egress figures, and much less interesting.

## Measurement plan

The two arms run simultaneously in one pool, so network conditions, the node
population and the crawl cadence are shared and cancel out.

- **Split**: `TOR_DIRTINESS_ARM` in `install.sh` lists the instance numbers
  that get `MaxCircuitDirtiness 3600`; the rest keep the 600s default. Both
  torrc variants are written *before* the pool starts, so every daemon begins
  cold at the same moment. Treating half the pool mid-run would restart those
  daemons and compare a re-ramping arm against a warm one.
- **Cost per arm**: `IPAccounting=yes` on the `tor@` template gives exact
  cumulative `IPEgressBytes` per instance. This replaces the `ss -tinp` delta
  method used in the 2026-08-01 autopsy, which samples and therefore misses
  sockets that are born and die between samples — with ~1k new TLS
  connections/min that is most of them.
- **Load per arm**: established connections on each instance's SocksPort
  (`ss -tn state established '( sport = :905N )'`) counts the crawler streams
  that daemon is carrying. The comparison metric is **egress bytes per
  carried connection**, not raw bytes.
- **Churn per arm**: `HeartbeatPeriod 900` makes each daemon log its own
  circuit-handshake and connection counters every 15 minutes. This is the
  direct measure of the thing being tested. A `ControlPort` would give
  live circuit counts too, but the heartbeat is enough and adds no listener.
- **Outcome guard**: total onion count in snapshots must not drop. If the
  treated arm degrades, the global number falls even though its own bytes
  look better.
- **Window**: onion needed 13h to plateau last time, so the run is ~24h and
  only the post-plateau hours are analysed. Run with `i2p = False`.

Analysis is a diff of two CSV columns; nothing is concluded from a single
sample or from the ramp.

## Migration Plan

1. Land the fork patch and this repo's scaffolding, but do not deploy
   casually: the first deploy restarts the Tor pool.
2. Deploy while intending to start the run — pool cold, split already in the
   torrc files, `i2p = False`, sampler timer enabled.
3. Let it run ~24h, then compare.
4. Whatever the result, reply in the BNOC thread: the lead came from there.

Rollback: `tor_proxy_affinity = False` in both confs (no restart of Tor
needed, the crawler picks it up on its next start) and `TOR_DIRTINESS_ARM`
empty.

## Open Questions

- If affinity plus dirtiness works, is the right end state a much larger
  `MaxCircuitDirtiness` (hours) or a revisit cadence tuned *below* the
  dirtiness window? The second is free and we never considered it because the
  interaction was invisible.
