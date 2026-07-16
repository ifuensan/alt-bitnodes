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

**Status**: Done 2026-07-16. Added `tests/` (34 tests over
`snapshots`, `nodes`, `leaderboard`, `util`), `pytest.ini`,
`requirements-dev.txt`, and a CI test job gating the deploy in
`.github/workflows/deploy.yml`. Redis is faked in `tests/conftest.py`;
snapshot fixtures are written to a temp `BITNODES_EXPORT_DIR`.
Remaining idea if ever needed: endpoint-level tests for `app.py` via
`fastapi.testclient` and coverage of `alt_bitnodes_mcp/tools.py`.

## Crawler features

### I2P SAM crawl integration

**Status**: Research complete
(`_bmad-output/planning-artifacts/research/technical-bitcoin-i2p-nodes-crawling-research-2026-05-13.md`).
Estimated ~9h coding + ~4h infra. Branch `feat/i2p-sam-crawl` on
`ifuensan/bitnodes`. Next concrete coding session whenever the user
decides to start.
