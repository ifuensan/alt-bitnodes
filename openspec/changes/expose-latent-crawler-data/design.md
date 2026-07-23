# Design: expose-latent-crawler-data

## Context

The crawler stack (fork of `ayeowch/bitnodes`) already writes three datasets
this repo never reads:

- `binv:<block-hash>` / `rinv:<tx-hash>` Redis zsets — member = `addr-port`,
  score = ms timestamp when that node announced the inv to us (written by the
  three `cache_inv.py` processes). ~360 recent blocks present at any time;
  zsets rotate out.
- `services` — field 6 of every snapshot row (and inside `peer:*` entries):
  the service-flag bitmask from the version handshake.
- `peer:<addr>-<port>` — JSON list of `[address, port, services, last_seen]`
  entries the peer advertised via `addr`/`addr2` gossip (~22k keys).

Established patterns this design reuses:

- **Precompute-on-timer, serve-from-JSON**: `alt-bitnodes-window-stats`
  systemd timer → `queries/window_stats.py` → cached JSON → cheap endpoint.
- **Charts**: Observable Plot + d3 from CDN, rendered into `<div>`
  containers, styled only via design-system tokens (`dashboard-bar-charts`,
  `dashboard-design-system` specs).
- **Three consumers, one data layer**: `queries/` returns plain dicts;
  `app.py` and `alt_bitnodes_mcp` translate.

Constraint: the `remove-rtt-pipeline` decision stands — `ping:*` RTT data
stays unexposed. The mcp-service spec's "REST v1 unchanged" requirement
refers to existing routes; adding new v1 routes follows the
`GET /api/v1/stats/window` precedent.

## Goals / Non-Goals

**Goals:**

- Persist block-propagation observations before Redis rotates them out, and
  serve per-block and aggregate views split by network class.
- Turn the services bitmask into named adoption metrics — latest snapshot
  and a historical series.
- Publish a weighted unique-node estimate (1/N over inferred network types)
  next to the raw reachable count.
- Define every chart (form, encodings, interactions) so implementation is
  mechanical, all on Observable Plot.

**Non-Goals:**

- Tx-level propagation (`rinv:*`): noisier, higher volume — recorded as a
  future capability, not built here.
- RTT/latency exposure of any kind.
- Changing what the crawler writes (read-only against crawler-owned keys).
- True origin-time propagation measurement: our timestamps are
  "first heard by our crawler", normalized per block. The charts are honest
  about this (relative-time ECDF, not absolute latency claims).

## Decisions

### D1 — Chart framework: Observable Plot (keep, and only it)

Plot + d3 are already loaded and specced (`dashboard-bar-charts` bans
Chart.js). ECDF step curves, dot plots, and line series are all first-class
`Plot.line`/`Plot.dot` marks; no case here needs anything beyond it.

Alternatives considered: raw d3 (max control, ~4× the code, no gain for
these forms); uPlot (fast time series but a second dependency and its own
styling model, breaking the "tokens only" rule); Chart.js (banned by spec).

### D2 — Chart definitions

All charts: transparent figure background, JetBrains Mono, colors from
design-system tokens, one color per network class used consistently across
all three sections (ipv4, ipv6, onion, i2p — the same mapping the network
breakdown tiles already use).

