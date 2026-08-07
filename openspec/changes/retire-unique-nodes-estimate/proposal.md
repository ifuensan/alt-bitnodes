## Why

The published 1/N unique-node estimate does not measure what it claims, and
the quantity it claims to measure is not observable at all. Two independent
findings, both verified:

1. **Wrong input.** N is derived from the crawler's `peer:*` Redis keys. In
   the fork's `crawl.py`, that key caches the result of `get_peers(conn)` —
   the response to a `GETADDR`, i.e. the addresses that peer knows about
   *other* nodes (its addrman sample). It is not the peer's own addresses.
   So N measures the network diversity of a node's address book, not the
   number of networks that node is reachable on. A clearnet-only node with a
   varied addrman (the common case — Core stores onion and I2P addresses
   whether or not it can dial them) is weighted 1/3 or 1/4 and counted as a
   fraction of a node. The estimate deflates silently, producing
   plausible-looking but wrong numbers.

2. **Unobservable target.** Fixing the input would not help. Cross-network
   deduplication requires linking a node's IPv4 address to its `.onion` or
   `.b32.i2p` address, and that link is not disclosed. Bitcoin Core
   self-advertises via `MaybeSendAddr()` → `GetLocalAddrForPeer(CNode&)`,
   which selects an address appropriate for *the network of the peer being
   talked to*: a node reached over IPv4 announces its IPv4, a node reached
   over Tor announces its onion. Unlinkability across networks is the design
   goal of Tor and I2P; no crawler observation defeats it.

Publishing a deduplicated count therefore cannot be made correct. Keeping it
would undermine the project's core claim — that measurement methodology is
stated precisely enough to be contested — right where that claim matters most.

The defect is currently masked: with the crawler stopped there is no gossip
data, every address falls back to N = 1, and the estimate equals the raw
reachable count (14,397 → 14,397). It will start producing wrong numbers
again as soon as the crawler resumes.

## What Changes

- **BREAKING**: remove the `GET /api/v1/stats/unique-nodes/` public endpoint
  and the legacy `GET /api/unique-nodes` endpoint.
- Remove the 1/N computation (`queries/unique_nodes.py`) and its section in
  the collector timer, along with the persisted `unique-nodes.json` cache.
- Remove band 2 (the 1/N estimate) from the main-page KPI matrix, leaving the
  two honest bands: reachable now, and windowed unique counts.
- Remove the N-composition stacked bar from the research page.
- Add, in its place, a short methodology note on the research page stating why
  no deduplicated node count is published — that address counts are not
  machine counts, and that cross-network linkage is not observable — and
  pointing to the windowed unique-node metric as the comparable figure.
- Remove the MCP tool exposure of the estimate, if present.

Not in scope: self-announcement capture (distinguishing a node's own address
from relayed gossip, and detecting nodes that leak an address from a network
other than the connection's). That is a genuinely new measurement capability
with its own crawler-side work, and it belongs in a separate change; the
methodology note deliberately does not promise it.

## Capabilities

### New Capabilities

_None._

### Modified Capabilities

- `unique-nodes-estimate`: the capability is retired. All of its requirements
  (computation, endpoints, KPI band, research-page composition) are removed
  and replaced by a single requirement: publish a methodology note explaining
  why no deduplicated count is served.
- `research-page`: the unique-node composition section is replaced by the
  methodology note.
- `mcp-service`: drops the unique-estimate tool/resource if it exposes one.

## Impact

- **Code**: `queries/unique_nodes.py` (deleted), `collector.py` (section
  removed), `app.py` (two endpoints removed), `static/research.js` +
  `templates/` (composition chart replaced by note), `queries/config.py`
  (`UNIQUE_STATS_FILE` removed), `alt_bitnodes_mcp/` (if it exposes the
  estimate), and the corresponding tests.
- **API consumers**: the v1 endpoint is public and bitnodes.io-adjacent;
  removal is breaking. Given the numbers it returns are wrong, removal is
  preferable to a deprecation window, but the response should not simply
  vanish without explanation — see design.md for the 410 vs 404 decision.
- **Data**: the persisted `data/unique-nodes.json` becomes obsolete and is
  removed on deploy.
- **Documents outside this repo** that cite the metric need updating: the
  NLnet grant draft lists weighted unique-node counts as deliverable T3, and
  the archived `expose-latent-crawler-data` change describes the 1/N work as
  delivered. Both are tracked in `docs/follow-ups.md` rather than here.
