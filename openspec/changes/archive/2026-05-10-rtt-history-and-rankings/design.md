## Context

The upstream `bitnodes` crawler emits Bitcoin protocol RTT samples into Redis as lists keyed `rtt:<addr>:<port>` (`cache_inv.cache_rtt`, `bitnodes/cache_inv.py:195`). Each list is LPUSH'd most-recent-first, capped at `rtt_count` entries, and expires after `ttl` seconds. Phase 1 of the dashboard (`bitnodes-dashboard/app.py`) already consumes the `opendata` zset and snapshot JSON files from `BITNODES_EXPORT_DIR`, but it ignores the `rtt:*` lists entirely and hard-codes `latency_ms=null` in `_v1_snapshot_payload` (`app.py:262`) and `v1_node` (`app.py:309`).

Constraints:
- Redis RTT samples expire; the dashboard runs as a separate FastAPI process and cannot extend upstream TTLs. We must read samples *out* of Redis on a cadence shorter than `rtt_ttl` and persist them.
- Snapshots are 10-minute-cadence JSON files keyed by epoch; existing endpoints already paginate these. The schema must let us join RTT samples to a known snapshot for ranking by country/ASN.
- The repo is a small FastAPI app with no ORM and no migrations framework. Adding either is overkill; SQLite via stdlib `sqlite3` keeps the dependency surface flat.
- `app.py` already uses module-level singleton patterns (`@lru_cache(maxsize=1)` for the redis client, `_addresses_state` dict). We follow the same idioms.

## Goals / Non-Goals

**Goals:**
- Durably store every fresh RTT sample observed by the upstream crawler so we can compute median RTT over arbitrary windows.
- Populate `latency_ms` in existing v1 endpoints from the new store.
- Expose latency time series, fastest-nodes leaderboard, and per-country/ASN/UA/same-IP rankings as new v1 endpoints.
- Keep ops simple: single SQLite file, no separate worker daemon required (a startup task or system cron is enough).

**Non-Goals:**
- Building a real time-series database (Prometheus, InfluxDB, ClickHouse). Volumes are small (~20k nodes × a few samples/min); SQLite handles it.
- Backfilling historical RTT before the change ships. We start collecting at deploy time.
- Compatibility with bitnodes.io's `/latency/` response shape down to the byte. We follow its spirit (median ms, time series of samples) but document our schema explicitly.
- Auth, rate limiting, or per-key quotas — out of scope for this change.

## Decisions

### Storage: single SQLite file
We use Python's stdlib `sqlite3` with WAL mode. Schema:

```sql
CREATE TABLE rtt_samples (
    address  TEXT NOT NULL,
    port     INTEGER NOT NULL,
    ts       INTEGER NOT NULL,  -- epoch seconds when ingest observed the sample
    rtt_ms   INTEGER NOT NULL,
    PRIMARY KEY (address, port, ts, rtt_ms)
) WITHOUT ROWID;
CREATE INDEX idx_rtt_node_ts ON rtt_samples(address, port, ts DESC);
CREATE INDEX idx_rtt_ts ON rtt_samples(ts);
```

`ts` is the ingest-observation timestamp (we cannot recover the precise pong-arrival time from `rtt:*` — only the elapsed milliseconds). The composite primary key dedupes when the ingest job overlaps with itself: the same `(addr, port, rtt_ms)` arriving at the same second collapses.

A retention task trims rows older than `RTT_RETENTION_DAYS` (default 30) on a daily cadence.

**Alternatives considered:**
- *Parquet partitioned by day*: cheap on disk but updating "median RTT for one node" requires scanning the partition. Not worth the complexity at this volume.
- *Postgres*: pulls in a server. We already run with Redis as the only stateful dep; adding a second is a step backwards.

### Ingest: in-process startup task on a fixed cadence
A FastAPI `startup` event launches an asyncio task that loops every `RTT_INGEST_INTERVAL_SECONDS` (default 30s, must be < `rtt_ttl`):

1. `SCAN` Redis for `rtt:*` keys (cursor-based, batches of 1000).
2. For each key, `LRANGE 0 -1` to read all samples, then keep only those *not* already stored — we track a tiny in-memory `{(addr, port): last_seen_count}` map; we re-read the list, slice off the prefix we've already ingested, and bulk-insert the rest. (Lists are LPUSH'd most-recent-first, capped, so list length is monotonic until cap is reached then stable. Tracking `len(list_at_last_ingest)` is sufficient: anything *above* that count when re-read is new.)
3. Bulk `INSERT OR IGNORE` into `rtt_samples` with the current ingest epoch as `ts`.

This sacrifices per-sample timing precision (every sample within one ingest cycle gets the same `ts`) for simplicity. Acceptable because median windows are minutes-scale.

**Alternatives considered:**
- *Separate `rtt_ingest.py` daemon*: cleaner separation but doubles the deploy footprint and the systemd units.
- *Redis keyspace notifications*: real-time but Redis isn't configured for them in the upstream pipeline, and we'd need a persistent subscriber anyway.

