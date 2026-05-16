# Follow-ups

Backlog of non-blocking work surfaced during operations or research. Not
fechado: items live here until they're scheduled into a real change.
For dated incidents see `docs/postmortems/`. For full research artefacts
see `_bmad-output/planning-artifacts/`.

## Operational

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
loading, rankings, `node_status`, `parse_node_id`. Either mock Redis
or run against fixtures with real snapshot JSON. Pulls in pytest as
the first test dependency.

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
