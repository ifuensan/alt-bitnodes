## Why

Phase 1 shipped a bitnodes.io-compatible v1 API but left `latency_ms` permanently `null` because RTT samples live only in capped, TTL-bounded Redis lists (`rtt:<addr>:<port>`) populated by the upstream `bitnodes/cache_inv.py` PCAP pipeline. Without durable history we cannot fill `latency_ms`, expose per-node latency time series, or compute the leaderboards/rankings that make the dashboard actually useful for comparing operators, ASNs, and countries.

## What Changes

- Persist a rolling RTT history in a local SQLite database fed by a periodic ingest job that copies fresh samples out of Redis before they expire.
- Backfill `latency_ms` in the existing `/api/v1/snapshots/{ts}/` and `/api/v1/nodes/{node_id}/` payloads using the median of recent RTT samples (matching bitnodes.io semantics).
- Add a per-node latency time-series endpoint (`/api/v1/nodes/{node_id}/latency/`).
- Add a fastest-nodes leaderboard endpoint with optional `country` and `asn` filters.
- Add ranking endpoints aggregated by country, ASN, and user-agent (count + median RTT each).
- Add a "same-IP group" endpoint that lists all `(address, port)` pairs sharing one IP (multi-port deployments behind a single host).
- Drop the phase-1 "latency_ms is currently null" caveat from `V1_NOTE`.

## Capabilities

### New Capabilities
- `rtt-history`: Durable storage and ingestion of per-node Bitcoin protocol RTT samples sourced from the upstream `rtt:*` Redis lists.
- `latency-api`: Public v1 endpoints exposing per-node latency (current median + time series) and populating `latency_ms` in existing snapshot/node payloads.
- `rankings-api`: Leaderboard and ranking endpoints (fastest nodes, by country, by ASN, by user-agent, same-IP group) backed by RTT history joined with snapshot metadata.

### Modified Capabilities
<!-- No modified capabilities: phase 1 didn't write specs (legacy code), so phase 2 introduces the first specs. The behavior change to /api/v1/snapshots/{ts}/ and /api/v1/nodes/{node_id}/ is captured under latency-api as a new requirement on those endpoints. -->

## Impact

- New runtime dependency: `sqlite3` (Python stdlib, no new package) and a writable data directory for the DB file.
- New background process or scheduled task: `rtt_ingest.py` (or an async task inside `app.py` on FastAPI startup) that pulls from Redis on a fixed cadence.
- `app.py` gains new routes and a thin SQLite query layer; the existing `_v1_snapshot_payload` and `v1_node` change to read latency from the DB.
- Operators must provision an `RTT_DB_PATH` env var (with sensible default) and ensure the ingest cadence is shorter than `rtt_ttl` from upstream `ping.py` to avoid sample loss.
- No breaking API changes: existing fields keep their shape; `latency_ms` simply transitions from always-`null` to a populated integer (milliseconds) when samples exist.
