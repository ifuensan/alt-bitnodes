# Tasks — add-i2p-crawling

## 1. Installer

- [x] 1.1 Add `setup_i2pd()` to `deploy/install.sh`: PPA purplei2p, apt
      install i2pd, enable service, bounded wait for 127.0.0.1:7656 with
      warn-only outcome; call after `setup_tor_pool`.
- [x] 1.2 Add `ensure_conf_key()` helper and use it to set `i2p = True`,
      `i2p_proxies = 127.0.0.1:7656`, `i2p_peers_sampling_rate = 100` in the
      crawl conf and `i2p = True` + proxies in the ping conf.
- [x] 1.3 Switch `CRAWLER_BRANCH` to `feat/i2p-sam-crawl`.
- [x] 1.4 `bash -n` + simulate `ensure_conf_key` twice on copies of the
      live-style confs (no i2p keys) to prove set-or-append convergence.

## 2. Deploy and verify

- [x] 2.1 Commit, push, CI green.
- [x] 2.2 Verify on host: i2pd active, 7656 listening, crawler on the new
      branch, no errors in crawl/ping logs.
- [x] 2.3 Within a few hours: first `.b32.i2p` nodes in snapshots.

## 3. Bookkeeping

- [x] 3.1 Update `docs/follow-ups.md` (I2P item → done; note upstream-PR
      follow-up after a week of soak).
- [x] 3.2 Archive change, sync `openspec/specs/i2p-crawling/`.
