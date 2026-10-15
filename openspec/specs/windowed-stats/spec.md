# windowed-stats Specification

## Purpose
The rolling-window union metric — unique `(address, port)` per network over N days, the figure bitnodes-style trackers report — how it is computed, cached by a timer, and served to the API, the MCP and the dashboard's union view.
## Requirements
### Requirement: Unique nodes are counted per network over rolling windows

The system SHALL compute, for each configured window (1, 3, 5, 8 and 24
days), the count of unique `(address, port)` pairs seen across all snapshots
in that window, split by network type: clearnet (IPv4 + IPv6, reported
separately too), tor (`.onion`), and i2p (`.b32.i2p`). Each window result
SHALL include the number of snapshots it covered and the union total. The
widest window SHALL be bounded by the raw-export retention.

#### Scenario: Union across the window
- **WHEN** the windowed compute runs over the snapshots on disk
- **THEN** for each window it reports ipv4/ipv6/tor/i2p unique counts, the
  clearnet and grand totals, and the snapshot count, deduplicating a node
  that appears in many snapshots to a single unit

#### Scenario: The 24-day window is wider than the 8-day one
- **WHEN** a node's last sighting is 10 days before the reference time
- **THEN** it is counted in the 24-day window and not in the 8-day window

### Requirement: The windowed counts are precomputed and cached

Because the union reads hundreds of snapshot files, it SHALL be precomputed
by a scheduled job and cached to a JSON file; the API SHALL serve the cached
file rather than computing on request. A missing or unreadable cache SHALL
yield an empty/last-known result, never a slow synchronous recompute in the
request path.

#### Scenario: API serves the cache
- **WHEN** a client requests the windowed counts
- **THEN** the response is served from the cached file without triggering a
  full recompute

#### Scenario: Cache absent
- **WHEN** no cache file exists yet
- **THEN** the endpoint responds with an empty result and a clear indication
  that no windowed data is available yet, not an error or a hang

### Requirement: The dashboard shows instantaneous and windowed totals

The dashboard SHALL present the windowed unique-node totals alongside the
instantaneous snapshot count, so a visitor can see both "reachable now" and
"unique over N days".

#### Scenario: Both figures visible
- **WHEN** windowed data is available
- **THEN** the dashboard shows the N-day unique total next to the
  instantaneous reachable-nodes figure


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