### Latency aggregation: median over sliding window
For `latency_ms` in node payloads, we compute median over the last `RTT_WINDOW_SECONDS` (default 1800s = 30 min) — long enough to be stable across one snapshot cycle, short enough to reflect current conditions. Median (not mean) matches bitnodes.io's published behavior and resists outliers from packet-loss-driven retries.

### Ranking joins: rebuild from latest snapshot at request time
Country/ASN/UA rankings join the latest snapshot's per-node geo metadata against per-node median RTT from SQLite. We do *not* persist country/ASN per sample — that data already lives in the snapshot JSON files and would just be redundant. We compute the join in Python over the snapshot rows (snapshots are already in `lru_cache`) and a single SQLite aggregate query:

```sql
SELECT address, port, MEDIAN(rtt_ms) AS p50  -- via percentile_cont workaround
FROM rtt_samples
WHERE ts >= ?
GROUP BY address, port
```

SQLite has no built-in `MEDIAN`; we implement it as a Python custom aggregate registered on each connection. (Numpy is overkill — `statistics.median` on lists of ints is fine.)

### Same-IP grouping
Trivial Python pass over the latest snapshot grouping by `address`. No DB query needed; the snapshot JSON is the authoritative source for "who is up right now". The endpoint returns `{address, ports: [...], total_nodes: N}`.

### Endpoints

| Path | Behavior |
|------|----------|
| `/api/v1/nodes/{node_id}/latency/` | Returns `{address, latency: [[ts, rtt_ms], ...]}` for the node, last `?hours=N` (default 24, max 168). |
| `/api/v1/leaderboard/` | Top-N fastest by median RTT in window. Filters: `?country=`, `?asn=`, `?limit=` (default 50, max 500). |
| `/api/v1/rankings/countries/` | Per-country `{country, total_nodes, median_rtt_ms}` sorted by node count desc. |
| `/api/v1/rankings/asns/` | Per-ASN equivalent. |
| `/api/v1/rankings/user-agents/` | Per-UA equivalent. |
| `/api/v1/groups/by-ip/` | List of `{address, ports, total_nodes}` where `total_nodes >= 2`, sorted by count desc. |
| `/api/v1/groups/by-ip/{address}/` | Detail for one address: list of `(port, latency_ms, height, user_agent)`. |

Existing `_v1_snapshot_payload` and `v1_node` start filling `latency_ms` from the same median query.

### Configuration
New env vars (all optional with defaults):
- `RTT_DB_PATH` — default `<EXPORT_DIR_parent>/rtt.sqlite`
- `RTT_INGEST_INTERVAL_SECONDS` — default 30
- `RTT_WINDOW_SECONDS` — default 1800
- `RTT_RETENTION_DAYS` — default 30
- `RTT_INGEST_ENABLED` — default `true`; set `false` for read-only replicas or test runs

## Risks / Trade-offs

- [Sample precision] RTT timestamps are batched per ingest cycle, not per pong. → Accept; document in spec. Median over 30-min windows is unaffected.
- [Sample loss] If the FastAPI process is down longer than `rtt_ttl`, we lose samples that expired in Redis. → Mitigation: ingest interval default of 30s leaves headroom; document the constraint; keep ingest in-process so it shares process supervision.
- [SQLite write contention] Single writer with WAL mode is fine for one ingest task + many readers, but if we ever scale to multiple FastAPI workers writing concurrently we'll see SQLITE_BUSY. → Mitigation: gate ingest with `RTT_INGEST_ENABLED` so only one worker writes; document in deploy notes.
- [Slowstart of latency_ms] On a fresh deploy, `latency_ms` is null until the first ingest cycle completes (~30s). → Acceptable; the existing field has been null forever.
- [Pagination of `addresses` endpoint] Already covered in phase 1; we don't change it.
- [Snapshot/RTT skew] A node may appear in the latest snapshot but have no recent RTT (or vice versa). → Endpoints surface `latency_ms: null` rather than dropping the row.

## Migration Plan

1. Ship the SQLite schema bootstrap inside `app.py` startup: `CREATE TABLE IF NOT EXISTS …`. No external migration tool.
2. Deploy. The ingest task starts populating immediately.
3. After first ingest cycle, existing `/api/v1/snapshots/{ts}/` and `/api/v1/nodes/{node_id}/` responses begin returning real `latency_ms` integers. No breaking change — clients that handled `null` already keep working.
4. Drop the "phase 2 pending" caveat from `V1_NOTE` in the same release.

Rollback: stop the process, remove the SQLite file (or just disable ingest with `RTT_INGEST_ENABLED=false`). The new endpoints return empty results; existing endpoints return `latency_ms=null` again. No upstream-affecting changes.

## Open Questions

- Should the leaderboard expose `min_rtt` in addition to median? Defer until first user feedback.
- Do we want a `/api/v1/rankings/asns/{asn}/` detail endpoint listing nodes in one ASN? Out of scope for this change; can add later if requested.
