# Tasks — conditional-crawler-restart

## 1. Implementation

- [x] 1.1 Add `crawler_fingerprint()` (sha256 over fork git rev, generated
      confs, run-bitnodes.sh, bitnodes.service unit) and capture it at the
      start of `main()`.
- [x] 1.2 Replace the unconditional `systemctl restart bitnodes ...` with the
      fingerprint/is-active comparison; keep dashboard + MCP restarts
      unconditional.
- [x] 1.3 `bash -n` and dry-run the fingerprint function logic locally.

## 2. Deploy and verify

- [ ] 2.1 Push; this deploy still restarts the crawler (the commit itself
      does not change crawler inputs, but the previous Tor tuning did — the
      real test is the next dashboard-only deploy).
- [ ] 2.2 On a later crawler-neutral deploy, confirm via logs/uptime that
      `bitnodes.service` was left running.

## 3. Bookkeeping

- [ ] 3.1 Archive change, sync spec.
