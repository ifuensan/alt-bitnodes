# Deploy alt-bitnodes

Single-node deployment that runs the bitnodes crawler stack and the
alt-bitnodes dashboard on one Ubuntu 24.04 LTS host. Production is a VM on
the home Proxmox host behind a Cloudflare Tunnel; the AWS EC2 procedure it
replaced is kept below under *Legacy: AWS EC2* until that instance is
terminated (see `openspec/changes/migrate-to-selfhosted-proxmox/`).

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
environment (the deploy runs it over SSH with none). Absent files mean the
legacy EC2 behaviour, so write both **before** the first run:

```bash
sudo install -d -m 0750 /etc/alt-bitnodes
echo cloudflare | sudo tee /etc/alt-bitnodes/edge
echo clearnet   | sudo tee /etc/alt-bitnodes/crawler-profile
```

| file | values | effect |
|---|---|---|
| `edge` | `cloudflare` \| `cloudfront` | nginx template (loopback + `CF-Connecting-IP` vs origin gate), cloudflared vs CloudWatch agent |
| `crawler-profile` | `clearnet` \| `full` | `onion`/`i2p` in both crawler confs; Tor pool + i2pd provisioned but stopped under `clearnet` |
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

First day: sample `ss -s` every minute and watch the household. If
established sessions trend past ~6.8k, lower `workers` in
`ping.f9beb4d9.conf` **in `install.sh`** (it is the snapshot ceiling and
the installer re-renders it) and re-run.

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

### Rollback during the transition

While the CloudFront stack still exists, cutover is reversible by pointing
the `pesquisa` CNAME back at `dxxxx.cloudfront.net` (DNS-only). After the
stack is deleted there is no AWS to go back to; the rollback is the VM's
vzdump plus the final EBS snapshot.

---

## Legacy: AWS EC2

Kept for the transition. Nothing below applies to the Proxmox host.

### 1. Create the EC2 instance

Recommended sizing: **c7g.2xlarge** (16 GB RAM, 8 vCPU, ARM Graviton3).
Pricing in us-east-1 ≈ $196/month on-demand.

For a smaller experiment or single-developer sandbox, **t4g.medium**
(4 GB / 2 vCPU burst, ~$24/month) works, but the crawler caps out
around ~1400 reachable nodes per snapshot on it due to handshake
CPU. See `deploy/TUNING.md` for the ceiling rationale.

### Via AWS Console

1. **AMI**: Ubuntu Server 24.04 LTS, **64-bit (Arm)**.
2. **Instance type**: `c7g.2xlarge` (or `t4g.medium` for the smaller
   profile).
3. **Key pair**: pick or create one. Save the `.pem` locally.
4. **Network settings → Security group**: create new with one rule:
   - SSH (port 22), source: **My IP**.
   - No other inbound rules. Public traffic enters via CloudFront —
     port 80 is opened separately by the edge CloudFormation stack
     and restricted to the CloudFront prefix list.
5. **Storage**: 1× EBS gp3, **16 GiB** (root). Default IOPS/throughput are fine.
6. **Advanced → User data**: leave empty (we run the installer manually).
7. Launch and associate an Elastic IP so the public DNS records can
   point at a stable address (the CloudFormation edge stack expects
   `origin.<your-domain>` to A-record to it).

### Via AWS CLI (alternative)

```bash
aws ec2 run-instances \
  --region us-east-1 \
  --image-id $(aws ec2 describe-images --region us-east-1 \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text) \
  --instance-type c7g.2xlarge \
  --key-name YOUR_KEY \
  --security-group-ids sg-XXXXXXXX \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=16,VolumeType=gp3}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=alt-bitnodes}]'
```

Note the public DNS / IP that AWS returns.

### 2. Run the installer

```bash
ssh -i ~/.ssh/your-key.pem ubuntu@<EC2_PUBLIC_DNS>

# On the instance:
curl -fsSLO https://raw.githubusercontent.com/ifuensan/alt-bitnodes/main/deploy/install.sh
sudo BITNODES_USER_AGENT="/your-tag:0.1/" bash install.sh
```

The installer:

- Installs apt deps + redis-server.
- Builds Python 3.12.4 with pyenv.
- Clones `ifuensan/bitnodes` (branch `fix/empty-include-asns`) → `~/bitnodes`.
- Clones `ifuensan/alt-bitnodes` → `~/alt-bitnodes`.
- Creates venvs, installs requirements.
- Generates `conf/*.f9beb4d9.conf` with your `user_agent`.
- Drops two systemd units (`bitnodes`, `alt-bitnodes`) and enables them.

Build of CPython takes ~3-5 min on t4g.medium.

### 3. Verify

```bash
systemctl status bitnodes alt-bitnodes
journalctl -u bitnodes -f          # crawler stdout
tail -f ~/bitnodes/log/crawl.f9beb4d9.log
redis-cli scard up                  # reachable nodes (grows over ~10 min)
ls ~/bitnodes/data/export/f9beb4d9/ # JSON snapshots
```

