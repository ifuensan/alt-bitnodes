# Deploy alt-bitnodes

Single-node deployment that runs the bitnodes crawler stack and the
alt-bitnodes dashboard on one Ubuntu 24.04 LTS host: a VM on the home
Proxmox host behind a Cloudflare Tunnel. It ran on an AWS EC2 behind
CloudFront from May to September 2026; that setup and the reasons for
leaving it are in `openspec/changes/archive/*-migrate-to-selfhosted-proxmox/`
and `docs/postmortems/2026-08-01-egress-cost-anomaly-false-positive.md`.

## Deploy on a Proxmox VM (Cloudflare Tunnel edge)

### 1. The VM

| item | value | why |
|---|---|---|
| image | Ubuntu 24.04 cloud image | cloud-init for user/key/IP |
| CPU / RAM | 8 vCPU (type `host`), 16 GiB | same as the c7g.2xlarge the tuning was calibrated on |
| `scsi0` | 20 GiB | root: OS, venvs, journal (capped at 200M) |
| `scsi1` | 80 GiB | `/data`: exports, archive, Redis, logs — a full data disk stops collection, not the OS |
| NIC | VirtIO on the LAN bridge, static IP via cloud-init | the tunnel is outbound-only; no port forward |
| extras | `qemu-guest-agent`, `serial0`, start on boot, weekly vzdump of root | |

Inside the VM, once:

```bash
sudo apt update && sudo apt full-upgrade -y
sudo mkfs.ext4 -L data /dev/sdb
echo 'LABEL=data /data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mkdir -p /data && sudo mount -a

# Nothing inbound except LAN SSH. The web path and CI SSH come through the tunnel.
sudo ufw default deny incoming
sudo ufw allow from 192.168.1.0/24 to any port 22    # your LAN
sudo ufw enable

# ~10k sockets for the clearnet profile; the unit already sets LimitNOFILE.
sudo tee /etc/sysctl.d/90-crawler.conf >/dev/null <<'EOT'
fs.file-max = 262144
net.ipv4.ip_local_port_range = 10240 65000
net.core.somaxconn = 4096
EOT
sudo sysctl --system
```

### 2. Marker files

`install.sh` reads its host-specific switches from files, never from the
environment (the deploy runs it over SSH with none). Write the profile
**before** the first run:

```bash
sudo install -d -m 0750 /etc/alt-bitnodes
echo clearnet | sudo tee /etc/alt-bitnodes/crawler-profile
```

| file | values | effect |
|---|---|---|
| `crawler-profile` | `clearnet` \| `full` | `onion`/`i2p` in both crawler confs, crawl `workers`; Tor pool + i2pd provisioned but stopped under `clearnet` |
| `parked-units` | unit names | never enabled/started by a deploy, whatever the profile |

`clearnet` is the profile the stock Digi router can carry (~6.5k held
sessions validated clean, household degrades between 7k and 10k). Switch
to `full` only after the ONT bridge + OPNsense are in and re-tested at 40k.

### 3. Cloudflare

1. Add `hacknodes.xyz` to Cloudflare; recreate every record **DNS-only**;
   move the nameservers at the registrar; wait for *Active*.
2. On the VM:
   ```bash
   curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
   echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' | sudo tee /etc/apt/sources.list.d/cloudflared.list
   sudo apt update && sudo apt install -y cloudflared
   cloudflared tunnel login                 # browser auth, writes ~/.cloudflared/cert.pem
   cloudflared tunnel create alt-bitnodes   # prints the tunnel id, writes ~/.cloudflared/<id>.json
   sudo install -d -m 0755 /etc/cloudflared
   sudo install -m 0600 ~/.cloudflared/<id>.json /etc/cloudflared/<id>.json
   ```
3. DNS records (proxied) for the public hostnames:
   ```bash
   cloudflared tunnel route dns alt-bitnodes pesquisa.hacknodes.xyz   # or pesquisa-next while validating
   cloudflared tunnel route dns alt-bitnodes ssh.hacknodes.xyz
   ```
4. Cache rule (Caching → Cache Rules): *Bypass cache* when URI path starts
   with `/api/` or `/mcp/`. Static assets keep the defaults; their URLs
   carry `?v=<commit>` so a deploy never serves a stale file.
5. Zero Trust → Access → Applications: self-hosted app for
   `ssh.hacknodes.xyz`, policy *Service Auth* with a new **service token**.
   Keep the client id/secret for the GitHub secrets.
