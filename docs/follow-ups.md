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

### Onion ramp-up after the multi-Tor pool

**Status**: `scale-onion-crawling-multi-tor` deployed 2026-07-16. Onion
counts went 12 → 226 in the first ~2h and were still climbing, with no
Tor saturation (18 circuit-pending mentions in 30 min vs ~1M/10 min in
the 2026-05-12 incident). Re-check in a few days: if the onion count
plateaus in the hundreds instead of thousands, the next lever is the
ping stack (`ping.workers` 600, 6 slaves) — snapshots count
*simultaneously open* sockets, and slow Tor sockets compete for those
slots — not more Tor instances.

### IPv6 connectivity

**Status**: Done 2026-07-17, AWS-side only (no repo change). VPC
`vpc-028219a15ed6cde2e` got Amazon-provided `2600:1f18:4614:4600::/56`;
subnet `subnet-013a3bf06e170e6a2` took the first /64; ENI
`eni-03cec437a852efaad` assigned `...:680:fc28:1dcb:db6a`; route
`::/0 -> igw-067cbb0e57ec7e4fb` added to `rtb-0195dc5dc21bc91f2`; SG
egress already allowed `::/0`. On the host, `/etc/netplan/60-ipv6.yaml`
enables `dhcp6: true` on ens5 (persistent). Egress verified with
`curl -6`. The crawler already ran with `ipv6 = True`, so IPv6 nodes
ramp up without a restart. Note: none of this is in CloudFormation
(edge.yaml only covers CloudFront) — if the VPC is ever rebuilt, redo
by hand or codify then.

### I2P SAM crawl integration

**Status**: Research complete
(`_bmad-output/planning-artifacts/research/technical-bitcoin-i2p-nodes-crawling-research-2026-05-13.md`).
Estimated ~9h coding + ~4h infra. Branch `feat/i2p-sam-crawl` on
`ifuensan/bitnodes`. Next concrete coding session whenever the user
decides to start.
