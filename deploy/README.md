# Deploy alt-bitnodes on AWS EC2

Single-node deployment that runs the bitnodes crawler stack and the
alt-bitnodes dashboard on the same Ubuntu 24.04 LTS (ARM64) instance.

## 1. Create the EC2 instance

Recommended sizing: **t4g.medium** (4 GB RAM, 2 vCPU burst, ARM Graviton).
Pricing in eu-west-3 ≈ $24/month on-demand.

### Via AWS Console

1. **AMI**: Ubuntu Server 24.04 LTS, **64-bit (Arm)**.
2. **Instance type**: `t4g.medium`.
3. **Key pair**: pick or create one. Save the `.pem` locally.
4. **Network settings → Security group**: create new with one rule:
   - SSH (port 22), source: **My IP**.
   - No other inbound rules. The dashboard is only reached via SSH tunnel.
5. **Storage**: 1× EBS gp3, **16 GiB** (root). Default IOPS/throughput are fine.
6. **Advanced → User data**: leave empty (we run the installer manually).
7. Launch.

### Via AWS CLI (alternative)

```bash
aws ec2 run-instances \
  --region eu-west-3 \
  --image-id $(aws ec2 describe-images --region eu-west-3 \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-arm64-server-*" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' --output text) \
  --instance-type t4g.medium \
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

## Cost notes

- t4g.medium 24/7: ~$24/month.
- EBS gp3 16 GiB: ~$1.30/month.
- Egress: ~1 GB/month (well under free tier 100 GB).
- Total: **~$25/month**.

Stop the instance when not needed (`aws ec2 stop-instances`) — you only
pay EBS while stopped (~$1.30/month). Public IP changes on stop unless
you allocate an Elastic IP.
