# Follow-ups

Backlog of non-blocking work surfaced during operations or research. Not
fechado: items live here until they're scheduled into a real change.
For dated incidents see `docs/postmortems/`. For full research artefacts
see `_bmad-output/planning-artifacts/`.

## RTT measurement

### Replace pcap-based RTT with active pings from `cache_inv`

**Status**: Open. Surfaced 2026-05-13 after the tcpdump-removal
experiment (snapshots stabilised at ~4000 once tcpdump was stopped,
confirming the sniffer was the cause of the oscillation we'd been
chasing for two days).

**Idea**: Today `cache_inv.py` reads `.pcap` files produced by
`tcpdump-pcap.service` to extract `pong` arrival times. The sniffer's
I/O and softirq load is what made snapshots oscillate. Replace the
passive sniffer with **active pinging from `ping.py` or `cache_inv.py`
itself**, recording RTT directly when each open socket gets its
`pong` back. Eliminates tcpdump from the critical path.

**Why not just optimise tcpdump (`-s 256`)**: tried at the conceptual
level but didn't apply — the user prefers to remove the sniffer
entirely. "Optimisations have bitten us before."

**Touch points**:

- `ping.py` (upstream `ifuensan/bitnodes`) — already sends pings; needs
  to also record the RTT timestamp when the matching pong arrives,
  write to `rtt:<addr>-<port>` in Redis.
- `cache_inv.py` — either becomes a no-op or pivots to consume the
  new Redis stream instead of pcap files.
- `tcpdump-pcap.service` and `run-tcpdump.sh` — eventually retired.

**Effort**: medium. Will require time on the fork to be careful.
Schedule alongside the I2P SAM crawl change (`feat/i2p-sam-crawl`)
or right after it.

### Multi-location RTT probes

**Status**: Aspirational. Mentioned 2026-05-13.

**Idea**: The RTT we measure today is "Virginia → peer". For a peer in
Madrid it can read ~120 ms from Virginia and ~10 ms from a Madrid
probe. To make latency genuinely useful as a node metric we'd need
**distributed probes** (e.g. 1 box per AWS region or via a CDN-tier
solution like Globalping/RIPE Atlas).

**Why not now**: cost + operational overhead. The current
single-location RTT is the same shape as Bitnodes' historical
implementation, so it's an acceptable baseline for v1 of the
dashboard.

## Operational

### Skip CI deploy on doc-only / openspec-only pushes

**Status**: Discussed and deferred 2026-05-12. User chose option C
("accept the restart per push"). May revisit if the friction
becomes meaningful once active crawler-code branches are in flight.

**Idea**: `.github/workflows/deploy.yml` only runs `install.sh` when
the diff touches `app.py`, `deploy/`, `static/`, `templates/`,
`requirements.txt`. Otherwise no-op.

### CloudFront access logs to S3

**Status**: Sonar hotspot `cloudformation:S6258` marked Safe
2026-05-13 because the omission is a deliberate phase-1 trade-off.
Reconsider if abuse investigation ever needs CDN-side data — see
`deploy/cloudformation/edge.yaml` comments and the public-edge
research thread.

## Testing

### Unit tests for the `queries/` data layer

**Status**: Deferred 2026-05-14 while archiving `expose-api-as-mcp`
(task 1.3). The `queries/` package was extracted as a pure, FastAPI-free
data layer precisely so it's testable, but the repo has no test infra
yet (no `tests/`, no pytest config).

**Idea**: Add `tests/` with minimal coverage of `queries/` — snapshot
loading, RTT median helpers, leaderboard/rankings, `node_status`,
`parse_node_id`. Either mock Redis/SQLite or run against fixtures with
real snapshot JSON. Pulls in pytest as the first test dependency.

**Why it matters**: both `app.py` and `alt_bitnodes_mcp/` now depend on
`queries/`; a regression there breaks the REST API and the MCP server at
once. Worth a safety net before the next refactor touches it.

## Crawler features

### I2P SAM crawl integration

**Status**: Research complete
(`_bmad-output/planning-artifacts/research/technical-bitcoin-i2p-nodes-crawling-research-2026-05-13.md`).
Estimated ~9h coding + ~4h infra. Branch `feat/i2p-sam-crawl` on
`ifuensan/bitnodes`. Next concrete coding session whenever the user
decides to start.
