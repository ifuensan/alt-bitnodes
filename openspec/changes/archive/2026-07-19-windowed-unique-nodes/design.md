# Design — windowed-unique-nodes

## Context

Snapshots (30-min JSONs in `EXPORT_DIR`, 15-field rows, `r[0]`=address) are
pruned at 90 days. A one-off host script already proved the concept: the
union over ~3-8 days gives clearnet ~10.5k, tor ~11.3k, i2p ~5k, total ~27k.
The union is I/O+CPU heavy (hundreds of files, millions of rows, ~1 min), so
it can't run in the request path. The repo already has the archiver/timer
pattern and the crawler-fingerprint rule (dashboard-side units don't restart
the crawler).

## Goals / Non-Goals

**Goals:** a cached, cheap-to-serve windowed union metric; visible on the
dashboard next to the instantaneous count; a citable API figure.

**Non-Goals:** per-request computation; historical time-series of the
windowed number (future); matching bitnod.es's exact 8-day pruning semantics
(we approximate with a snapshot union over N days).

## Decisions

1. **Precompute via a timer, serve from cache.** `window_stats.py` (job)
   computes all windows in a single pass over the snapshots and writes
   `data/window-stats.json`; `GET /api/v1/stats/window` reads that file.
   Mirrors `export-prune`/archiver. Hourly + niced — the union changes
   slowly and this bounds the load.
2. **Single pass, multiple windows.** Read each snapshot once; add each
   node's `(address, port)` to every window-set whose cutoff it satisfies
   (widest window is the superset). Avoids re-reading files per window.
3. **Windows 1/3/8 days**, constants. 8d is the bitnod.es comparison; 1d is
   the honest current-config figure for tor/i2p (which only came online
   recently); 3d bridges.
4. **Pure compute in `queries/window_stats.py`** (testable with fixture
   snapshots) + a thin job entrypoint; listing/read helper also there for the
   API. Keeps pyarrow/heavy deps out — this is stdlib json + sets.
5. **Dashboard: a compact secondary figure**, not a full second KPI strip —
   show the 8-day unique total next to the instantaneous count (e.g. in the
   header meta or a small sub-line under the KPIs), to avoid clutter.

## Risks / Trade-offs

- [Recompute competes with the crawler for CPU] → niced, hourly, single
  pass; bounded at ~1-2 min even with 8 clean days (~384 files).
- [Cache staleness up to 1h] → acceptable; the windowed number moves slowly.
- [Our "8 days" is currently ~3 days of data due to past crawler gaps] →
  reported snapshot-count makes this transparent; grows as clean days
  accumulate.
- [Memory: holding unique sets for 8 days] → ~tens of thousands of tuples
  per network, a few MB; negligible on 16 GB.

## Migration Plan

One commit → CI deploy (crawler untouched) → timer installed, first run
writes the cache → verify endpoint + dashboard. Rollback: revert; the cache
file and idle timer are harmless.

## Open Questions

- Exact dashboard placement (header meta vs sub-line) — decide during
  implementation, keep it compact.
