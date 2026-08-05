# Follow-ups

Backlog of non-blocking work surfaced during operations or research. Not
fechado: items live here until they're scheduled into a real change.
For dated incidents see `docs/postmortems/`. For full research artefacts
see `_bmad-output/planning-artifacts/`.

## Operational

### Migrate production off AWS to self-hosted Proxmox

**Status**: Decided 2026-08-01. Driver: egress cost — the scaled
crawler pushes ~356 GB/day (>99% Tor/I2P overlay machinery, ~0.1%
Bitcoin protocol), ~$22/day at AWS transfer rates (~$660/month). See
`docs/postmortems/2026-08-01-egress-cost-anomaly-false-positive.md`
and stage 9 of `docs/delving-draft-stages.md`.

**2026-08-01, cost contained**: the traffic generators are STOPPED and
disabled on the EC2 host (`bitnodes.service`, `i2pd`, `tor@*`, and
`export-prune.timer` — frozen so the 90-day retention doesn't erode the
snapshot history before the move). Dashboard/API/MCP stay up serving
the last snapshot (~14.4k nodes); egress measured ~8 KB/s afterwards
(≈ $0/day). **Caution**: a non-docs push to main triggers the deploy
and `install.sh` may re-enable the crawler — avoid deploys until the
migration, or guard `install.sh` first.

**Provider cost comparison (2026-08-01)**: AWS resumed ≈ €600-780/mo.
Hetzner CAX31 (8 ARM vCPU/16GB, 20TB included) ≈ €16-21/mo, CAX41
(16/32GB) ≈ €31-41/mo — caveat: Hetzner's netscan/abuse detection may
flag a crawler opening connections to thousands of IPs. OVH VPS
(8 vCore, unmetered) ≈ €25-35/mo. Oracle free tier no longer viable
(cut to 2 OCPU/12GB in June 2026). Second home fiber line, separate
ONT/provider, dedicated to the crawler: Finetwork 1Gb €25/mo (own
network), O2 €31/mo (Movistar network, no permanence) — plus own
router/OPNsense (€0, VM), full isolation from the household line,
unmetered, no cloud AUP risk; needs UPS + DDNS/tunnel for the
dashboard origin. Both paths cut the bill >95%.

**Home-router NAT validation (2026-08-01)**: Digi's Zyxel (MT7988)
rate-limits connection bursts >~100/s (SYN-flood protection; the real
crawler opens ~17/s — compatible), accumulates cleanly to ~6.5k
concurrent sessions, but somewhere between ~7k and 10k held sessions
**the whole household degrades** (new connections from any device fail;
instant recovery on release). Verdict: the 40k-connection crawler
profile does not fit behind the stock Digi router — plan for ONT
bridge + own router (OPNsense VM on Proxmox, high conntrack) and
likely a public IP from Digi, then re-test. Fallback: a detuned
crawler (~5k sessions).

Notes for the migration:
- No urgency: compute is prepaid (all-upfront Savings Plan until
  2026-11-10); data transfer is the only marginal AWS cost, and it
  stops the moment the crawler moves.
- Bandwidth budget on the new host: ~33 Mbit/s *sustained* upload.
  Validated 2026-08-01 from the home LAN (Digi fiber, Madrid):
  **573 Mbit/s** measured upload to Cloudflare, latency under full
  upload load 6.7 ms vs 6.3 ms baseline (no bufferbloat). The crawler
  would use ~6% of uplink. Remaining risks to validate on-site: home
  router NAT/conntrack under ~40k concurrent flows + ~1k new
  connections/min (consider ONT bridge + own router/OPNsense, or raise
  `nf_conntrack_max`); inbound path for the dashboard origin (Digi may
  CGNAT — a Cloudflare Tunnel sidesteps it entirely; the crawler
  itself is outbound-only and unaffected); Digi AUP on ~11 TB/month
  sustained upload (no known caps).
- Current instance is ARM (c7g/Graviton); the stack (Python, Tor,
  i2pd, Redis, nginx) is architecture-portable.
- Decide the public edge: keep CloudFront pointing at the new origin
  (free tier covers the dashboard) or drop it and terminate TLS
  locally. `deploy/install.sh` placeholders make the host swap mostly
  mechanical; the CloudFront prefix-list SG trick has no LAN
  equivalent — rethink origin protection.
- On the way out: release the idle Elastic IPs (34.206.227.120 /
  3.219.165.64), review WAF (~$30/month) and CloudWatch dashboards
  (~$9/month) — they die with the AWS footprint.

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

## Dashboard content

### "About / Methodology" page for pesquisa.hacknodes.xyz

**Status**: Open 2026-07-22. Write an About/Methodology section for our
dashboard, adapted from two sources:

1. **bitnodes.io original "About" text** (to adapt, not copy verbatim —
   ours crawls IPv4/IPv6/onion/I2P and lives in the `ifuensan/bitnodes`
   fork):
   > Bitnodes is currently being developed to estimate the size of the
   > Bitcoin network by finding all the reachable nodes in the network.
   > The current methodology involves sending getaddr messages
   > recursively to find all the reachable nodes in the network,
   > starting from a set of seed nodes. Bitnodes uses Bitcoin protocol
   > version 70001 (i.e. >= /Satoshi:0.8.x/), so nodes running an older
   > protocol version will be skipped. The crawler implementation in
   > Python is available from GitHub (ayeowch/bitnodes) and the crawler
   > deployment is documented in Provisioning Bitcoin Network Crawler.
   >
   > The crawler maintained by Bitnodes connects from these IP
   > addresses: 88.99.167.175, 88.99.167.186, 2a01:4f8:10a:37ee::2
   Our adaptation should state *our* crawl origin addresses (EC2 EIP +
   IPv6), the fork lineage, and the networks covered.

2. **21.ninja methodology pages** (reviewed 2026-07-22), two ideas
   worth considering:
   - `reachable-nodes/methodology`: DNS-seed bootstrap + recursive
     getaddr like ours; they discard advertised addresses older than
     **48h** before dialing (reachability drops exponentially with age).
     We currently rely on the crawler's 5-day max node age instead.
   - `unique-reachable-nodes/methodology`: estimates *unique nodes*
     (vs reachable addresses) by inferring each peer's supported
     network types from the composition of its addr advertisements,
     then weighting each address 1/N (N = network types detected), so a
     dual-stack+Tor node counts 1.0 instead of 3. Known limitation:
     can't dedupe multiple addresses of the same network type. Could
     complement our 5-day rolling-window unique count.

### I2P SAM crawl integration

**Status**: Done 2026-07-19. Live in production: 4.7k reachable I2P nodes.
Required three fixes beyond the initial SAM client (validated only against
a fake bridge): seed nodes (clearnet peers don't gossip I2P — ship 512
mainnet seeds from bitcoin/bitcoin), INFO instrumentation, and THE bug —
serialize_network_address classified .b32.i2p as IPv4 (it has dots) and
crashed the Bitcoin version handshake on inet_pton. No upstream PR
(ayeowch/bitnodes unmaintained); the fork is the living lineage.
