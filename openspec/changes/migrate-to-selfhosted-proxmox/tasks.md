## 0. Repo: host-agnostic installer (safe to merge while the EC2 lives)

- [x] 0.1 `install.sh`: read `/etc/alt-bitnodes/edge` (absent → `cloudfront`)
      and `/etc/alt-bitnodes/crawler-profile` (absent → `full`) into
      `EDGE_MODE` / `CRAWLER_PROFILE` next to `PARKED_UNITS_FILE`, with the
      same "intent lives in a file, not in the environment" comment.
- [x] 0.2 `apply_crawler_profile`: under `clearnet` render `onion = False`
      and `i2p = False` into both `*.f9beb4d9.conf` (via `ensure_conf_key`);
      under `full` render `True`/`True` as today. Make `setup_tor_pool` and
      `setup_i2pd` provision always but only `enable_unit --now` under
      `full`; under `clearnet` `systemctl disable --now` the pool, `tor@default`
      and `i2pd`.
- [x] 0.3 `setup_data_volume`: if `/data` is a mountpoint, create
      `bitnodes-data`, `bitnodes-log`, `alt-bitnodes-data`, `redis`, `attic`,
      add the four bind entries to `/etc/fstab` if absent, `mount -a`, and
      `chown` the user-owned ones. Otherwise log a warning. Runs after both
      clones (the bind targets `~/bitnodes/data|log` and `~/alt-bitnodes/data`
      must exist) and before any unit starts writing to them.
- [x] 0.4 `deploy/nginx/alt-bitnodes-tunnel.conf.template`: loopback listen,
      no `X-Origin-Auth`, `real_ip_header CF-Connecting-IP`, everything else
      byte-identical to the CloudFront template. `configure_nginx` picks the
      template by `EDGE_MODE`; `bootstrap_origin_secret` and
      `install_cloudwatch_agent` run only under `cloudfront`.
- [x] 0.5 `deploy/cloudflared/config.yml.template` (`__TUNNEL_ID__`,
      `__PUBLIC_HOST__`, `__SSH_HOST__`; ingress → `http://127.0.0.1:80`,
      `ssh://127.0.0.1:22`, catch-all 404) and `setup_cloudflared`: install
      from Cloudflare's apt repo, render `/etc/cloudflared/config.yml`,
      `cloudflared service install` once, `systemctl enable --now cloudflared`.
      Reads tunnel id and hostnames from `/etc/alt-bitnodes/cloudflared.env`
      (written at provisioning, task 2.5). Runs only under `cloudflare`.
- [x] 0.6 `deploy/README.md`: new top section "Deploy on a Proxmox VM"
      (VM spec, disks, marker files, Cloudflare setup, first install); the
      EC2 section stays until phase 6 under a "Legacy: AWS EC2" heading.
- [ ] 0.7 `.github/workflows/deploy.yml`: rename to "Deploy to production";
      install `cloudflared` on the runner; `ProxyCommand cloudflared access
      ssh --hostname $DEPLOY_HOST` with `CF_ACCESS_CLIENT_ID/SECRET` in the
      environment; `known_hosts` from `DEPLOY_HOST_KEY`; secrets renamed
      `DEPLOY_*`. Do **not** merge this task before 4.1 has the secrets in
      place — until then the workflow would fail on every push.
- [x] 0.8 `docs/follow-ups.md`: migration entry → "In progress, see
      `openspec/changes/migrate-to-selfhosted-proxmox`"; note that the
      `install.sh` data-volume gap is closed by 0.3.
- [ ] 0.9 Before merging, on the EC2: `grep /data /etc/fstab` and confirm
      the four binds are written as `/data/<x> <dst> ...` (the installer's
      duplicate check keys on `src dst`); confirm `parked-units` lists
      `bitnodes.service`, `i2pd.service`, `tor.service` and the `tor@*`
      units. Then merge 0.1–0.6 + 0.8 to `main`. The EC2 deploys them with
      both markers absent: nginx re-renders identically, the crawler confs
      are byte-identical (`onion`/`i2p` were already `True`), the parked
      crawler is untouched, CloudWatch still installs. Confirm with the
      smoke test and `systemctl is-active bitnodes` → inactive.

## 1. Proxmox VM

