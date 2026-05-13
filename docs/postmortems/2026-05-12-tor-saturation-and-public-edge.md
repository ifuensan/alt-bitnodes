# 2026-05-12 — Tor saturation, crawler tuning, public edge

## Summary

A single-day operations session that fixed three intertwined issues on the
production EC2 (t4g.medium, us-east-1):

1. **Tor was pinned at 100% CPU**, dropping ~1M circuit requests per
   10 min. Root cause: upstream `bitnodes` defaults (crawl `workers=700`,
   ping `workers=2000`, `onion_peers_sampling_rate=100`) overwhelm a
   single-threaded Tor on a 2-vCPU host.
2. **Snapshots oscillated wildly** (55 → 1384 → 95 → …) and exported far
   fewer nodes than the crawler had reachable. Root cause: tuning step (1)
   left the crawl sweep unable to finish within the export window.
3. **No public exposure**: the dashboard listened on `127.0.0.1:8000` and
   was only reachable via SSH tunnel. We put it behind CloudFront with TLS,
   origin auth and a CloudFront-restricted security group.

Also surfaced and fixed: **CI deploy ran the on-disk `install.sh` _before_
`git pull` refreshed it**, so any config change introduced in the same
commit was silently reverted by the stale installer. Confirmed twice
before we wrote the fix.

## Impact

- Before: load averages of 9–10 on a 2-vCPU box (saturation); snapshot
  counts oscillating 55–1400 with rare spikes to ~5000; dashboard not
  reachable from the public internet.
- After: load 2–3 sustained; snapshot counts stable around ~1390;
  dashboard live at `https://pesquisa.hacknodes.xyz` with TLS and edge
  cache.

No data loss. The crawler kept running throughout (the existing snapshots
on disk remained intact); we only restarted the systemd units.

## Timeline (UTC)

All times approximate; the host clock and our timestamps agree within
seconds.

| Time | Event |
|------|-------|
| 09:00 | User shares `htop`: load 9.93, both vCPUs at 100%, Tor at 99.7% CPU for 10h36m. |
| 09:15 | Diagnose: `journalctl -u tor@default` shows _"32 client circuits pending. [1,063,310 similar messages suppressed in last 660 seconds]"_. Tor is the bottleneck. |
| 09:30 | First mitigation: reduce slaves in `deploy/run-bitnodes.sh` (4→2 crawl, 15→6 ping). Load drops 9.93 → 2.74 in <2 min; Tor still ~91%. |
| 10:00 | Second mitigation: in upstream `*.conf`, drop `workers` (crawl 700→200, ping 2000→200), `socket_timeout` 60→30, `onion_peers_sampling_rate` 100→25. Tor's "suppressed" rate drops from ~1.06M / 10 min to ~260k. Load steady at ~2.7. |
| 10:45 | Persist tuning in `deploy/install.sh`. CI deploy runs successfully — confirmed by `gh run list`. |
| 12:30 | User decides to expose publicly behind CloudFront. New change `expose-dashboard-via-cloudfront` proposed via `/opsx:propose`. |
| 13:00 | Implement nginx reverse proxy with `X-Origin-Auth` gate, rate limiting (`limit_req` 20 r/s burst 40), security headers. CloudFormation template (`deploy/cloudformation/edge.yaml`) for ACM cert + CloudFront distribution + SG ingress restricted to CloudFront prefix list. |
| 13:30 | Apply via CI. First `aws cloudformation deploy` fails: empty `DomainValidationOptions.HostedZoneId`. Drop the block (ACM emits CNAMEs on its own); redeploy succeeds. |
| 14:00 | DNS records created at Namecheap: ACM validation CNAME, `pesquisa` CNAME to CloudFront, `origin` A to EC2 EIP. Stack reaches CREATE_COMPLETE after ACM validates. |
| 14:15 | Smoke test from laptop: `GET https://pesquisa.hacknodes.xyz/` returns 200; direct hit to `http://<ec2-ip>/` times out (SG drops it); rate-limit fires at ~140/500 successful requests. |
| 17:30 | User notices snapshots dropped from historical ~7000 to 169. Investigate. |
| 18:00 | Discover the crawler log shows `81907/5484` known/reachable but export wrote 169. `open:*` in Redis matches export count: snapshots capture _simultaneously open sockets_, not total reachable. With `workers=200` and `snapshot_delay=600s`, a sweep of 63k known nodes can't complete in the export window. |
| 18:25 | Bump `workers` 200→300 and `snapshot_delay` 600→900. Snapshots stabilise at ~1380. |
| 21:51 | User pushes for more. Bump `workers` 300→500 directly via SSH. CI auto-deploys, and **reverts the change** — same `install.sh`-runs-before-`git pull` bug as before. Re-apply manually. |
| 22:10 | Root-cause the CI bug: `deploy.yml` ran `sudo bash ~/alt-bitnodes/deploy/install.sh`, but the on-disk copy of the script is the one from the _previous_ run. `install.sh` does git-pull the dashboard repo internally, but the running script is already in memory by then. Fix: `git fetch && git reset --hard origin/main` _before_ invoking `install.sh`. Pushed; next deploy preserves the new config. |
| 22:30 | Snapshots stable at ~1390 with `workers=500`. Almost no gain over `workers=300`. Investigation: 5446 TCP sockets established system-wide, but only 1387 counted as `open:*`. ~4000 are TCP connections that never complete the Bitcoin handshake. The bottleneck is **handshake completion rate**, not workers, not Tor, not file descriptors, not conntrack. |
| 22:45 | User reveals previous environment was a 14-core local machine; the t4g.medium has 2 vCPUs. Confirms the ceiling is CPU-bound handshake processing, not configuration. |
| 04:41 (May 13) | Final try: `socket_timeout` 30→60 to give slow peers more time to complete the handshake. Pushed via CI; this time the `git pull` fix carries it through correctly on first deploy. |
| 06:55 | Final state: load ~2, Tor ~95% (steady), snapshots ~1390 stable, public dashboard live, billing alarm armed at 5 USD/month. |

