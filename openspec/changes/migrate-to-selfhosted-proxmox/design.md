# Design — migrate-to-selfhosted-proxmox

## Context

Everything AWS-specific in the deployment is in four places:

- `deploy/cloudformation/edge.yaml` — ACM certificate, CloudFront
  distribution, security-group ingress from the CloudFront prefix list.
- `deploy/nginx/alt-bitnodes.conf.template` — the `X-Origin-Auth` gate and
  twenty `set_real_ip_from` CloudFront ranges.
- `deploy/install.sh` — `bootstrap_origin_secret`, `install_cloudwatch_agent`,
  the "Ubuntu 24.04 ARM64 / Graviton" assumptions in comments.
- `.github/workflows/deploy.yml` — SSH to `EC2_HOST` with `EC2_SSH_KEY`.

Things the EC2 has that the repo does not describe: the `/data` volume with
its bind mounts (built by hand on 2026-08-13), `/etc/netplan/60-ipv6.yaml`,
the VPC IPv6 block, the MaxMind key, and the three token files.

Home-side facts that constrain the design (validated 2026-08-01):

- Upload 573 Mbit/s; the crawler needs ~33 Mbit/s sustained.
- Digi's Zyxel router: bursts >~100 new connections/s are rate-limited (the
  crawler opens ~17/s — fine); ~6.5k held sessions OK; somewhere between 7k
  and 10k the household loses connectivity. Instant recovery on release.
- Digi may CGNAT the line. Inbound to the dashboard cannot be assumed.

## Goals / Non-Goals

**Goals**
- Same public surface, same URL, same MCP token, no code change in the app.
- Zero inbound ports at home. The tunnel is the only ingress.
- Installer that rebuilds the whole host from a bare Ubuntu VM, `/data`
  layout included.
- A safe path for the existing EC2 during the transition: no push to `main`
  may change what the EC2 renders until it is decommissioned.
- Before 2026-11-10.

**Non-Goals**
- Re-enabling Tor/I2P. Gated on ONT bridge + OPNsense; own change.
- Replacing CloudWatch with a monitoring stack. Follow-up.
- Terraform/Ansible for Proxmox. One VM, created by hand, documented.
- Keeping CloudFront. Considered and rejected below.

## Decisions

### 1. Edge: Cloudflare Tunnel, not CloudFront-over-relay, not direct TLS

Three options were on the table.

*Keep CloudFront with an AWS relay.* The clean t3.micro already running
would be the CloudFront origin, forwarding over WireGuard to the VM. Keeps
`edge.yaml` and the DNS untouched. Rejected: it keeps an AWS host to patch
and pay for, adds a WireGuard hop to operate, and still needs the
`X-Origin-Auth` + prefix-list dance. It only makes sense if leaving AWS were
not the goal.

*Direct TLS at home.* Public IP from Digi, port 443 on OPNsense, certbot.
Rejected for now: needs the ONT-bridge work that is exactly what the
overlays are waiting on, exposes the home IP, and is dead under CGNAT.

*Cloudflare Tunnel.* `cloudflared` on the VM opens outbound connections to
Cloudflare's edge; public hostnames route into them. TLS, HTTP/2, IPv6 and
static caching come from Cloudflare; no inbound port, CGNAT irrelevant.
Costs the nameserver move (`hacknodes.xyz` is at Namecheap) — public
hostnames on a tunnel require the zone on Cloudflare DNS. Free plan.

Locally-managed tunnel (config file + credentials JSON on the VM) rather
than the dashboard-managed token flavour: the ingress rules live in the
repo as `deploy/cloudflared/config.yml.template`, rendered by `install.sh`,
the same way nginx is. The credentials file is created once by
`cloudflared tunnel create` and treated like the token files.

### 2. nginx stays, on loopback

Cloudflare could point the tunnel straight at uvicorn, but nginx is doing
real work: the `/api/` rate limit, security headers, `/mcp/` SSE settings
(no buffering, 1h timeouts, the `Host` rewrite the MCP SDK insists on), and
the trailing-slash redirect fix. Keep it; change only:

- `listen 127.0.0.1:80` — nothing on the LAN reaches it.
- Drop the `X-Origin-Auth` `if` and `bootstrap_origin_secret`. The tunnel
  is authenticated by construction.
- Replace the CloudFront `set_real_ip_from` list with
  `set_real_ip_from 127.0.0.1; real_ip_header CF-Connecting-IP;` so
  `limit_req` and the access log keep seeing the real client.
- Keep `X-Forwarded-Proto https`; the app builds absolute URLs from it.

Two templates during the transition (`alt-bitnodes.conf.template` for
`cloudfront`, `alt-bitnodes-tunnel.conf.template` for `cloudflare`); the
first is deleted at teardown and the second renamed.

### 3. Marker files, not environment, select host behaviour

The deploy runs `sudo bash install.sh` over SSH with no environment (the
A/B arm learnt this the hard way). Anything that must differ between the
EC2 and the VM is therefore a file under `/etc/alt-bitnodes/`, read by the
installer, written once at provisioning:

| file | values | absent means | why that default |
|---|---|---|---|
| `edge` | `cloudfront` \| `cloudflare` | `cloudfront` | a push during the transition must not re-render the EC2's nginx |
| `crawler-profile` | `full` \| `clearnet` | `full` | matches the EC2's current confs, so the fingerprint does not change and the parked crawler is not touched |