- [ ] 1.1 Create the VM from the Ubuntu 24.04 cloud image: 8 vCPU (host
      type), 16 GiB RAM, `scsi0` 20 GiB root, `scsi1` 80 GiB data, VirtIO
      NIC on the LAN bridge, static IP via cloud-init, SSH key for the
      operator, `qemu-guest-agent`, `serial0` console.
- [ ] 1.2 Inside: `apt update && apt full-upgrade`, `mkfs.ext4 -L data
      /dev/sdb`, `/etc/fstab` line `LABEL=data /data ext4 defaults,nofail 0 2`,
      `mount -a`. Time sync (`timedatectl`), `ufw default deny incoming`,
      `ufw allow from <LAN>/24 to any port 22`, `ufw enable`.
- [ ] 1.3 Kernel/limits for ~10k sockets: `fs.file-max`, `net.ipv4.ip_local_port_range
      = 10240 65000`, `net.core.somaxconn` in `/etc/sysctl.d/90-crawler.conf`.
      (`LimitNOFILE=65535` is already in the unit.)
- [ ] 1.4 Write the markers:
      `echo cloudflare | sudo tee /etc/alt-bitnodes/edge`,
      `echo clearnet | sudo tee /etc/alt-bitnodes/crawler-profile`
      (create `/etc/alt-bitnodes` 0750 root:root first).
- [ ] 1.5 Proxmox side: backup job for the VM (vzdump, weekly, root disk
      only — `/data` is reproducible from the archive and the EC2 snapshot),
      start-on-boot, and a note in the Proxmox host docs.

## 2. Cloudflare

- [ ] 2.1 Add `hacknodes.xyz` to a Cloudflare account; import/recreate every
      existing record (Namecheap export) **DNS-only**, including
      `pesquisa` CNAME → `dxxxx.cloudfront.net` and `origin` A → EC2 IP.
- [ ] 2.2 Change nameservers at Namecheap; wait for "Active"; verify
      `dig +short pesquisa.hacknodes.xyz @1.1.1.1` still resolves to
      CloudFront and the site still returns 200.
- [ ] 2.3 `cloudflared tunnel login` + `cloudflared tunnel create alt-bitnodes`
      on the VM; credentials JSON → `/etc/cloudflared/<id>.json` 0600.
- [ ] 2.4 Public hostnames on the tunnel: `pesquisa-next.hacknodes.xyz`
      (temporary, for validation) and `ssh.hacknodes.xyz`. Cache rule:
      bypass cache for `/api/*` and `/mcp/*`; leave `/static/*` on defaults.
- [ ] 2.5 Zero Trust → Access: application for `ssh.hacknodes.xyz`, policy
      "Service Auth" with a new service token; record client id/secret
      for 4.1. Write `/etc/alt-bitnodes/cloudflared.env` on the VM with
      `TUNNEL_ID`, `PUBLIC_HOST=pesquisa-next.hacknodes.xyz` (flipped in 5.2),
      `SSH_HOST=ssh.hacknodes.xyz`.
- [ ] 2.6 Access → Settings: SSE / WebSocket proxying on; confirm the 100 s
      idle-response behaviour against a long MCP tool call once 3.4 is up.

## 3. Data copy and first install

- [ ] 3.1 On the EC2: `redis-cli save`; note sizes of
      `/data/bitnodes-data/export/f9beb4d9`, `/data/alt-bitnodes-data`,
      `/data/redis/dump.rdb`.
- [ ] 3.2 From the VM (pull, EC2 is the one with a public IP):
      `rsync -aH --info=progress2 ubuntu@<ec2>:/data/bitnodes-data/export/ /data/bitnodes-data/export/`,
      same for `/data/alt-bitnodes-data/` (exclude `unique-nodes.json`),
      `dump.rdb` → `/data/redis/`, and `/etc/alt-bitnodes/{mcp-token,research-token}`
      + `~/bitnodes/geoip/.maxmind_license_key` via `scp`. Verify counts and
      a checksum sample.
- [ ] 3.3 `sudo bash deploy/install.sh` on the VM (curl the raw file from
      `main` first, as the README says). Expect: `/data` binds in place,
      Redis started on the copied RDB (stop Redis, chown `redis:redis`,
      start — before the installer enables it), nginx on loopback, tunnel up,
      `tor@*`/`i2pd` present but inactive, `bitnodes.service` active,
      `crawl.f9beb4d9.conf` showing `onion = False`, `i2p = False`.
