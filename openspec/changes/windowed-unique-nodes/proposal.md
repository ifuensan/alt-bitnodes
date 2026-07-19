# Windowed unique-node counts (apples-to-apples with bitnod.es)

## Why

Our snapshots count nodes reachable *simultaneously* (~12k). Trackers like
bitnod.es count the *union of unique nodes seen over a rolling window* (8
days, ~22k) — a different metric of the same network. Measured the same way,
alt-bitnodes already matches them on clearnet, exceeds them on Tor, and adds
~5k I2P nodes nobody else tracks (union total ~27k vs their 22k). Surfacing a
windowed count makes the comparison legible on the dashboard and gives the
project a citable "instantaneous vs N-day" figure.

## What Changes

- A job computes the union of unique `(address, port)` per network type
  (clearnet=ipv4+ipv6, tor, i2p) over configurable windows (1/3/8 days) from
  the snapshots on disk, and caches the result to a small JSON.
- The union is expensive (reads hundreds of snapshot files, ~1 min), so it is
  precomputed by a systemd timer, not per request — the API just serves the
  cached JSON.
- New endpoint `GET /api/v1/stats/window` returns the cached windowed counts.
- The dashboard surfaces the windowed totals alongside the instantaneous
  snapshot (a compact "unique over N days" line/tiles).

## Capabilities

### New Capabilities
- `windowed-stats`: the rolling-window union metric — how it's computed
  (per-network unique union over N days), how it's cached (precomputed to
  disk by a timer), and how it's served (API + dashboard).

### Modified Capabilities

<!-- none -->

## Impact

- New: `queries/window_stats.py` (pure compute + cache read), `window_stats.py`
  job entrypoint, endpoint in `app.py`, dashboard element,
  `deploy/alt-bitnodes-window-stats.{service,timer}`.
- Disk: one small JSON (`data/window-stats.json`).
- Dashboard-side only; the deploy will not restart the crawler.
- Load: the timer's full-union recompute is niced and hourly; competes
  mildly with the crawler but is bounded (single pass over snapshots).