## What we tried, and what worked

### Slave reduction (deploy/run-bitnodes.sh)
- 4→2 crawl slaves, 15→6 ping slaves.
- **Worked.** Load 9.93 → 2.74 immediately. This was the biggest single win
  because it removed Python-side contention; Tor was still saturated but
  the host stopped thrashing.

### Worker / timeout tuning (conf files)
- `crawl.workers` 700 → 200 → 300 → 500.
- `ping.workers` 2000 → 200.
- `socket_timeout` 60 → 30 → 60.
- `onion_peers_sampling_rate` 100 → 25.
- `snapshot_delay` 600 → 900.
- **Partially worked.** Each change moved a needle but the snapshot count
  ceiling stayed near 1400 once we got past `workers=300`. The
  scaling becomes non-linear because handshake completion (CPU-bound) caps
  out before workers do.

### CloudFront edge
- nginx reverse proxy with `X-Origin-Auth` header check.
- `set_real_ip_from` for the CloudFront edge ranges so rate limit and
  access logs see real client IPs.
- SG ingress only from `pl-3b927c52` (CloudFront origin-facing prefix
  list).
- ACM with DNS validation (CNAMEs created manually at Namecheap).
- **Worked first try after the `DomainValidationOptions` fix.** All
  six requirements from `specs/public-edge/spec.md` verified.

### CI fix
- Workflow now does `git fetch && git reset --hard origin/main` before
  invoking `install.sh`, instead of relying on `install.sh`'s own
  late-stage `git pull`.
- **Worked.** Confirmed on the very next push: change in `install.sh`
  applied on first run, no revert.

## What didn't work, and why

- **Removing Tor or onion crawling entirely** — proposed but not done.
  After tuning, onion is only ~3% of `open:*` (44 of 1387). It's not the
  bottleneck for the snapshot count.
- **Hoping `workers` would scale linearly** — wrong. Above ~300 workers,
  the handshake completion rate caps out because the t4g.medium has only
  2 vCPUs and each handshake is a few rounds of cryptography + parsing.
  More workers just creates more TCP connections in handshake purgatory.

## Lessons

1. **Look at the real bottleneck, not the configured one.** "Tor at 100%
   CPU" is what we saw first, but the actual snapshot ceiling was CPU on
   the host (handshake processing), not Tor. We could only see this after
   confirming `open:*` ≈ snapshot count, and `TCP established` ≫ `open:*`.
2. **CI scripts that update themselves are dangerous.** A deploy script
   that does its own `git pull` halfway through has a chicken-and-egg
   problem: the on-disk copy at start time is one revision behind. Fixed
   by pulling _before_ exec, in the calling workflow.
3. **Tor is single-threaded.** Upstream `bitnodes` defaults assume hardware
   with many cores and dedicated network. On small AWS instances those
   defaults DDoS your own Tor.
4. **`limit_req_zone` needs `set_real_ip_from`.** Without it the limit
   applies per CloudFront edge IP and never fires.
5. **ACM `DomainValidationOptions` is finicky.** For DNS validation with
   an external DNS provider, leave the block out entirely; ACM emits the
   validation CNAMEs in the certificate's `DomainValidationOptions` field
   for you to read.

## Follow-ups

- Resize to `c6g.2xlarge` (8 vCPU, ~$96/mo) if snapshot counts of 5k+
  matter. Handshake processing scales near-linearly with vCPU count up to
  a few thousand concurrent.
- Consider stopping Tor entirely if onion visibility (~3% of nodes) isn't
  worth the steady 95% CPU it consumes.
- Wire the upstream `bitnodes` block-height endpoint to a real source —
  currently it tries `bitnodes.io` (offline), logs a warning, and exports
  `"latest_height": 0` in every snapshot. Cosmetic but ugly.
- Add CloudFront access logs to an S3 bucket if abuse investigation ever
  matters; today only nginx `access.log` is local.

## Final config (snapshot of this day's outcome)

| Setting | Value | Rationale |
|---------|-------|-----------|
| `deploy/run-bitnodes.sh` crawl slaves | 2 | Was 4. |
| `deploy/run-bitnodes.sh` ping slaves | 6 | Was 15. |
| `crawl.conf workers` | 500 | Was 700 (upstream) → 200 → 300 → 500. |
| `ping.conf workers` | 200 | Was 2000 (upstream). |
| `crawl.conf socket_timeout` | 60 | Was 60 → 30 → 60. |
| `ping.conf socket_timeout` | 60 | Was 60 → 30 → 60. |
| `crawl.conf onion_peers_sampling_rate` | 25 | Was 100. |
| `crawl.conf snapshot_delay` | 900 | Was 600. |
| nginx | reverse proxy with header gate + rate limit | New. |
| CloudFront distribution | ACM cert, prefix-list-restricted SG | New. |
| Billing alarm | $5/mo via SNS | New. |
| Deploy workflow | `git pull` before `install.sh` | Fixed. |