- [ ] 3.4 Validate on `https://pesquisa-next.hacknodes.xyz` with
      `deploy/smoke-test-v2.sh` (adapt the host); `redis-cli scard up`
      climbing; first export within `snapshot_delay`; MCP with the copied
      bearer token.
- [ ] 3.5 First-day watch: `ss -s | grep estab` every minute into a file,
      household connectivity sanity checks at ~2h and ~8h. If established
      sessions trend above ~6.8k, lower ping `workers` in `install.sh` (it
      is the snapshot ceiling, so the change is a repo commit, not a hand
      edit) and re-run the installer.

## 4. Deploy pipeline

- [ ] 4.1 GitHub → environment `PRO`: add `DEPLOY_SSH_KEY` (new ed25519 key,
      public half in the VM user's `authorized_keys`), `DEPLOY_HOST`
      (`ssh.hacknodes.xyz`), `DEPLOY_USER`, `DEPLOY_HOST_KEY`
      (`ssh-keyscan` run from the LAN), `CF_ACCESS_CLIENT_ID`,
      `CF_ACCESS_CLIENT_SECRET`. Keep the `EC2_*` secrets until phase 6.
- [ ] 4.2 Merge 0.7; run `workflow_dispatch`; confirm test → deploy → smoke
      green against the VM and that a docs-only push still skips.
- [ ] 4.3 Remove the EC2 deploy key from the EC2's `authorized_keys` (the
      pipeline must have exactly one target).

## 5. Cutover

- [ ] 5.1 Preconditions: 3.4 green for ≥ 24 h, one archive tier written on
      the VM (`ls data/archive/`), window-stats advancing.
- [ ] 5.2 Cloudflare DNS: `pesquisa` CNAME → `<tunnel-id>.cfargotunnel.com`,
      proxied; add `pesquisa` as a public hostname on the tunnel (or rename
      `pesquisa-next`); `PUBLIC_HOST=pesquisa.hacknodes.xyz` in
      `cloudflared.env`; re-run the installer.
- [ ] 5.3 Smoke test on the real hostname; check the certificate is
      Cloudflare's; `curl -sI https://pesquisa.hacknodes.xyz/static/app.js`
      shows `cf-cache-status`. MCP client (`claude mcp list`) still works
      with the old token.
- [ ] 5.4 Remove `pesquisa-next`. Leave `origin.hacknodes.xyz` and the
      CloudFront stack alone for 72 h as rollback.
- [ ] 5.5 `docs/follow-ups.md`: record cutover date and the first
      household/session observations.

## 6. AWS teardown

- [ ] 6.1 After the 72 h: `aws cloudformation delete-stack --stack-name
      alt-bitnodes-edge`; delete the WAF web ACL and the CloudWatch
      dashboards/alarms; release the two idle EIPs (34.206.227.120,
      3.219.165.64); delete the `origin` DNS record.
- [ ] 6.2 Final EBS snapshot of the root and `/data` volumes (tagged
      `alt-bitnodes-final-<date>`); `stop-instances`.
- [ ] 6.3 Once the VM has run a full weekly archive cycle: terminate the
      instance, delete both volumes, release its EIP, delete the
      `EC2_*` secrets and the EC2 deploy key pair.
- [ ] 6.4 Repo: delete `deploy/cloudformation/`, `deploy/cloudwatch-agent.json`,
      `install_cloudwatch_agent`, `bootstrap_origin_secret`, the
      `cloudfront` branch of `configure_nginx` and the old nginx template;
      rename the tunnel template; drop the `edge` marker (installer assumes
      Cloudflare); README "Legacy: AWS EC2" section → one paragraph of
      history pointing at the archived change.
- [ ] 6.5 `deploy/README.md` cost notes → home hosting; `deploy/TUNING.md`
      header → VM sizing.

## 7. Hand-off to the overlays change (not done here)

- [ ] 7.1 Write `docs/runbooks/enable-overlays.md`: prerequisites (ONT
      bridge, OPNsense with conntrack ≥ 100k, NAT re-test at 40k sessions),
      then `echo full | sudo tee /etc/alt-bitnodes/crawler-profile` and
      `sudo bash deploy/install.sh`; expected ramp times (onion ~13 h, I2P
      needs seeds); the MaxCircuitDirtiness end-state decision from
      `onion-proxy-affinity` applies at that moment.
- [ ] 7.2 Sync specs and archive this change.