6. Tell the installer about the tunnel:
   ```bash
   sudo tee /etc/alt-bitnodes/cloudflared.env >/dev/null <<'EOT'
   TUNNEL_ID=<id>
   PUBLIC_HOST=pesquisa.hacknodes.xyz
   SSH_HOST=ssh.hacknodes.xyz
   EOT
   ```
   The ingress rules themselves are in the repo
   (`deploy/cloudflared/config.yml.template`); the installer renders and
   restarts `cloudflared` only when they change.

### 4. Data from the previous host (migration only)

The VM pulls; it is the side without a public address. Skip
`unique-nodes.json` (retired metric). Do this before the first
`install.sh` so Redis starts on the copied RDB.

```bash
sudo mkdir -p /data/{bitnodes-data/export,alt-bitnodes-data,redis}
sudo rsync -aH --info=progress2 ubuntu@<old-host>:/data/bitnodes-data/export/ /data/bitnodes-data/export/
sudo rsync -aH --exclude unique-nodes.json ubuntu@<old-host>:/data/alt-bitnodes-data/ /data/alt-bitnodes-data/
sudo rsync -a ubuntu@<old-host>:/data/redis/dump.rdb /data/redis/     # after `redis-cli save` there
sudo chown -R redis:redis /data/redis
for f in mcp-token research-token; do
  ssh ubuntu@<old-host> "sudo cat /etc/alt-bitnodes/$f" | sudo tee /etc/alt-bitnodes/$f >/dev/null
done
ssh ubuntu@<old-host> 'cat ~/bitnodes/geoip/.maxmind_license_key' > /tmp/mm && mkdir -p ~/bitnodes/geoip && install -m 0600 /tmp/mm ~/bitnodes/geoip/.maxmind_license_key
```

Same tokens on the new host means every MCP client and the research page
keep working across the cutover.

### 5. First install and checks

```bash
curl -fsSLO https://raw.githubusercontent.com/ifuensan/alt-bitnodes/main/deploy/install.sh
sudo bash install.sh
```

Expect, in order: apt + Redis, Tor pool provisioned **and stopped**, i2pd
installed **and stopped**, pyenv, both repos, `/data` binds
(`findmnt ~/bitnodes/data`), units, nginx on `127.0.0.1:80`, `cloudflared`
active, and the final line `Done (edge=cloudflare, crawler-profile=clearnet)`.

```bash
grep -E '^(onion|i2p) ' ~/bitnodes/conf/crawl.f9beb4d9.conf    # both False
systemctl is-active bitnodes alt-bitnodes alt-bitnodes-mcp cloudflared
systemctl is-active tor@bitnodes1 i2pd                            # inactive
ss -ltn                                                            # 22 on LAN, everything else on 127.0.0.1
redis-cli scard up                                                 # climbing
curl -fsSI https://pesquisa.hacknodes.xyz/                         # 200, Cloudflare cert
curl -sI  https://pesquisa.hacknodes.xyz/api/v1/snapshots/latest/ | grep -i cf-cache-status   # DYNAMIC/BYPASS
```

The `clearnet` profile also sets crawl `workers = 40` (vs 1200 on the
EC2), crawl `socket_timeout = 15` and a 2-day `max_age` for gossiped
addresses (fewer and shorter attempts to dead addresses). Behind the Digi router the limit is new IPv4 connections per second
(~100/s before its SYN-flood protection drops them), not CPU or held
sessions: 1200 workers gave 627 IPv4 nodes per cycle, 40 gave 4842. Cycles
take ~2 h instead of 30 min. Do not raise it until the ONT bridge + own
router are in. Watch the first day with the external-socket log in
`/var/log/alt-bitnodes/sessions.log` (note `ss -s` counts loopback Redis
connections too; only external ones reach the router).

### 6. Enabling the overlays later

Only after the ONT bridge + own router are in place and re-tested:

```bash
echo full | sudo tee /etc/alt-bitnodes/crawler-profile
sudo bash ~/alt-bitnodes/deploy/install.sh   # starts tor@*, i2pd; restarts the crawler once
```

Onion takes ~13 h to plateau; I2P bootstraps from the shipped seeds.

### 7. CI deploys through Cloudflare Access

The workflow SSHes to `ssh.hacknodes.xyz` with
`ProxyCommand cloudflared access ssh --hostname %h` and the service token.
Secrets in the `PRO` environment: `DEPLOY_SSH_KEY`, `DEPLOY_HOST`,
`DEPLOY_USER`, `DEPLOY_HOST_KEY` (`ssh-keyscan <vm-lan-ip>` run from the
LAN — the runner cannot keyscan through the proxy), `CF_ACCESS_CLIENT_ID`,
`CF_ACCESS_CLIENT_SECRET`.

