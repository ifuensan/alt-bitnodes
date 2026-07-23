# block-propagation

## Purpose

Defines the block-propagation subsystem: a timer-driven collector that reads
per-block `binv:*` Redis zsets and persists per-block propagation statistics
(announcer counts and per-network-class percentiles and ECDF points relative
to each block's first observed announcement) before Redis rotation, the
legacy and v1 REST endpoints that serve that persisted data, and the research
page ECDF chart that visualizes it. All propagation data is served from
persisted JSON files, never from Redis in the request path.

## Requirements

### Requirement: Propagation collector persists per-block stats before Redis rotation
The system SHALL provide a timer-driven collector that reads `binv:*` Redis
zsets and persists, for every completed block, a JSON document containing
the block hash, first-observed timestamp, announcer count, and per-network-
class (ipv4, ipv6, onion, i2p) percentiles and ECDF points of announcement
time relative to the block's first observed announcement. Blocks whose
first announcement is less than 30 minutes old SHALL be skipped as still
accumulating. Collected files SHALL be pruned after 30 days. The collector
SHALL issue only read-only Redis commands.

#### Scenario: Completed block is collected once
- **WHEN** the collector runs and finds a `binv:<hash>` zset whose first
  announcement is older than 30 minutes and no JSON file exists for `<hash>`
- **THEN** it writes one JSON document for that block with per-class
  percentiles and ECDF points, and subsequent runs do not rewrite it

#### Scenario: Hot block is deferred
- **WHEN** the collector finds a block first announced less than 30 minutes ago
- **THEN** no file is written for it in that run

#### Scenario: Section failures are isolated
- **WHEN** collection of one block raises an exception
- **THEN** the collector logs it and continues with the remaining blocks

### Requirement: Propagation data served via legacy and v1 endpoints
The system SHALL serve collected propagation data from the persisted JSON
files (never from Redis in the request path): a legacy `GET /api/propagation`
endpoint shaped for the dashboard charts, and a public
`GET /api/v1/stats/propagation/` endpoint. Both SHALL include the aggregate
median ECDF over recent blocks, the recent-blocks list with per-class
percentiles, and a definition note stating times are relative to the
crawler's first observation.

#### Scenario: Aggregate response
- **WHEN** a client requests `GET /api/v1/stats/propagation/`
- **THEN** the response contains an aggregate ECDF per network class over
  the most recent collected blocks and a list of those blocks with height,
  hash, announcer count, and per-class p50/p90

#### Scenario: No collected data yet
- **WHEN** no propagation files exist
- **THEN** endpoints return an empty result with HTTP 200, not an error

### Requirement: Research page renders propagation ECDF chart
The research page (`/research`) SHALL render the block-propagation
section using Observable
Plot: an ECDF step-line chart with x = milliseconds since first observed
announcement on a log scale, y = cumulative fraction of announcers, one
line per network class using the same class-color mapping as the network
breakdown tiles, plus a dense table of recent blocks. Selecting a block in
the table SHALL switch the chart from the aggregate view to that block.
All colors SHALL come from design-system tokens.

#### Scenario: Default aggregate view
- **WHEN** the research page loads and propagation data is available
- **THEN** the ECDF chart shows the aggregate median curves per network
  class, with a caption stating the first-heard-relative definition

#### Scenario: Per-block drill-down
- **WHEN** the user selects a row in the recent-blocks table
- **THEN** the chart re-renders showing that single block's ECDF curves
