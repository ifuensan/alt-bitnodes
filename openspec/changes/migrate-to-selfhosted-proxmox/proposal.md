## Why

Production has been half-parked since 2026-08-01. The scaled crawler pushes
~356 GB/day of egress — over 99% of it Tor and I2P overlay machinery — which
at AWS transfer rates is ~$22/day, ~$660/month, for a research observatory
whose Bitcoin-protocol bytes are a rounding error. The decision to leave AWS
for self-hosted Proxmox was taken that day (see
`docs/postmortems/2026-08-01-egress-cost-anomaly-false-positive.md`, stage 9
of `docs/delving-draft-stages.md`, and the migration entry in
`docs/follow-ups.md`). Compute is prepaid until **2026-11-10**, so the move is
unhurried but has a hard end date: after that the instance bills on-demand.

Since then the dashboard has served a frozen snapshot (~14.4k nodes) and the
8-day windowed series has stopped advancing. Every week parked is a week of
missing observatory data.

The home side has been validated: 573 Mbit/s upload with no bufferbloat, and
the crawler's ~33 Mbit/s sustained fits in ~6% of it. The stock Digi router
holds ~6.5k concurrent sessions cleanly and degrades the whole household
between ~7k and 10k, so the full 40k-connection overlay profile needs the
ONT bridge + own router (OPNsense on Proxmox) first. Clearnet alone is
~6.4k reachable nodes and fits today.

## What Changes

**Platform.** Production moves from the c7g.2xlarge EC2 to an Ubuntu 24.04
VM on the existing home Proxmox host. Same stack (Python 3.12, Redis, Tor
pool, i2pd, nginx, systemd units); architecture-portable, x86-64 now.

**Public edge.** CloudFront + ACM + the `edge.yaml` CloudFormation stack are
replaced by a **Cloudflare Tunnel** (`cloudflared` as a systemd unit on the
VM). Nothing inbound is opened at home; CGNAT is irrelevant. nginx stays as
the local reverse proxy (rate limiting, security headers, `/mcp/` SSE
handling) but listens on loopback only, drops the `X-Origin-Auth` gate (the
tunnel is the only path in) and takes the client IP from `CF-Connecting-IP`.
The `hacknodes.xyz` zone moves to Cloudflare DNS.

**Deploy path.** GitHub Actions can no longer SSH straight to the host. The
workflow reaches it through **Cloudflare Access** (`cloudflared access ssh`
as `ProxyCommand`, service-token authenticated). The push → test → deploy →
smoke-test semantics, the `deploy-prod` concurrency group and the docs-only
skip all stay as they are.

**Installer.** `deploy/install.sh` becomes host-agnostic through two marker
files under `/etc/alt-bitnodes/`, in the same spirit as `parked-units`:

- `edge` — `cloudfront` (legacy) or `cloudflare`. Absent means `cloudfront`
  so no push during the transition can change the behaviour of the EC2.
- `crawler-profile` — `full` (legacy) or `clearnet`. `clearnet` renders
  `onion = False` / `i2p = False` into both crawler confs and keeps the
  `tor@` pool and `i2pd` stopped. Absent means `full`.

It also learns the `/data` layout that was hand-built on 2026-08-13 (bind
mounts for exports, logs, dashboard data and Redis), so a rebuilt host does
not silently put collected data back on the root volume. The CloudWatch
agent is only installed under `edge = cloudfront` and is deleted from the
repo together with `edge.yaml` at teardown.

**Data.** Snapshot history (prune frozen since 2026-08-01), the Parquet/CSV
archive, propagation data, the Redis RDB and the MCP/research tokens are
copied from the EC2 to the VM before cutover, so the public API, the archive
tiering and the MCP clients see no discontinuity beyond the parked gap.

**Cutover and teardown.** DNS flips `pesquisa.hacknodes.xyz` from the
CloudFront CNAME to the tunnel CNAME; then the CloudFormation stack, WAF,
CloudWatch dashboards and idle Elastic IPs go, the EC2 is stopped behind a
final EBS snapshot and terminated before 2026-11-10.

**Out of scope, deliberately.** Turning the overlays back on. That is gated
on the ONT bridge + OPNsense work and gets its own change; this one leaves
the switch a one-line marker edit plus a re-run of the installer, and
records the procedure.

## Capabilities

### New Capabilities
- `deployment-pipeline`: how a commit on `main` reaches the production host
  when that host has no public inbound path — Cloudflare Access SSH from the
  GitHub runner, host-agnostic installer driven by marker files, data-volume
  layout the installer reproduces.

### Modified Capabilities
- `public-edge`: TLS, origin isolation, caching, rate limiting and the
  operational docs are re-specified for Cloudflare Tunnel; every CloudFront /
  CloudFormation / security-group requirement is removed.
- `crawler-systemd-units`: the installer applies a crawler network profile
  (`full` | `clearnet`) that gates onion/I2P dialing and the overlay daemons.

## Impact

- **New**: `deploy/cloudflared/config.yml.template`, `deploy/nginx/`
  loopback template variant, `setup_data_volume`, `apply_crawler_profile`
  and `setup_cloudflared` in `install.sh`; a "Deploy on a Proxmox VM"
  section in `deploy/README.md`.
- **Modified**: `deploy/install.sh` (marker files, conditional edge,
  conditional CloudWatch), `.github/workflows/deploy.yml` (Cloudflare Access
  ProxyCommand, renamed secrets), `deploy/README.md`, `docs/follow-ups.md`.
- **Removed at teardown (phase 6)**: `deploy/cloudformation/edge.yaml`,
  `deploy/cloudwatch-agent.json`, `install_cloudwatch_agent`,
  `bootstrap_origin_secret`, the CloudFront `set_real_ip_from` list.
- **Unchanged**: `app.py`, `queries/`, `alt_bitnodes_mcp/`, every unit file
  under `deploy/` except where a path placeholder moves; the crawler fork
  needs no code change (`onion` and `i2p` are already boolean gates in
  `crawl.py` and `ping.py`).
- **Operational**: nameserver change for `hacknodes.xyz`; a Cloudflare
  account with a tunnel, two public hostnames and one Access application;
  a VM on Proxmox with two virtual disks; a one-time data copy.
- **Cost**: AWS from ~$200/month compute + ~$660/month egress to $0.
  Cloudflare free plan covers the tunnel, DNS and Access (≤50 users).
  Marginal cost at home: electricity for a VM that was already budgeted.
- **Risk**: the household network. `clearnet` is sized to stay under the
  ~6.5k-session ceiling of the Digi router; `full` must not be enabled
  before the ONT bridge + OPNsense are in place and re-tested.
- **Interaction with `retire-unique-nodes-estimate`**: its open tasks 5.3
  and 5.4 (delete stale `data/unique-nodes.json` on the host, keep parked
  units parked through the deploy) resolve here — the file is simply not
  copied to the VM, and the profile marker replaces parking as the way
  overlays stay off.
