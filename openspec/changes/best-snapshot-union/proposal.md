# BEST UNION view and a pinned best photo

## Why

Since 2026-09-19 the crawler runs the `clearnet` profile (the home router
cannot take the full ~40k-session load), so every live and rolling view
shows Tor and I2P at 0. The archive still holds the era when they were
measured: the 2026-07-26 photo has 23,507 nodes, 11,450 of them onion and
4,758 I2P. ifuensan asked (2026-10-16) for a third button that shows that
accumulated picture — a union of every snapshot up to 2026-07-26 — and for
the best photo to be guaranteed never to be deleted. Cosmetic: the crawler
profile is not touched.

Time-sensitive: raw exports are pruned after 90 days, so the 07-17…07-26
raw snapshots disappear within days; the union must be built before then.

## What Changes

- New frozen union: `best_union.py <date>` builds, once, the union of every
  raw snapshot and every archived photo with timestamp up to the end of that
  UTC day, and writes `data/best-union-{stats,nodes}.json`. It refuses to
  overwrite without `--force`; no timer touches it.
- `GET /api/best/stats` and `GET /api/best` serve it in the same shape as
  `/api/window/{days}[/stats]` (404 until built).
- Fourth toggle button `BEST UNION` (view id `best`): same panels, lower KPI
  band "Unique up to <date>", notes "unique up to <date>", Last-seen column.
  Disabled with a title when the union has not been built on the host.
- The 2026-07-26 photo is pinned: `compute_keep` always keeps pinned
  timestamps, so the archiver's rotation can never remove it.

## Capabilities

### New Capabilities
- `best-union`: the frozen union and its endpoints.

### Modified Capabilities
- `dashboard-view-mode`: the BEST UNION view.
- `snapshot-archive`: pinned photos survive rotation.

## Impact

`queries/{best_union,archives,config,__init__}.py`, `best_union.py`, `app.py`,
`templates/index.html`, `static/app.{js,css}`, tests, README. A one-off
build on VM 114 (~1 min, reads ~450 raw snapshots + 4 photos).
