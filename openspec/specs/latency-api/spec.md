# latency-api

## Purpose

Public v1 endpoints exposing per-node latency: median over a sliding window for `latency_ms` in existing snapshot/node payloads, plus a per-node time-series endpoint. Brings the dashboard's bitnodes.io-compatible API to feature parity for the `latency_ms` field.

## Requirements

### Requirement: latency_ms populated in existing v1 payloads
The system SHALL populate the `latency_ms` field in `/api/v1/snapshots/{timestamp}/`, `/api/v1/snapshots/latest/`, and `/api/v1/nodes/{node_id}/` with the median RTT in milliseconds over the most recent configured window (default 1800 seconds), or `null` when no samples exist for that node within the window.

#### Scenario: Node with recent samples
- **WHEN** a client requests `/api/v1/nodes/{addr}-{port}/` and one or more RTT samples for that node exist within the latency window
- **THEN** the response `data` array's fourth element SHALL be an integer equal to the median of those samples in milliseconds.

#### Scenario: Node with no recent samples
- **WHEN** a client requests `/api/v1/nodes/{addr}-{port}/` and no RTT samples for that node exist within the latency window
- **THEN** the response `data` array's fourth element SHALL be `null` and the request SHALL still return 200.

#### Scenario: Snapshot payload populates latency for every node
- **WHEN** a client requests `/api/v1/snapshots/latest/`
- **THEN** every entry in the `nodes` map whose `(address, port)` has samples within the window SHALL have a non-null `latency_ms` (5th array position), and entries without samples SHALL have `null`.

### Requirement: Per-node latency time series endpoint
The system SHALL expose `GET /api/v1/nodes/{node_id}/latency/` returning the time series of RTT samples for one node over the requested window.

#### Scenario: Default window
- **WHEN** a client requests `/api/v1/nodes/{addr}-{port}/latency/` without query parameters
- **THEN** the response SHALL be `{"address": "<addr>", "latency": [[ts, rtt_ms], ...]}` covering the last 24 hours, sorted by `ts` ascending.

#### Scenario: Custom window
- **WHEN** a client passes `?hours=N` with `1 <= N <= 168`
- **THEN** the response SHALL cover the last `N` hours of samples.

#### Scenario: Window out of range
- **WHEN** a client passes `?hours=0` or `?hours=200`
- **THEN** the response SHALL be HTTP 422 with a description of the allowed range (FastAPI default for query-parameter validation errors).

#### Scenario: Unknown node
- **WHEN** the requested `node_id` has never produced samples and is not in the latest snapshot
- **THEN** the response SHALL be HTTP 404.

#### Scenario: Known node with no samples
- **WHEN** the requested `node_id` is in the latest snapshot but has no samples in the window
- **THEN** the response SHALL be HTTP 200 with `latency: []`.

### Requirement: V1_NOTE no longer claims latency is null
The system SHALL NOT advertise that `latency_ms` is "currently null pending RTT persistence" once this capability is implemented.

#### Scenario: OpenAPI description updated
- **WHEN** a client fetches the OpenAPI schema or v1 endpoint summaries
- **THEN** there SHALL be no text claiming that `latency_ms` is null pending phase 2.
