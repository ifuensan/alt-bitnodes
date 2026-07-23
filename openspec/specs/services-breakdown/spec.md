# services-breakdown

## Purpose

Defines the services-breakdown subsystem: decoding the `services` bitmask of
snapshot rows into named capability flags, computing per-flag adoption counts
and percentages (total and per network class) for the latest snapshot,
maintaining a daily-sampled historical adoption series persisted from the raw
export directory, serving both via legacy and v1 endpoints, and rendering the
compact main-page strip plus the full research-page adoption charts.

## Requirements

### Requirement: Services bitmask decoded into named capability flags
The data layer SHALL decode the `services` field of snapshot rows into
named flags — at minimum NODE_NETWORK (1), NODE_BLOOM (4), NODE_WITNESS
(8), NODE_COMPACT_FILTERS (64), NODE_NETWORK_LIMITED (1024), and
NODE_P2P_V2 (2048) — and compute, for a given snapshot, the count and
percentage of reachable nodes advertising each flag, in total and split by
network class. Bits outside the named set SHALL be aggregated as `other`
with the raw mask preserved, never silently dropped.

#### Scenario: Latest snapshot breakdown
- **WHEN** the breakdown is computed for the latest snapshot
- **THEN** it returns, per flag, the node count and percentage overall and
  per network class (ipv4, ipv6, onion, i2p)

#### Scenario: Unknown bits surfaced
- **WHEN** a node advertises a service bit outside the named set
- **THEN** it is counted under `other` and the raw bitmask remains
  available in the per-flag detail

### Requirement: Historical adoption series sampled daily from the export dir
The system SHALL maintain a historical series of per-flag adoption
percentages sampled at the last snapshot of each complete UTC day from the
raw export directory, refreshed by the collector timer, backfilled up to
90 days on first run, and persisted as JSON served without recomputation
in the request path. Because the persisted series accumulates (sampled
days are never recomputed), export pruning does not erase history.

> Criterion change 2026-07-23 (review decision D1): the original draft
> specified sampling "from the archive" (GFS photo archive). Amended to
> the raw export dir before first ship: the GFS archive only holds daily
> photos for 7 days (weekly/monthly beyond), so it cannot source a
> *daily* series past one week, while the export dir covers the full
> 90-day backfill window in native JSON.

#### Scenario: Series refresh
- **WHEN** the collector timer runs on a new day
- **THEN** the series gains that day's sample and the persisted JSON is
  updated

#### Scenario: Missing day
- **WHEN** no snapshot exists on disk for a given day and the day is not
  already in the persisted series
- **THEN** that day is absent from the series (no interpolation) and the
  refresh continues

### Requirement: Services data served via legacy and v1 endpoints
The system SHALL expose the latest-snapshot breakdown and the historical
series via a legacy `GET /api/services` endpoint for the dashboard and a
public `GET /api/v1/stats/services/` endpoint.

#### Scenario: v1 response shape
- **WHEN** a client requests `GET /api/v1/stats/services/`
- **THEN** the response contains the latest-snapshot per-flag breakdown
  (total and per network class) and the daily adoption series per flag

### Requirement: Main page shows a compact services strip
The main page SHALL show a compact one-line services strip below the KPI
matrix with the adoption percentages of the headline flags (at minimum
NODE_P2P_V2, NODE_COMPACT_FILTERS, NODE_NETWORK_LIMITED), linking to the
full services section on `/research`. The strip SHALL contain numbers and
labels only — no chart marks — styled from design-system tokens.

#### Scenario: Strip renders
- **WHEN** the main page loads and services data is available
- **THEN** the strip shows each headline flag's adoption percentage and
  links to the research page's services section

### Requirement: Research page renders services adoption charts
The research page SHALL render the full services section using Observable
Plot: a horizontal bar chart of per-flag adoption percentage for the
latest snapshot with a per-network grouped variant, and small-multiple
line charts of the daily adoption series (one panel per flag, shared
y-scale 0–100%). All styling SHALL come from design-system tokens;
tooltips SHALL show flag name, bit value, count, and percentage.

#### Scenario: Adoption bars render
- **WHEN** the research page loads and services data is available
- **THEN** one bar per named flag is shown, sorted by adoption descending,
  with `other` last

#### Scenario: Historical small multiples render
- **WHEN** the daily series contains at least two days
- **THEN** each flag renders a small line panel showing adoption % over
  time, so adoption trends (e.g., NODE_P2P_V2) are visible
