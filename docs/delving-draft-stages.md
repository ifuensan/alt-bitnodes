# Draft — Delving Bitcoin post

Status: draft 2026-07-23, peak numbers filled from the 2026-07-22/23
post-UseEntryGuards plateau. Ready for author review. Target venue:
https://delvingbitcoin.org, category "Implementation" or "Research".

---

# Your node tracker's "reachable node count" measures its own infrastructure

Over the last two months I revived a bitnodes-style crawler (a fork of
the unmaintained `ayeowch/bitnodes`) and scaled it from **~1,400 to
~22,000 reachable Bitcoin nodes** — without the network changing
underneath it. Every jump came from removing a bottleneck in *my*
infrastructure, not from nodes appearing. Each fix exposed the next
ceiling, and every ceiling looked exactly like "the real size of the
network" until it broke.

The thesis, in one line: **a tracker's reachable node count is a
property of the tracker, not of the network.** When two trackers
disagree, the interesting question is not who is right — it's which
bottleneck each one has not hit yet.

Live instance: https://pesquisa.hacknodes.xyz (dashboard, REST API,
MCP server). Crawler fork: https://github.com/ifuensan/bitnodes.

## The stages

Each stage ended at a hard, reproducible ceiling that looked like a
plateau of the network itself.

### Stage 1 — Tor eats the CPU (ceiling: ~1,390)

On a 2-vCPU t4g.medium with upstream defaults, a single Tor daemon sat
at 100% CPU dropping ~1M circuit requests per 10 minutes, and the
crawler's sweep couldn't finish inside the export window: snapshot
counts oscillated 55 → 1,384 → 95. De-tuning the crawler (fewer
workers, onion sampling) stabilized it at ~1,390. That number held for
weeks and looked like a fact about the network.

### Stage 2 — handshake CPU (ceiling: ~4,170)

Resizing to a c7g.2xlarge (8 vCPU) tripled the count to ~4,170, which
held for **two months**. Nothing in the data suggested it was an
artifact; it took a composition check to break the illusion.

### Stage 3 — composition reveals the artifact (same ceiling)

Of those ~4,170, only **12** were onion nodes. Adding a pool of 6 Tor
daemons and full onion peer sampling ramped onion into the hundreds —
and the total did not move: every onion node gained displaced one IPv4
node, 1:1. That is the smoking gun that the ceiling was structural.

### Stage 4 — the snapshot is a socket count (ceiling broken: ~11.6k)

The realization: in this architecture, a snapshot can only contain as
many nodes as there are *simultaneously open sockets*, which is
`ping processes × workers per process`. 7 × 600 = 4,200 ≈ the observed
4,170. Scaling to 12 × 2,000 = 24,000 slots broke the ceiling: 11,600
nodes in five hours, with the IPv4 population (~6.4k) finally complete.

### Stage 5 — Tor is single-threaded (lever: more daemons, not bigger ones)

Onion counts kept decaying over days. `sar` showed the box 36% idle
while onion starved — each Tor daemon is single-threaded and tops out
at ~1 core regardless of how many cores you buy. The lever is *more
daemons* (pool of 9), not a bigger instance. Raising
`MaxClientCircuitsPending` treats a symptom; parallelism treats the
cause.

### Stage 6 — I2P needs seeds, not bandwidth (+4.7k nodes)

Clearnet peers do not gossip `.b32.i2p` addresses, so an I2P-capable
crawler discovers exactly zero I2P nodes on its own. Seeding 512 known
destinations from Bitcoin Core's fixed seeds bootstrapped the ring, and
the count went from 0 to **~4,700 reachable I2P nodes** — a population
essentially no public tracker counts. (Two real bugs on the way: the
fork's address serializer classified `.b32.i2p` as IPv4 because it
contains dots, crashing the version handshake; and i2pd itself died
when my own debug logging filled the disk.)

### Stage 7 — the silent freeze (availability is part of measurement)

With ~123k Redis keys per cycle, the crawler's `restart()` sent one
giant MULTI transaction — a multi-MB single `send()` that stalled under
full load until TCP gave up (~16 min), and the uncaught exception
killed the scheduler greenlet. Every process stayed alive, every
systemd unit stayed green, and the dashboard served a frozen snapshot
for **21.5 hours**. The fix was boring (batched pipelines, supervised
greenlet); the lesson isn't: at this scale the tracker itself becomes a
distributed system, and its failure modes look like network changes.
(Diagnosed and hot-patched via gdb + `PyRun_SimpleString` injection
into the live process — greenlet stacks are invisible to thread-level
profilers.)

### Stage 8 — Tor's guard anti-DoS throttles crawlers (onion: 0 → ~10,800)

After a restart, onion never re-ramped: 17 → 21 → 0 over a day, while
the same Tor daemons sat nearly idle and manual onion dials succeeded.
The guard logs told the story: `247,230 circuits timed out` vs `212
completed`, "Guard is failing more circuits than usual." A crawler
concentrates all circuit creation through 1–2 entry guards per daemon,
and the guards' per-IP DoS defense throttles exactly that pattern —
politely, invisibly, and increasingly with load.

For a crawler with no anonymity requirement the fix is one line per
torrc: **`UseEntryGuards 0`** — a random entry relay per circuit,
spreading creation across the whole relay set. Under identical crawler
load, onion went from 3 to 2,532 in two hours, kept compounding (more
reachable onion nodes → more onion addr gossip → more discovery), and
plateaued ~13 hours later.

- Onion at the plateau: **~10,700–10,800 simultaneously open
  connections** (previous best snapshot: 3,394 — a 3.2× jump from one
  torrc line)
- Total reachable at the plateau: **~22,100** (previous ceiling: ~13.5k)
- Two footnotes the raw numbers hide: per-sweep crawl counts still
  oscillate 3k–9k depending on momentary circuit luck — the same
  crawler, minutes apart, "measures" wildly different networks — and
  our *instantaneous* onion count now exceeds the 8-day *windowed* Tor
  count bitnod.es reports (~10.6k), which says less about who is right
  and more about how much measurement infrastructure shapes the number.

## What this means for node-count numbers

- **Instantaneous vs windowed counts measure different things.** Tor
  connections are transient; an instantaneous snapshot structurally
  undercounts onion. Over an 8-day rolling union my instance sees
  27,063 unique nodes where bitnod.es reports 22,232 — and both are
  "right" for their definition.
- **Cross-tracker comparisons are infrastructure comparisons.** IPv4
  counts converge across trackers because IPv4 is cheap to enumerate.
  Onion and I2P counts diverge wildly because they are bounded by Tor
  circuit capacity, guard throttling, and seed availability — none of
  which are properties of the Bitcoin network.
- **The interesting metric is the derivative.** If your count plateaus,
  before concluding "that's the network", check composition (stage 3),
  socket budget (stage 4), and upstream throttling (stage 8).

Happy to share configs, the fork's diffs, or raw snapshots — everything
is public at the links above.
