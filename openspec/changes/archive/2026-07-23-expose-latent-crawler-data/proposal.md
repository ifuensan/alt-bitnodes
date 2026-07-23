# Proposal: expose-latent-crawler-data

## Why

The crawler already collects three datasets that never reach the dashboard,
API, or MCP: per-node block/tx announcement timestamps (`binv:*`/`rinv:*`
Redis zsets), the `services` capability bitmask (stored in every snapshot row
but only ever displayed raw), and the `addr` gossip each peer advertises
(`peer:*`). Exposing them turns collected-but-invisible data into three
differentiated features no other public tracker offers together: block
propagation including Tor/I2P, protocol-capability adoption metrics
(BIP324, compact filters, pruned share), and an honest deduplicated
unique-node estimate.

## What Changes

- New data-layer modules in `queries/` reading `binv:*` zsets, decoding the
  `services` bitmask from snapshot rows, and computing a weighted
  unique-node estimate from `peer:*` gossip composition (1/N method as
  documented by 21.ninja).
- A timer-driven collector (window-stats/archiver pattern) that persists
  per-block propagation stats to JSON before the Redis zsets rotate out.
- New legacy `/api/*` endpoints feeding three new dashboard chart sections,
  and new `/api/v1/*` read-only endpoints for the public surface.
- A two-page information architecture: the main page keeps the at-a-glance
  role and gains a three-band KPI matrix (reachable now → unique 1/N
  estimate now → unique over the 8-day window, same four network columns
  per band, per the maintainer's layout sketch) plus a compact services
  strip; a new `/research` page hosts the exploratory charts — propagation
  ECDF with per-block drill-down, services adoption history small
  multiples, and the unique-estimate composition breakdown — all rendered
  with Observable Plot (the established framework, `dashboard-bar-charts`)
  and styled exclusively through design-system tokens.
- New MCP tools exposing the same three datasets through `alt_bitnodes_mcp`.
- RTT/latency stays out of scope — the `remove-rtt-pipeline` decision is
  not revisited (`ping:*` machinery remains unexposed).

## Capabilities

### New Capabilities

- `block-propagation`: collect, persist, and serve per-block announcement
  timing (percentile stats and ECDF curves, split by network class:
  IPv4/IPv6/onion/I2P), plus its dashboard chart and API endpoints.
- `services-breakdown`: decode the services bitmask into named capability
  flags (NODE_NETWORK, NODE_WITNESS, NODE_COMPACT_FILTERS,
  NODE_NETWORK_LIMITED, NODE_P2P_V2, …), serve adoption counts for the
  latest snapshot and a historical series from archived snapshots, plus
  dashboard charts and API endpoints.
- `unique-nodes-estimate`: infer each reachable peer's supported network
  types from the composition of its advertised `addr` gossip (`peer:*`),
  weight every reachable address 1/N, and serve the resulting deduplicated
  node estimate (total and per-network weighted sums) alongside raw
  reachable counts, plus dashboard display and API endpoint.
- `research-page`: a second dashboard page at `/research` hosting the
  exploratory chart sections, with header navigation between the two pages.

### Modified Capabilities

- `mcp-service`: the tool surface grows three read-only tools
  (`get_block_propagation`, `get_services_breakdown`,
  `get_unique_nodes_estimate`) mirroring the new query functions.

## Impact

- `queries/` — three new modules plus a propagation collector entrypoint;
  no changes to existing query functions.
- `app.py` — new legacy endpoints (dashboard) and new v1 endpoints
  (public API). Existing v1 routes unchanged (mcp-service contract).
- `templates/index.html`, `static/app.js`, `static/app.css` — three new
  chart sections consuming design-system tokens; no new chart library
  (Observable Plot + d3 already loaded).
- `alt_bitnodes_mcp/tools.py` — three new tools.
- `deploy/` — one new systemd service+timer pair for the propagation
  collector (same pattern as `alt-bitnodes-window-stats`).
- `tests/` — coverage for bitmask decoding, weighting math, propagation
  percentile computation, and new endpoints.
- Redis load: read-only `ZRANGE`/`SCAN` against existing keys; no new
  writes to crawler-owned keys.
