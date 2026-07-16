# Tasks — scale-onion-crawling-multi-tor

## 1. Installer: Tor pool provisioning

- [x] 1.1 Add `setup_tor_pool()` to `deploy/install.sh`: for instances
      `bitnodes1`..`bitnodes5`, run `tor-instance-create` if
      `/etc/tor/instances/<name>` doesn't exist, write torrc with
      `SocksPort 127.0.0.1:905N` (idempotent overwrite), and
      `systemctl enable --now tor@<name>`; call it from the main flow after
      `install_apt_packages`.
- [x] 1.2 Make the crawler-conf sed idempotent for multi-line values: delete
      stale `tor_proxies` continuation lines before rewriting the key with
      the six proxies (9050–9055) as indented continuations.
- [x] 1.3 Change the `onion_peers_sampling_rate` sed from 25 to 100.
- [x] 1.4 `bash -n deploy/install.sh` and dry-review the generated sed output
      against a local copy of `crawl.conf.default` (simulate two consecutive
      runs to prove idempotency).

## 2. Deploy and verify

- [ ] 2.1 Commit and push; confirm CI (test + deploy jobs) green.
- [ ] 2.2 Health check ~15 min after deploy: `tor@bitnodes1..5` active,
      SocksPorts 9051–9055 listening, load average sane, no circuit-drop
      floods in `journalctl -u 'tor@*'`.
- [ ] 2.3 Verify onion recovery ~2 h after deploy: onion count in the latest
      snapshot via `/api/v1/snapshots/latest/` clearly above the old ~12 and
      trending up; note load/Tor CPU for the record.
- [ ] 2.4 If saturation signs appear, execute the rollback (revert commit,
      CI redeploy) and document findings.

## 3. Bookkeeping

- [ ] 3.1 Update `docs/follow-ups.md`: mark the onion gap addressed; add
      follow-up candidates (ping worker retune, IPv6 enablement in VPC).
- [ ] 3.2 Archive the change and sync `openspec/specs/onion-crawling/`.
