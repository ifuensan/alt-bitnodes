## ADDED Requirements

### Requirement: Each window carries a distribution in the snapshot-stats shape

For every configured window the cached payload SHALL include a
`distribution` object with the same keys as the per-snapshot stats (network
split, `countries_total`, `asns_total`, `user_agents_total`,
`median_height`, `top_countries`, `top_user_agents`, `top_asns`,
`countries_iso3`, `height_histogram`), computed over one row per unique
node — the row of that node's most recent sighting inside the window — and
a `since` cutoff timestamp.

#### Scenario: Latest sighting defines the node
- **WHEN** a node appears in several snapshots of the window with different
  attributes (country, user agent, height)
- **THEN** the window's distribution counts it once, with the attributes of
  its most recent sighting

### Requirement: The union's node list is cached separately

The job SHALL write, next to the stats cache, a node file for the widest
window holding each unique node's row plus its `last_seen` timestamp. The
public `/api/v1/stats/window` payload SHALL NOT include node rows.

#### Scenario: Narrower windows read from the same file
- **WHEN** nodes are requested for a window narrower than the widest one
- **THEN** the result is the subset whose `last_seen` is on or after that
  window's cutoff, with no recompute

### Requirement: Dashboard endpoints serve one window in the snapshot shape

`GET /api/window/{days}/stats` SHALL return the window's distribution
flattened to the shape of `GET /api/snapshot/{ts}/stats`, plus `days`,
`snapshots`, `since` and `generated_at`. `GET /api/window/{days}` SHALL
return `{days, generated_at, since, count, nodes}` with `last_seen` on each
node. Both SHALL serve the caches only.

#### Scenario: Window not cached
- **WHEN** the cache is absent, empty, or does not hold the requested window
- **THEN** both endpoints respond 404 with a clear detail, never a
  synchronous recompute
