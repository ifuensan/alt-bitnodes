# Dashboard union view (LIVE vs 8-DAY UNION)

## Why

The Overview renders one snapshot: the nodes reachable at that instant.
Since July the KPI matrix also prints the 8-day union totals next to it,
but only as four numbers — the globe, the three rankings and the node table
still describe the instantaneous set. For Tor that picture is misleading
(connections are transient, so the instantaneous onion count is a fraction
of the union), and for anyone comparing with bitnodes-style trackers the
union is the comparable figure. ifuensan asked (2026-10-15) for a way to
flip the whole page to the accumulated reading: "the same image as the
realtime one, but static".

## What Changes

- The hourly window job keeps, per node, the last row it was seen with, and
  emits for every window a `distribution` block in the exact shape of
  `snapshot_stats` (top countries / user agents / ASNs, ISO-3 choropleth
  data, median height, network split), plus a second cache file with the
  union's node list (row + `last_seen`) for the widest window.
- Two dashboard-facing endpoints mirror the live ones:
  `GET /api/window/{days}/stats` and `GET /api/window/{days}` (nodes).
  Both serve the caches only; a window not cached yet is a 404.
  `GET /api/v1/stats/window` gains the `distribution` block (additive).
- The Overview header gets a `LIVE | 8-DAY UNION` toggle. The union view
  re-renders the globe, rankings, side KPIs and node table (with a *Last
  seen* column) from the union payload; the "right now" band stays live,
  the snapshot picker hides, and each panel carries a "unique over 8 days"
  note. The choice persists in `localStorage['pesquisa:view']`; if the
  cache is absent the toggle disables itself and the page stays live.

## Capabilities

### New Capabilities
- `dashboard-view-mode`: the LIVE / UNION toggle and what each view shows.

### Modified Capabilities
- `windowed-stats`: the cached payload carries the distribution and a node
  list; two dashboard endpoints serve one window in the snapshot shape.

## Impact

- `queries/snapshots.py` (shared `distribution_stats`), `queries/window_stats.py`,
  `queries/config.py` (`WINDOW_NODES_FILE`), `app.py`, `window_stats.py` job,
  `templates/index.html`, `static/app.{js,css}`, tests, README API lists.
- The stats cache grows from ~1 KB to ~10 KB; the node cache is a few MB
  (3.7 MB for ~10k nodes) and is parsed once per rewrite (mtime-keyed
  `lru_cache`). The timer's unit already grants `data/` write access.
- MCP `get_window_stats` returns the richer payload unchanged.
