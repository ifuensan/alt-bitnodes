# Design — dashboard union view

## Membership by last sighting

A node belongs to an N-day window iff it was seen in any snapshot after the
cutoff, which is the same as "its *last* sighting is after the cutoff". So
one pass keeps `latest[(address, port)] = (ts, row)` over the widest window
and every narrower window is a filter over that dict. This replaces the
four per-window sets of the original job with one dict and gives each node
a canonical row (the most recent) for the distribution — a node that moved
country or upgraded its user agent counts once, with its newest attributes.

## One shape for both views

`snapshot_stats` was split into `distribution_stats(rows)` (pure, over any
row list) plus the timestamp. The window job calls the same function per
window, so `/api/window/{days}/stats` returns exactly the keys the frontend
already consumes for `/api/snapshot/{ts}/stats`, plus `days`, `snapshots`,
`since`, `generated_at`. The frontend's renderers (`renderCharts`,
`updateTable`, side KPIs) take either payload through one `applyView`.

## Two cache files

The v1 window endpoint is public and MCP-exposed; attaching ~10k node rows
to it would turn a 1 KB response into megabytes. The distribution (bounded:
15-entry rankings + ≤250 ISO-3 pairs per window) stays in
`window-stats.json`; the node list goes to `window-nodes.json`, written
atomically by the same run, for the widest window only. The read side
filters by `last_seen >= generated_at - days*86400`, so any configured
window is served from one file. Parsing a multi-MB JSON per request is
avoided with an `lru_cache` keyed on `(path, mtime_ns)`.

## 404, not empty

Unlike `/api/v1/stats/window` (empty payload when the cache is missing —
an aggregate reads fine as zeros), a *view* with no data is not renderable.
The dashboard endpoints return 404 and the toggle treats 404 as "not
available yet": it disables itself and the page stays on LIVE.

## Naming

`LIVE` and `8-DAY UNION` rather than "realtime" / "static": the second
view is not static (it moves hourly) and what distinguishes it is the
union semantics the KPI band already calls "Unique over 8 days".
`UNION_DAYS` is a frontend constant; the API accepts any configured window.