1. **Block propagation — ECDF ("what fraction of announcers had the block
   after t ms")**
   - Aggregate view (default): x = ms since the block's first observed
     announcement (log scale, 100 ms – 5 min), y = cumulative fraction of
     that block's announcers, one `Plot.line` (step) per network class,
     median curve over the last N collected blocks.
   - Per-block view: same encoding for a single block selected from a
     compact table of recent blocks (height, short hash, announcer count,
     p50/p90 per class). Table rows follow the dense-table type scale.
   - Tooltip: network class, t, fraction; caption states the
     "first-heard-relative" definition.
2. **Services adoption — grouped horizontal bars + historical small
   multiples**
   - Latest snapshot: one horizontal bar per named flag
     (NODE_NETWORK, NODE_WITNESS, NODE_COMPACT_FILTERS,
     NODE_NETWORK_LIMITED, NODE_P2P_V2), value = % of reachable nodes
     advertising it, with a per-network split available as grouped bars
     (same layout family as the existing top-N bar charts).
   - History: small-multiple line charts (one per flag), x = date,
     y = adoption %, built from one sample per day (daily archive), so
     BIP324 and compact-filter adoption curves are visible at a glance.
   - Unknown/high bits are summed into an `other` row with the raw mask
     available in the tooltip — the data is surfaced, never silently
     dropped.
3. **Unique nodes — matrix band + composition bar**
   - Main page: the estimate is band 2 of the KPI matrix (see D7) with
     per-class weighted sums as its columns.
   - Research page: one stacked horizontal bar showing the composition —
     % of reachable addresses whose peer advertises 1, 2, or 3+ network
     types (the denominator of the weighting) — plus the method
     description, so the estimate is inspectable rather than a black box.

### D3 — Propagation collection: timer job persisting per-block JSON

A `queries/block_propagation.py` collector (invoked by a new
`alt-bitnodes-propagation` systemd service+timer, every 10 min) scans
`binv:*`, skips blocks already collected or still "hot" (first announcement
< 30 min ago, still accumulating), computes per-class percentiles and ECDF
points, and appends one JSON document per block under
`BITNODES_EXPORT_DIR`-adjacent storage (`propagation/` dir, one file per
block, pruned after 30 days). Serving reads files, never Redis.

Why not compute on request: zsets rotate (data loss), ZRANGE over hundreds
of zsets per request is needless Redis load, and the window-stats pattern
already proved the timer approach operationally.

### D4 — Services metrics: latest from snapshot, history sampled daily from the export dir

Latest-snapshot decoding is pure math over rows already in memory
(`lru_cache`d loads). The historical series samples the last snapshot of
each complete UTC day rather than iterating all ~1,500 snapshots — the
adoption curves move slowly; daily resolution is enough and keeps the
collector O(days), not O(snapshots). The same timer run refreshes the
series JSON.

Amended 2026-07-23 (review decision D1, pre-ship): the source is the raw
export dir, not the GFS photo archive as first drafted. The archive keeps
daily photos only 7 days (weekly/monthly beyond) so it cannot feed a
daily series past one week; the export dir covers the whole 90-day
backfill in native JSON, and the accumulated persisted series decouples
history from export pruning.

### D5 — Unique estimate: computed in the timer, threshold-free 1/N

For each address in the latest snapshot, read its `peer:*` key and count
the distinct network classes present in its advertised gossip: that is N
(minimum 1; peers with no gossip data count as N=1). The node estimate is
Σ 1/N. Runs in the timer (a SCAN + ~22k GETs is not request-path work),
persisted as JSON with the composition histogram. Documented limitation
(inherited from the method): multiple addresses of the same network type
cannot be deduplicated, and sparse onion gossip biases N low — the
composition bar makes this visible.

### D6 — API surface

- Legacy (dashboard): `GET /api/propagation`, `GET /api/services`,
  `GET /api/unique-nodes` — shaped exactly for the charts.
- Public v1 (windowed-stats precedent, trailing slashes):
  `GET /api/v1/stats/propagation/`, `GET /api/v1/stats/services/`,
  `GET /api/v1/stats/unique-nodes/`.
- MCP: `get_block_propagation`, `get_services_breakdown`,
  `get_unique_nodes_estimate` wrapping the same query functions.

### D7 — Two-page information architecture: KPI matrix on `/`, exploration on `/research`

Placement follows visitor intent, not chart count. The main page is
"the state of the network in 10 seconds": it gains a **three-band KPI
matrix** (from the maintainer's layout sketch, extended by one band)
sharing the same four columns — TOTAL, CLEARNET, TOR, I2P:

```
REACHABLE NODES — right now           │ COUNTRIES  ASNS  MEDIAN HEIGHT
UNIQUE estimate (1/N dedup) — now     │ services strip → /research
UNIQUE over 8 days (windowed)         │
```

The three bands form a ladder of definitions — raw instantaneous →
deduplicated instantaneous → windowed union — so the page itself makes
the project's core argument (the count depends on the definition).
Per-class 1/N weighted sums make band 2's columns methodologically sound
(they sum to the total estimate). Below the matrix, a numbers-only
services strip (BIP324, compact filters, pruned).

Everything exploratory moves to a new `/research` page (own template,
same design system, header nav tabs on both pages): the propagation ECDF
with drill-down (interactive — a different mode from the glanceable main
page), services history small multiples, and the unique-composition bar.

Rationale: keeps main-page first paint unchanged, separates "look" from
"operate" interactions, and gives the Delving post and MCP docs a stable
deep link (`/research`). Alternatives considered: everything on the main
page (rejected: infinite scroll, mixes modes, penalizes the majority
KPI-only visit); unique estimate as a right-cluster tile or an annotation
under the instantaneous total (rejected in review with the maintainer in
favour of the full band — the aligned columns are the story).

## Risks / Trade-offs

- [Collector SCAN load on a 355k-key Redis] → SCAN with bounded COUNT in a
  nice'd timer process, never in the request path; read-only commands only.
- [binv timestamps measure our crawler's view, not network truth] →
  relative-time ECDF framing, definition stated in chart caption and API
  docs; no absolute-latency claims.
- [Unique estimate biased for onion-heavy peers (sparse addr gossip)] →
  composition histogram published beside the number; documented limitation.
- [Timer job grows: propagation + services history + unique in one run] →
  single entrypoint with independent try/except per section, so one
  failure doesn't starve the others (lesson from the cron-greenlet
  postmortem).
- [Chart count grows page weight] → all sections render from one fetch
  each, lazily after the primary KPIs, keeping first paint unchanged.

## Migration Plan

1. Ship `queries/` modules + tests (inert).
2. Ship collector + systemd timer (starts writing JSON; nothing reads it
   yet). Verify output on prod.
3. Ship endpoints + dashboard sections + MCP tools.
4. Rollback at any step = disable timer / revert commit; no state to
   migrate, no crawler-side changes.

## Open Questions

- Percentile set for the propagation table: p50/p90 proposed; p99 is noisy
  with small announcer counts per block — decide with real collected data.
- Whether the services history should backfill from the full snapshot
  archive on first run (one-off cost) or start from deploy day. Proposed:
  backfill from daily archives, capped at 90 days.