The first complete export appears after `snapshot_delay = 600s`.

### 4. Open the dashboard

Dashboard listens on `127.0.0.1:8000` only. Open via SSH tunnel:

```bash
ssh -i ~/.ssh/your-key.pem -N -L 8000:127.0.0.1:8000 ubuntu@<EC2_PUBLIC_DNS>
```

Then http://localhost:8000 in your browser.

### 5. Updates

```bash
ssh ubuntu@<host>
sudo bash ~/alt-bitnodes/deploy/install.sh   # idempotent: pulls both repos, restarts services
```

### 6. Stop / start

```bash
sudo systemctl stop  bitnodes alt-bitnodes
sudo systemctl start bitnodes alt-bitnodes
```

### MaxMind GeoLite2 refresh

The crawler resolves country, ASN, and city for each peer via MaxMind GeoLite2 databases under `~/bitnodes/geoip/`. The repo ships a recent snapshot of the three `.mmdb` files, but they go stale (MaxMind republishes Tue/Fri). A weekly `geoip-update.timer` is installed; it only runs if a license key is present.

```bash
# 1. Get a free license: https://www.maxmind.com/en/accounts/current/license-key
# 2. Drop it into the crawler's geoip dir, mode 600
echo 'YOUR_KEY' | sudo -u ubuntu tee ~/bitnodes/geoip/.maxmind_license_key
sudo chmod 600 ~/bitnodes/geoip/.maxmind_license_key

# 3. Re-run the installer; it enables the timer
sudo bash ~/alt-bitnodes/deploy/install.sh

# 4. Verify
systemctl list-timers geoip-update.timer
sudo systemctl start geoip-update.service   # one-off run to validate the key
ls -la ~/bitnodes/geoip/*.mmdb              # mtime should refresh
```

The timer runs every Wednesday at 06:00 with up to 30 min jitter. `Persistent=true` reruns missed cycles when the box was off. To check the last run: `journalctl -u geoip-update.service`.

### API smoke test

After deploy, hit a few endpoints:

```bash
curl -s http://localhost:8000/api/v1/rankings/countries/ | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/rankings/asns/      | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/rankings/user-agents/ | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/groups/by-ip/        | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/snapshots/latest/    | jq '.total_nodes'
```

### Public edge (CloudFront + nginx)

Until now the dashboard lives on `127.0.0.1:8000` and is reachable only via SSH
tunnel. To expose it publicly the path is **CloudFront → EC2:80 (nginx) →
uvicorn:8000**: TLS lives on CloudFront, the EC2 only accepts traffic from
CloudFront IPs that carry the right secret header.

#### Prerequisites

- AWS CLI configured with permissions for `acm:*`, `cloudfront:*`,
  `ec2:AuthorizeSecurityGroupIngress`, `ec2:RevokeSecurityGroupIngress`,
  `cloudformation:*`. A local profile pointing at `us-east-1` works fine.
- The EC2 instance already exists, its public IP is known, and its security
  group ID is known (`aws ec2 describe-instances --instance-ids <id>`).
- Access to the external DNS provider for `hacknodes.xyz` (Namecheap/GoDaddy
  /etc.) so you can create CNAME and A records by hand.

#### One-time bootstrap

```bash
# 1. Generate the shared origin-auth secret locally.
openssl rand -hex 32 > /tmp/origin-secret

# 2. Deploy the CloudFormation stack. Stays CREATE_IN_PROGRESS until ACM
#    validation CNAMEs are created — that's expected.
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name alt-bitnodes-edge \
  --template-file deploy/cloudformation/edge.yaml \
  --parameter-overrides \
      DomainName=pesquisa.hacknodes.xyz \
      OriginHostname=origin.hacknodes.xyz \
      OriginAuthSecret=$(cat /tmp/origin-secret) \
      OriginEc2SecurityGroupId=<sg-xxxxxxxx> \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Grab the ACM validation CNAMEs (Name/Value pairs) and create them
#    in the external DNS provider; the stack will finish once ACM sees them.
aws acm describe-certificate --region us-east-1 \
  --certificate-arn $(aws cloudformation describe-stacks --region us-east-1 \
      --stack-name alt-bitnodes-edge \
      --query 'Stacks[0].Outputs[?OutputKey==`AcmCertificateArn`].OutputValue' \
      --output text) \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord'

# 4. Wait for CREATE_COMPLETE, then read the CloudFront hostname.
aws cloudformation describe-stacks --region us-east-1 \
  --stack-name alt-bitnodes-edge \
  --query 'Stacks[0].Outputs'
```

#### DNS records to create in the external provider

