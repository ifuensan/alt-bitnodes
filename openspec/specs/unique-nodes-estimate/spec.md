# unique-nodes-estimate

## Purpose

Defines the unique-nodes-estimate subsystem: a deduplicated node estimate for
the latest snapshot computed with the 1/N weighting method over advertised
`addr` gossip, per-network-class weighted sums and an N-composition
histogram, persisted by the collector timer, served via legacy and v1
endpoints with its documented limitation stated, and presented as the middle
band of the main-page KPI matrix with its composition breakdown on the
research page.

## Requirements

### Requirement: Weighted unique-node estimate from advertised gossip
The system SHALL compute a deduplicated node estimate for the latest
snapshot using the 1/N weighting method: for each reachable address, N is
the number of distinct network classes present in that peer's advertised
`addr` gossip (`peer:*` Redis key), with N = 1 when no gossip data exists;
the estimate is the sum of 1/N over all reachable addresses. The
computation SHALL also produce per-network-class weighted sums (the 1/N
weights of addresses in each class: clearnet, tor, i2p), which together
sum to the total estimate. The computation SHALL run in the collector
timer (not the request path), use only read-only Redis commands, and
persist the estimate together with the per-class sums and a composition
histogram (share of addresses with N = 1, 2, 3+) as JSON.

#### Scenario: Estimate computed and persisted
- **WHEN** the collector timer runs
- **THEN** the persisted JSON contains the weighted estimate, the raw
  reachable count, the per-N composition histogram, and the snapshot
  timestamp it was computed from

#### Scenario: Peer without gossip data
- **WHEN** a reachable address has no `peer:*` key or an empty advertised
  list
- **THEN** it contributes weight 1 (N = 1)

### Requirement: Unique estimate served with its limitations stated
The system SHALL expose the estimate via a legacy `GET /api/unique-nodes`
endpoint and a public `GET /api/v1/stats/unique-nodes/` endpoint. Responses
SHALL include the raw reachable count alongside the estimate and a
`method` field describing the 1/N weighting and its documented limitation
(same-network multi-address nodes cannot be deduplicated).

#### Scenario: v1 response shape
- **WHEN** a client requests `GET /api/v1/stats/unique-nodes/`
- **THEN** the response contains `estimate`, `reachable`, the composition
  histogram, the source snapshot timestamp, and the `method` description

#### Scenario: No computed data yet
- **WHEN** the collector has not yet produced an estimate
- **THEN** the endpoints return an empty result with HTTP 200

### Requirement: Estimate is the middle band of the main-page KPI matrix
The main page SHALL present a three-band KPI matrix sharing the same four
columns (TOTAL, CLEARNET, TOR, I2P): band 1 = reachable nodes right now,
band 2 = the weighted unique estimate (1/N dedup) right now, band 3 = the
windowed unique counts. Band 2 SHALL show the total estimate and the
per-class weighted sums, and SHALL link to the composition breakdown on
`/research`. The composition stacked bar (share of addresses with
N = 1, 2, 3+) SHALL render on the research page, not the main page.

#### Scenario: Matrix bands aligned
- **WHEN** the main page loads and an estimate is available
- **THEN** the three bands render with aligned columns so the same
  network class can be read vertically across "now", "1/N estimate", and
  "window"

#### Scenario: Estimate unavailable
- **WHEN** no estimate has been computed yet
- **THEN** band 2 shows an em-dash placeholder in each column and the
  other two bands render normally

#### Scenario: Composition on research page
- **WHEN** the visitor follows band 2's link
- **THEN** they land on the research page section showing the stacked
  N-composition bar and the 1/N method description
