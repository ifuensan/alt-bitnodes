# 2026-08-01 — cost-anomaly "compromise" was the crawler; quarantine took prod down ~30 min

## Summary

AWS Cost Anomaly Detection flagged $216.87 of unexpected
DataTransfer-Out (2,307% over expected, 2026-07-18 → 07-31, us-east-1).
An incident-response session attributed the egress to the production
instance `i-09cc1c8a059eed000` (100.50.100.201), diagnosed it as
"compromised, used as a proxy/relay", and applied a quarantine security
group (`sg-06b0927da977a36c2`, no ingress, no egress) at 08:38 UTC —
taking pesquisa.hacknodes.xyz down (CloudFront 504) and locking out SSH.
A `stop-instances` was queued as the next step.

It was a **false positive**. The instance is the alt-bitnodes
production box; the egress is the crawler itself after the July
scale-up (4k → 22k reachable nodes). The original SG
(`sg-043f570db4c031003`) was restored at ~09:10 UTC; the site returned
200 on the first probe and the crawler survived the quarantine window
unharmed (next snapshot exported 09:14 UTC, 14.8k nodes).

## Impact

- Public dashboard/API down ~30 min (08:38 → ~09:10 UTC), CloudFront
  504. MCP unreachable for the same window.
- SSH locked out for the operator too — the quarantine SG had no
  ingress at all.
- No data loss: the crawler's ~40k established sockets survived
  (security groups are stateful; only *new* connections were blocked),
  which is also why the responder saw "traffic did not drop after
  isolation" and read it as further evidence of compromise.
- Had the queued `stop-instances` run, onion would have reset to 0 with
  an hours-long re-ramp (every crawler restart does — see the scaling
  notes).

## Root cause

A cost anomaly was triaged as a security incident without correlating
the traffic ramp against the operator's own change timeline. The
evidence read as compromise:

- ramp from ~5 GB/day (Jul 15) to a flat 330–350 GB/day from Jul 20,
  24/7, no diurnal pattern — "proxy/relay profile";
- traffic did not stop when the instance was isolated (stateful SG kept
  established flows alive).

But the ramp dates map 1:1 onto deliberate scaling work: Jul 17 (24k
socket budget), Jul 19 (I2P handshake fix + Tor pool of 9), Jul 23
(`UseEntryGuards 0`) — each visible as a step in Cost Explorer's daily
curve ($0.30 → $1.60 → $9–15 → $22/day).

**A scaled Tor+I2P crawler is behaviourally indistinguishable from a
compromised relay from the outside.** Only correlation with the change
log, or a per-process traffic breakdown from inside, can tell them
apart.

## Verification technique (worth remembering)

- Per-process egress attribution without extra tooling: two `ss -tinp`
  snapshots 60 s apart, delta of `bytes_sent` per socket keyed by
  local|peer|process, residual vs `/proc/net/dev` = churn of
  short-lived sockets. Loopback excluded (doesn't bill).
- Result: python (Bitcoin protocol) ~0.2 MB/min; tor ~110 MB/min
  (~1,000 fresh TLS connections/min — the `UseEntryGuards 0` price);
  i2pd ~137 MB/min, much of it SSU2/UDP invisible to `ss -t`.
- i2pd's router console (127.0.0.1:7070) confirmed **transit = 0** —
  the router carries no third-party traffic; it is all our own tunnel
  machinery (67% build success rate, leaseset lookups, NetDb).
- Bottom line: >99% of the 356 GB/day is overlay overhead, ~0.1% is
  Bitcoin protocol bytes.

## Lessons

1. **Correlate cost alarms with your own change timeline before
   containing.** The anomaly window started two days after a deliberate
   scale-up. A `git log` / journal check would have reclassified the
   incident in minutes.
2. **A quarantine SG with no ingress locks *you* out too.** Keep an SSH
   (or SSM) path in the quarantine SG — losing hands-on access during
   triage made the "is it malware?" question unanswerable from inside.
3. **Stateful SGs don't kill established flows.** "Traffic continued
   after isolation" is expected behaviour, not evidence of
   sophistication.
4. **Alert on the trend, not the anomaly.** 14 days passed before the
   anomaly fired. A plain billing alarm with a low threshold (or a
   NetworkOut CloudWatch alarm) would have surfaced the ramp on day 2 —
   and would have been read as "the scale-up costs money", not "we are
   hacked".
5. **Don't operate the CLI as root** (the responder did; so did we).
6. The egress cost itself is real and structural (~$660/month at AWS
   rates): decision taken 2026-08-01 to migrate production to
   self-hosted Proxmox. Compute is sunk (all-upfront Savings Plan until
   2026-11-10); transfer is the only marginal AWS cost, so the
   migration can be unhurried.

## Follow-ups

- Migrate production to Proxmox (see `docs/follow-ups.md`).
- Release the idle Elastic IPs on the stopped instances
  (34.206.227.120 / 3.219.165.64, ~$4/month).
- Billing alarm with a low threshold; optionally a NetworkOut alarm on
  the crawler host.
- Full write-up as stage 9 of `docs/delving-draft-stages.md`.