| Type  | Name (host)                          | Value                              | Purpose                       |
|-------|--------------------------------------|------------------------------------|-------------------------------|
| CNAME | `<random>._<random>.hacknodes.xyz`   | `<random>.acm-validations.aws.`    | ACM domain validation         |
| A     | `origin.hacknodes.xyz`               | EC2 public IP (`100.50.100.201`)   | CloudFront origin lookup      |
| CNAME | `pesquisa.hacknodes.xyz`             | `dxxxx.cloudfront.net`             | Public hostname → CloudFront  |

The ACM CNAME comes from step 3 above. The CloudFront hostname comes from the
stack output `CloudFrontDomain`.

#### Push the secret to the EC2

```bash
SECRET=$(cat /tmp/origin-secret)
ssh -i $PEM_HNL ubuntu@<ec2-ip> "sudo install -d -m 0750 /etc/alt-bitnodes && \
  echo 'ORIGIN_AUTH_SECRET=${SECRET}' | sudo tee /etc/alt-bitnodes/origin-auth.env >/dev/null && \
  sudo chmod 0600 /etc/alt-bitnodes/origin-auth.env"
```

Then push to `main` (or trigger the deploy workflow) so `install.sh` runs and
configures nginx with the secret already in place. If you skip this step
`install.sh` will generate its own secret on first boot — fine for a brand-new
instance, but you'd then need to read it back and update the CloudFormation
parameter to match.

#### Smoke tests after deploy

```bash
SECRET=$(cat /tmp/origin-secret)

# Public hostname over HTTPS — 200 from CloudFront.
curl -fsSI https://pesquisa.hacknodes.xyz/

# Direct hit to the origin without the secret — 403 from nginx.
curl -sI http://<ec2-ip>/

# Direct hit with the secret — 200 (CloudFront does the same internally).
curl -sI -H "X-Origin-Auth: ${SECRET}" http://<ec2-ip>/

# Static asset served from edge cache.
curl -sI https://pesquisa.hacknodes.xyz/static/<some-asset>  # X-Cache: Hit from cloudfront

# Rate limit on the API path.
for i in $(seq 1 100); do
  curl -so /dev/null -w '%{http_code}\n' https://pesquisa.hacknodes.xyz/api/<endpoint>
done | sort | uniq -c
```

Once everything verifies, `rm /tmp/origin-secret`.

#### Rotating the OriginAuthSecret

1. Generate a new secret locally: `NEW=$(openssl rand -hex 32)`.
2. Update the CloudFormation stack (CloudFront swaps the header value):
   ```bash
   aws cloudformation deploy --region us-east-1 \
     --stack-name alt-bitnodes-edge \
     --template-file deploy/cloudformation/edge.yaml \
     --parameter-overrides OriginAuthSecret=${NEW} \
     --capabilities CAPABILITY_NAMED_IAM
   ```
3. Update the EC2: `echo "ORIGIN_AUTH_SECRET=${NEW}" | sudo tee /etc/alt-bitnodes/origin-auth.env`,
   then re-run `sudo bash /home/ubuntu/alt-bitnodes/deploy/install.sh` (re-renders
   the nginx config with the new secret and reloads). Brief 403s are possible
   while CloudFront propagates the new header.

#### Rollback

```bash
# Public layer
aws cloudformation delete-stack --region us-east-1 --stack-name alt-bitnodes-edge

# On the EC2
sudo systemctl disable --now nginx
sudo apt purge -y nginx
sudo rm -rf /etc/alt-bitnodes /etc/nginx/sites-enabled/alt-bitnodes \
            /etc/nginx/sites-available/alt-bitnodes /etc/nginx/conf.d/alt-bitnodes-limits.conf
```

DNS records can be left in place (pointing at a deleted distribution does no
harm) or removed from the external provider.

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

Get the token off the EC2 (only root and the service user can read it):

```bash
ssh -i $PEM_HNL ubuntu@<host> 'sudo cat /etc/alt-bitnodes/mcp-token'
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
ssh -i $PEM_HNL ubuntu@<host> '
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

Current production sizing (c7g.2xlarge in us-east-1):

- c7g.2xlarge 24/7: ~$196/month.
- EBS gp3 16 GiB: ~$1.30/month.
- Elastic IP (associated): free.
- CloudFront + ACM: free tier (1 TB egress + 10M requests/mo) covers
  current traffic; ACM certificate is free.
- Egress from EC2 to CloudFront: covered under "to CloudFront" free
  tier; user-facing egress is metered on CloudFront's side.
- **Total: ~$197–200/month** at current traffic.

Smaller alternative (t4g.medium) costs ~$24/month for the instance —
viable if you accept a snapshot ceiling around 1400 reachable nodes
(see `deploy/TUNING.md`).

Stop the instance when not needed (`aws ec2 stop-instances`) — you only
pay EBS while stopped (~$1.30/month). With an Elastic IP associated,
the public IP persists across stops.
