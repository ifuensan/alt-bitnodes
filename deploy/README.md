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

## Cost notes

- t4g.medium 24/7: ~$24/month.
- EBS gp3 16 GiB: ~$1.30/month.
- Egress: ~1 GB/month (well under free tier 100 GB).
- Total: **~$25/month**.

Stop the instance when not needed (`aws ec2 stop-instances`) — you only
pay EBS while stopped (~$1.30/month). Public IP changes on stop unless
you allocate an Elastic IP.