### Rollback

There is no second host. Rollback is the VM's vzdump plus the final EBS
snapshots left in AWS (`alt-bitnodes-final-2026-09-20-root/-data`,
us-east-1), which hold the EC2's root and `/data` as of the cutover.

---

## Legacy: AWS EC2

From 2026-05-10 to 2026-09-20 production was a c7g.2xlarge (later
m7g.large) in us-east-1 behind CloudFront + ACM, with nginx gating the
origin on a shared `X-Origin-Auth` header and a security-group rule for the
CloudFront prefix list, provisioned by `deploy/cloudformation/edge.yaml`
and monitored by the CloudWatch agent. All of it is gone from the repo and
from AWS; the archived migration change and the git history keep the
procedure if it is ever needed again.

## MCP service

`alt-bitnodes` also exposes its data through a **Model Context Protocol**
server so LLM clients (Claude Desktop, Claude Code, etc.) can query the
network directly. Same Redis/SQLite reads as the REST API — no new data
store, no writes.

Surface:

- **10 tools** — `get_latest_snapshot`, `list_snapshots`, `get_snapshot_by_timestamp`,
  `get_node_details`, `search_nodes`, `get_chart_data`, `get_ip_groups`,
  `get_ip_group_detail`, `get_rankings`, `parse_node_id_str`.
- **2 resources** — `bitcoin://snapshot/latest`, `bitcoin://snapshot/{timestamp}`.
- **3 prompts** — `analyze-network-health`, `compare-snapshots`,
  `network-distribution-summary`.

Two transports:

- **stdio** — for local Claude Desktop / local `claude mcp add`. No auth
  (process-level trust).
- **Streamable HTTP** — `127.0.0.1:8001` behind nginx + CloudFront at
  `https://pesquisa.hacknodes.xyz/mcp/`. Bearer-token authenticated.

### Connect from Claude Code (HTTPS, recommended)

Get the token off the host (only root and the service user can read it):

```bash
ssh ubuntu@<vm-lan-ip> 'sudo cat /etc/alt-bitnodes/mcp-token'
```

Register the remote server:

```bash
claude mcp add --transport http pesquisa-btc \
  https://pesquisa.hacknodes.xyz/mcp/ \
  --header "Authorization: Bearer <token>"
```

Inside Claude Code, `/mcp` lists the registered server and its tools.

### Connect from Claude Desktop (local stdio)

For a local checkout (no auth, runs `python -m alt_bitnodes_mcp --stdio`):

```json
{
  "mcpServers": {
    "pesquisa-btc": {
      "command": "/path/to/alt-bitnodes/venv/bin/python",
      "args": ["-m", "alt_bitnodes_mcp", "--stdio"],
      "cwd": "/path/to/alt-bitnodes",
      "env": {
        "BITNODES_EXPORT_DIR": "/path/to/bitnodes/data/export/f9beb4d9"
      }
    }
  }
}
```

Drop that into Claude Desktop's `mcpServers` config (Settings → Developer
→ Edit Config). Restart the app and the tools/resources/prompts appear.

For the HTTPS server (any MCP-capable client), use the same URL and
bearer pattern as the Claude Code example above; the JSON shape varies
per client.

### Rotating the bearer token

```bash
ssh ubuntu@<vm-lan-ip> '
  sudo rm /etc/alt-bitnodes/mcp-token
  sudo bash ~/alt-bitnodes/deploy/install.sh   # regenerates + restarts the service
'
```

Then re-distribute the new token to every client. `install.sh` is
idempotent — if the file already exists it is left alone, so the only
way to rotate is to delete it first.

### Caveats

- **Read-only.** No tool mutates Redis, no tool triggers a crawl.
- **SSE timeout at 1 h.** nginx caps individual HTTP sessions at one
  hour. Long-running MCP sessions reconnect automatically; if a client
  doesn't, restart the session.
- **One shared token.** Single-tenant by design. If you need per-client
  identity, the MCP SDK supports OAuth — pending follow-up.

## Cost notes

Home hosting: the VM runs on hardware that was already on; the marginal
cost is electricity. Cloudflare's free plan covers DNS, the tunnel and
Access. The AWS bill for the same service was ~$200/month of compute plus
up to ~$660/month of data transfer once the Tor/I2P overlays were scaled
(see the 2026-08-01 postmortem). What remains in AWS for this project is
two EBS snapshots (~46 GB, a few dollars a month).
