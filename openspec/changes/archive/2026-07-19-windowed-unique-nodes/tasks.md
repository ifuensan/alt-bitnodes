# Tasks — windowed-unique-nodes

## 1. Compute + cache

- [x] 1.1 `queries/window_stats.py`: single-pass union over snapshots for
      windows [1,3,8] days → per-network unique counts (ipv4/ipv6/tor/i2p),
      clearnet + grand totals, snapshot count; plus a cache read helper
      (`load_window_stats`) and the cache path in `queries/config.py`.
- [x] 1.2 `window_stats.py` job entrypoint: compute + write
      `data/window-stats.json` atomically; `__main__` runnable.
- [x] 1.3 Tests: union dedupes across snapshots, network classification,
      window cutoffs, empty/missing-cache read.

## 2. API + dashboard

- [x] 2.1 `app.py`: `GET /api/v1/stats/window` serving the cached JSON
      (empty result if absent, never a synchronous recompute).
- [x] 2.2 Dashboard: show the 8-day unique total next to the instantaneous
      reachable-nodes count (compact); fetch `/api/v1/stats/window`.
- [x] 2.3 Endpoint test (cached present / absent).

## 3. Deploy

- [x] 3.1 `deploy/alt-bitnodes-window-stats.{service,timer}` (oneshot,
      hourly + jitter, niced, dashboard venv/user); wire into `install.sh`
      (crawler fingerprint untouched).
- [x] 3.2 Commit, push, CI green, "Crawler unchanged" in deploy log.
- [x] 3.3 Verify on production: first run writes the cache, endpoint returns
      the windowed counts, dashboard shows both figures.

## 4. Bookkeeping

- [x] 4.1 Archive change, sync `windowed-stats` spec.