Provisioning the VM writes `cloudflare` and `clearnet` before the first
`install.sh` run. At teardown the `edge` marker and its `cloudfront` branch
are deleted; `crawler-profile` stays — it is how overlays come back.

### 4. Crawler profile is a conf render plus unit gating

`clearnet` renders `onion = False` and `i2p = False` into
`crawl.f9beb4d9.conf` and `ping.f9beb4d9.conf` (both are boolean gates in
`crawl.py:268/273/530/578/584` and `ping.py:256/265`), and makes
`setup_tor_pool` / `setup_i2pd` provision but **not** enable-or-start
`tor@bitnodes*`, `tor@default` and `i2pd` (a `systemctl disable --now` when
the profile is `clearnet`, so switching back is provisioning-free). Tor
pool confs, `tor_proxies` and the I2P seed file are still rendered, so
flipping the marker to `full` and re-running the installer is the entire
procedure. The conf change moves `crawler_fingerprint`, so the crawler
restarts exactly when the profile changes.

Sizing for `clearnet` behind the Digi router: ping holds one socket per
reachable node (~6.4k IPv4+IPv6 in July) and crawl adds a transient few
hundred. That sits right at the ~6.5k figure that was validated clean. The
first day runs with `ss -s` sampled every minute and the household watched;
if sessions creep towards 7k, `workers` in `ping.f9beb4d9.conf` comes down
(each ping slave holds ≤ `workers` sockets) before anything else. The
router is the ceiling, not the VM.

### 5. Deploy reaches the VM through Cloudflare Access

Options: (a) self-hosted GitHub runner on the VM — gives the repo a foothold
inside the LAN and needs the runner patched; (b) pull-based timer on the VM
polling `origin/main` and the check-runs API — loses the synchronous smoke
test and the `cancel-in-progress: false` concurrency guarantee; (c)
Cloudflare Access SSH — the tunnel already exists, one more ingress rule
(`ssh.hacknodes.xyz → ssh://127.0.0.1:22`), one Access application with a
service token, and the runner uses `cloudflared access ssh` as
`ProxyCommand`. The rest of the workflow is unchanged. (c).

Secrets rename to lose the EC2 prefix: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`
(the Access hostname), `DEPLOY_USER`, `CF_ACCESS_CLIENT_ID`,
`CF_ACCESS_CLIENT_SECRET`. `known_hosts` is seeded from a
`DEPLOY_HOST_KEY` secret rather than `ssh-keyscan` (which cannot go through
the ProxyCommand).

### 6. `/data` volume, reproduced by the installer

The 2026-08-13 layout is kept as-is because the argument for it has not
changed: bind mounts keep every path identical under `ProtectHome` +
`ReadWritePaths`, and a full data disk stops collection instead of the OS.
`setup_data_volume` in `install.sh`: if `/data` is a mountpoint, create the
five directories, add the bind entries to `/etc/fstab` if missing, `mount -a`;
if `/data` is not a mountpoint, warn loudly and continue (a dev box). The
VM gets a second virtual disk for it (80 GiB, ext4, `nofail`).

### 7. Data copy, then cutover, then teardown — in that order

The VM has no public address, so it *pulls* from the EC2 with rsync over
SSH. What moves: the export JSONs (history back to May, prune frozen), the
dashboard `data/` (archive tiers, propagation), Redis (`redis-cli save`,
copy `dump.rdb` into the stopped VM Redis — carries `height`, `opendata`
and the last live state so the dashboard is not empty while the crawler
warms), `/etc/alt-bitnodes/{mcp-token,research-token}` (clients keep
working), the MaxMind key. Not copied: `data/unique-nodes.json` (retired),
crawler confs and logs, venvs.

Cutover is a DNS flip on a zone already at Cloudflare: `pesquisa` CNAME
from `dxxxx.cloudfront.net` (DNS-only) to `<tunnel-id>.cfargotunnel.com`
(proxied). Verified beforehand on a temporary `pesquisa-next` hostname on
the same tunnel using `deploy/smoke-test-v2.sh`. Rollback is the same flip
in reverse as long as the CloudFormation stack is still up — which is why
teardown waits a few days.

Teardown: delete `alt-bitnodes-edge` stack, WAF, CloudWatch dashboards and
the two idle EIPs immediately; final EBS snapshot; stop the instance;
terminate and release its EIP once the VM has run a full archive cycle.
Terminating does not refund the Savings Plan, so nothing is gained by
waiting for 2026-11-10 — and something is lost if it is missed.

## Risks

- **Household degradation** if sessions climb past ~7k. Mitigation: profile
  `clearnet`, ping `workers` as the throttle, watch the first day.
- **Nameserver move** breaks anything else on `hacknodes.xyz`. Mitigation:
  copy every record into Cloudflare (DNS-only) before changing NS; verify
  with `dig @1.1.1.1`.
- **Cloudflare caches HTML.** Default cache rules do not cache HTML, and
  static assets carry `?v=<sha>`, so a deploy never serves stale JS. A
  cache rule bypassing `/api/*` and `/mcp/*` is set explicitly anyway.
- **SSE through Cloudflare.** Free-plan proxied connections have a 100 s
  idle timeout on responses. MCP sessions already reconnect on the 1h
  nginx cap; verify a long tool call streams keep-alives inside 100 s or
  document the reconnect.
- **Home power / ISP outage** takes the observatory down with no failover.
  Accepted: it is a research instrument, and the archive tiering tolerates
  gaps. A UPS for the Proxmox host is a follow-up.
