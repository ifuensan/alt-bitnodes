# rtt-history

## Purpose

Durable storage and ingestion of per-node Bitcoin protocol RTT samples sourced from the upstream `rtt:*` Redis lists. Provides the substrate that latency and rankings APIs query, ensuring samples survive Redis TTL expiry and remain available for arbitrary historical windows.

## Requirements

### Requirement: Persistent RTT sample store
The system SHALL persist Bitcoin protocol RTT samples observed by the upstream crawler in a durable local store keyed by `(address, port, ingest_timestamp, rtt_ms)`, so that median latency can be computed over arbitrary historical windows after the upstream Redis TTL has elapsed.

#### Scenario: Fresh sample is persisted
- **WHEN** the upstream crawler has written one or more new entries to a Redis list `rtt:<addr>:<port>` since the previous ingest cycle
- **THEN** the new entries SHALL appear as rows in the persistent store with the current ingest cycle's epoch second as `ts`, and SHALL remain queryable after the Redis list expires.

#### Scenario: Duplicate samples do not accumulate
- **WHEN** the same `(address, port, rtt_ms)` triple is read in the same ingest cycle more than once (e.g., overlapping cycles)
- **THEN** the persistent store SHALL contain at most one row for that triple at that `ts`.

### Requirement: Bounded retention
The system SHALL trim RTT samples older than a configurable retention horizon (default 30 days) so that the store size remains bounded.

#### Scenario: Old samples are pruned
- **WHEN** a sample's `ts` is older than the configured retention horizon
- **THEN** the sample SHALL be removed from the store within one retention-task cycle (24h).

### Requirement: Ingest cadence is shorter than upstream TTL
The system SHALL run the ingest task at an interval strictly shorter than the upstream `rtt_ttl` so that samples are not lost to TTL expiry under nominal operation.

#### Scenario: Default cadence is below upstream TTL
- **WHEN** the system is deployed with default configuration
- **THEN** the ingest interval SHALL be at most 30 seconds and SHALL be configurable via `RTT_INGEST_INTERVAL_SECONDS`.

### Requirement: Ingest can be disabled for read replicas
The system SHALL support a configuration flag that disables the ingest task while still serving reads from an existing store, so that operators can run multiple processes without write contention.

#### Scenario: Ingest disabled
- **WHEN** `RTT_INGEST_ENABLED=false`
- **THEN** the FastAPI process SHALL NOT start the ingest task and SHALL still serve all read endpoints from the existing SQLite file.
