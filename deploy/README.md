# Deploy alt-bitnodes on AWS EC2

Single-node deployment that runs the bitnodes crawler stack and the
alt-bitnodes dashboard on the same Ubuntu 24.04 LTS (ARM64) instance.

## 1. Create the EC2 instance

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

## 2. Run the installer

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

## 3. Verify

```bash
systemctl status bitnodes alt-bitnodes
journalctl -u bitnodes -f          # crawler stdout
tail -f ~/bitnodes/log/crawl.f9beb4d9.log
redis-cli scard up                  # reachable nodes (grows over ~10 min)
ls ~/bitnodes/data/export/f9beb4d9/ # JSON snapshots
```

The first complete export appears after `snapshot_delay = 600s`.

## 4. Open the dashboard

Dashboard listens on `127.0.0.1:8000` only. Open via SSH tunnel:

```bash
ssh -i ~/.ssh/your-key.pem -N -L 8000:127.0.0.1:8000 ubuntu@<EC2_PUBLIC_DNS>
```

Then http://localhost:8000 in your browser.

## 5. Updates

```bash
ssh ubuntu@<host>
sudo bash ~/alt-bitnodes/deploy/install.sh   # idempotent: pulls both repos, restarts services
```

## 6. Stop / start

```bash
sudo systemctl stop  bitnodes alt-bitnodes
sudo systemctl start bitnodes alt-bitnodes
```

## MaxMind GeoLite2 refresh

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

## RTT history & latency endpoints

The dashboard process maintains a SQLite file populated by an in-process ingest task that copies fresh `rtt:<addr>-<port>` entries out of Redis on a fixed cadence. RTT samples are produced upstream by `bitnodes/cache_inv.py`, which consumes rotating pcap files written by `tcpdump-pcap.service`.

The systemd graph is:

```
tcpdump-pcap.service  →  data/pcap/f9beb4d9/*.pcap  →  cache_inv (inside bitnodes.service)  →  Redis rtt:*  →  alt-bitnodes ingest  →  data/rtt.sqlite
```

`tcpdump-pcap.service` runs as root (needs CAP_NET_RAW), drops privileges to the install user via `tcpdump -Z`, auto-detects the default-route interface (do not use `-i any` — that produces LINUX_SLL2 link-layer that `dpkt.ethernet` cannot parse), and applies a Bitcoin-magic-bytes BPF filter so disk usage stays small.

Env vars on the dashboard service (all optional):

| Var | Default | Notes |
|-----|---------|-------|
| `RTT_DB_PATH` | `<DASHBOARD_DIR>/data/rtt.sqlite` (set in alt-bitnodes.service) | SQLite file location. Parent dir is created if missing. |
| `RTT_INGEST_INTERVAL_SECONDS` | `30` | Must be < upstream `rtt_ttl` (see `~/bitnodes/conf/ping.conf`) so samples don't expire before ingest. |
| `RTT_WINDOW_SECONDS` | `1800` | Window over which `latency_ms` is computed (median). |
| `RTT_RETENTION_DAYS` | `30` | Older samples are pruned daily. |
| `RTT_INGEST_ENABLED` | `true` | Set `false` on read-only replicas (only one process per DB file should write). |

### Smoke test

After deploy, wait one ingest interval (≥30s) and run:

```bash
curl -s http://localhost:8000/api/v1/leaderboard/?limit=5 | jq
curl -s http://localhost:8000/api/v1/rankings/countries/ | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/rankings/asns/      | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/rankings/user-agents/ | jq '.results[:5]'
curl -s http://localhost:8000/api/v1/groups/by-ip/        | jq '.results[:5]'
NODE=$(curl -s http://localhost:8000/api/v1/snapshots/latest/ | jq -r '.nodes | keys[0]' | sed 's/:/-/')
curl -s "http://localhost:8000/api/v1/nodes/$NODE/latency/?hours=24" | jq
sqlite3 "${RTT_DB_PATH:-$HOME/alt-bitnodes/data/rtt.sqlite}" \
  'SELECT count(*), datetime(min(ts),"unixepoch"), datetime(max(ts),"unixepoch") FROM rtt_samples'
```

If `leaderboard.results` stays empty for several minutes, walk the chain:

```bash
systemctl status tcpdump-pcap                         # producer healthy?
ls ~/bitnodes/data/pcap/f9beb4d9/                     # *.pcap appearing/being consumed
journalctl -u bitnodes -g cache_inv | tail            # 'pkt=N pong=M' — pong>0 means pcap parses OK
redis-cli --scan --pattern 'rtt:*' | wc -l            # >0 once cache_inv has produced samples
journalctl -u alt-bitnodes -g 'rtt ingest' | tail     # ingest is running
```

`pkt=0` from cache_inv means tcpdump is writing in a link-layer format dpkt cannot parse. Confirm the unit is using a real interface (not `any`); `tcpdump-pcap.service` auto-picks via `ip route get 1.1.1.1`, but you can override with `Environment=TCPDUMP_IFACE=ens5` in `systemctl edit tcpdump-pcap.service`.

### Rollback

```bash
sudo systemctl stop alt-bitnodes tcpdump-pcap
# either: keep the DB and disable writes
sudo systemctl edit alt-bitnodes  # add Environment=RTT_INGEST_ENABLED=false
# or: drop the DB entirely
rm ~/alt-bitnodes/data/rtt.sqlite
sudo systemctl start alt-bitnodes  # leave tcpdump-pcap stopped if you want zero capture
```

`latency_ms` reverts to `null` in v1 payloads; existing fields keep their shape.

## Public edge (CloudFront + nginx)

Until now the dashboard lives on `127.0.0.1:8000` and is reachable only via SSH
tunnel. To expose it publicly the path is **CloudFront → EC2:80 (nginx) →
uvicorn:8000**: TLS lives on CloudFront, the EC2 only accepts traffic from
CloudFront IPs that carry the right secret header.

### Prerequisites

- AWS CLI configured with permissions for `acm:*`, `cloudfront:*`,
  `ec2:AuthorizeSecurityGroupIngress`, `ec2:RevokeSecurityGroupIngress`,
  `cloudformation:*`. A local profile pointing at `us-east-1` works fine.
- The EC2 instance already exists, its public IP is known, and its security
  group ID is known (`aws ec2 describe-instances --instance-ids <id>`).
- Access to the external DNS provider for `hacknodes.xyz` (Namecheap/GoDaddy
  /etc.) so you can create CNAME and A records by hand.

### One-time bootstrap

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

### DNS records to create in the external provider

| Type  | Name (host)                          | Value                              | Purpose                       |
|-------|--------------------------------------|------------------------------------|-------------------------------|
| CNAME | `<random>._<random>.hacknodes.xyz`   | `<random>.acm-validations.aws.`    | ACM domain validation         |
| A     | `origin.hacknodes.xyz`               | EC2 public IP (`100.50.100.201`)   | CloudFront origin lookup      |
| CNAME | `pesquisa.hacknodes.xyz`             | `dxxxx.cloudfront.net`             | Public hostname → CloudFront  |

The ACM CNAME comes from step 3 above. The CloudFront hostname comes from the
stack output `CloudFrontDomain`.

### Push the secret to the EC2

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

### Smoke tests after deploy

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

### Rotating the OriginAuthSecret

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

### Rollback

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
