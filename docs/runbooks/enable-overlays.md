# Runbook — enable the Tor/I2P overlays on the Proxmox VM

The crawler runs the `clearnet` profile since the 2026-09-20 migration:
IPv4/IPv6 only, Tor pool and i2pd installed but stopped. This is how the
`full` profile comes back and what has to be true first.

## Prerequisites (do not skip)

1. **The Digi router is out of the path**: ONT in bridge mode, own router
   (OPNsense VM on frodo or equivalent) doing NAT with a conntrack table of
   at least 100k entries and no per-host session or SYN-rate limits.
   Behind the stock Zyxel the household degrades between 7k and 10k held
   sessions, and the crawler host alone is throttled on IPv4 (see
   `docs/follow-ups.md`, "The Digi router caps the crawler host's IPv4
   sessions").
2. **Re-test at the full profile's scale** before flipping: ~40k concurrent
   sessions and ~1k new connections/min from the VM's IP, with another LAN
   host checking that its own connectivity stays intact.
3. `df -h /data` has room: onion + I2P snapshots are ~3x the clearnet ones.

## Procedure

```bash
ssh ubuntu@192.168.1.165
echo full | sudo tee /etc/alt-bitnodes/crawler-profile
sudo bash ~/alt-bitnodes/deploy/install.sh
```

The installer renders `onion = True` / `i2p = True` into both crawler
confs, restores crawl `workers = 1200`, `socket_timeout = 60` and the 5-day
`max_age`, enables and starts `tor.service`, `tor@default`,
`tor@bitnodes1..8` and `i2pd`, and restarts `bitnodes.service` once because
its fingerprint changed. Parked units stay parked; check
`/etc/alt-bitnodes/parked-units` is empty first.

## What to expect

- Onion takes ~13 h to reach its plateau (~10.8k on the EC2 with
  `UseEntryGuards 0`); I2P bootstraps from `conf/i2p_seeds.txt` and reached
  ~5k within a day.
- Egress rises to ~350 GB/day, >99% Tor/I2P overlay machinery. Fine on a
  home line; never again on metered cloud egress.
- The `MaxCircuitDirtiness` end state from the `onion-proxy-affinity`
  change applies at this point (task 4.2 there): the A/B showed 63% less
  handshake churn on the treated half; decide whether to keep 3600 on the
  whole pool now that egress is no longer billed.

## Verify

```bash
systemctl is-active tor@bitnodes1 i2pd bitnodes
grep -E '^(onion|i2p|workers) ' ~/bitnodes/conf/crawl.f9beb4d9.conf
tail -1 /var/log/alt-bitnodes/sessions.log      # if the sampler is still running
grep 'Reachable nodes' ~/bitnodes/log/crawl.f9beb4d9.log | tail -1
```

## Back out

`echo clearnet | sudo tee /etc/alt-bitnodes/crawler-profile` and re-run the
installer: the daemons stop, the confs flip back, the crawler restarts once.
