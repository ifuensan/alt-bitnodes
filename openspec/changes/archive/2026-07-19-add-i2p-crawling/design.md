# Design — add-i2p-crawling

## Context

The SAM dial path lives in the crawler fork
(`feat/i2p-sam-crawl`, commit ee99baa): sam.py client (persistent session per
process, Bitcoin Core's HELLO → NAMING LOOKUP → STREAM CONNECT flow), config
keys with fallbacks, resolve.py guards. This change is the deployment half.
It follows the minimum-viable decision (same host, no VM split) taken over
the May research's full architecture.

## Goals / Non-Goals

**Goals:** i2pd + SAM on the existing c7g.2xlarge; crawler switched to the
I2P-capable branch with the feature on; deploy stays one push.

**Non-Goals:** VM split / `install.sh --role` (May research architecture) —
revisit if I2P load ever matters; upstream PR (after ≥1 week in production);
dashboard changes (I2P nodes flow through snapshots as-is, ASN tag "I2P").

## Decisions

1. **i2pd from the PurpleI2P PPA** — current versions, ARM64 builds, updates
   via `apt upgrade`. Chosen in the May research over repo.i2pd.xyz.
2. **Rely on i2pd's default SAM** (enabled, 127.0.0.1:7656) instead of
   editing `/etc/i2pd/i2pd.conf` — appending a duplicate `[sam]` section
   risks boot failure on duplicate keys, and the default is what we want.
   A bounded wait + warning verifies it; warn-only because I2P is
   best-effort and a broken SAM must not block clearnet/Tor deploys.
3. **`ensure_conf_key` set-or-append helper** for the crawler confs: the
   live `.f9beb4d9.conf` files were generated from the pre-I2P defaults
   (install.sh only copies `.conf.default` when the target is missing), so
   pure seds would silently no-op. Both conf files are single-section, so
   appending at EOF lands keys in the right section.
4. **Branch switch, not merge**: `feat/i2p-sam-crawl` was branched off the
   deployed `fix/empty-include-asns`, so switching `CRAWLER_BRANCH` is a
   fast-forward that keeps the previous fix.

## Risks / Trade-offs

- [i2pd bootstrap takes minutes on first start (reseed + tunnel build)] →
  first crawl cycles simply fail I2P dials; coverage appears gradually.
  No action needed.
- [SAM disabled in some i2pd package default] → the bounded wait surfaces it
  in the deploy log; fix would be a one-line i2pd.conf edit done manually.
- [I2P dials hold crawl workers longer (60s timeout)] → sampling is
  bounded by the small I2P peer population; monitor crawl throughput.

## Migration Plan

One commit → CI deploy → installer installs i2pd, appends conf keys,
switches branch, restarts the stack. Verify: 7656 listening, `.b32.i2p`
appearing in `journalctl`/snapshots within a few hours. Rollback: revert
commit (branch returns to `fix/empty-include-asns`, `i2p` keys revert to
False via `ensure_conf_key`).

## Open Questions

- None blocking.
