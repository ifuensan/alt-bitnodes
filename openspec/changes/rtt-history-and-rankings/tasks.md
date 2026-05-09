## 1. Storage layer

- [x] 1.1 Add `RTT_DB_PATH`, `RTT_INGEST_INTERVAL_SECONDS`, `RTT_WINDOW_SECONDS`, `RTT_RETENTION_DAYS`, `RTT_INGEST_ENABLED` env-var defaults near the top of `app.py` next to `EXPORT_DIR` / `REDIS_URL`.
- [x] 1.2 Add a `_db()` helper (cached connection, `check_same_thread=False`, WAL mode) that creates the SQLite file and runs `CREATE TABLE IF NOT EXISTS rtt_samples (...) WITHOUT ROWID;` plus `idx_rtt_node_ts` and `idx_rtt_ts` indexes on first call.
- [x] 1.3 Register a Python `median` aggregate on each connection (uses `statistics.median` on accumulated ints).

## 2. Ingest task

- [x] 2.1 Implement `ingest_once(redis_conn, db_conn, prev_lengths)` that SCANs `rtt:*`, LRANGEs each, slices off already-ingested prefix using the `prev_lengths` map, bulk-INSERT-OR-IGNOREs new rows with the current epoch as `ts`, and returns the updated `prev_lengths`.
- [x] 2.2 Wire a FastAPI `@app.on_event("startup")` handler that, when `RTT_INGEST_ENABLED` is true, launches an asyncio task running `ingest_once` every `RTT_INGEST_INTERVAL_SECONDS`, logging exceptions and continuing.
- [x] 2.3 Add a daily retention pass inside the same loop (or a sibling task) that deletes `WHERE ts < strftime('%s','now') - RTT_RETENTION_DAYS*86400`.

## 3. Median + window helpers

- [x] 3.1 Implement `median_rtt_for(addr, port, window_seconds)` returning `int | None`.
- [x] 3.2 Implement `medians_in_window(window_seconds)` returning `dict[(addr, port), int]` for use by ranking endpoints (single query, group by node).
- [x] 3.3 Implement `samples_for(addr, port, hours)` returning `list[(ts, rtt_ms)]` for the time-series endpoint.

## 4. Wire latency_ms into existing v1 payloads

- [x] 4.1 In `_v1_snapshot_payload` (`app.py:262`), build the medians map once via `medians_in_window`, then replace the hardcoded `None` (4th slot of each `nodes[...]` value) with `medians.get((addr, port))`.
- [x] 4.2 In `v1_node` (`app.py:309`), call `median_rtt_for` and substitute it into the `data` array (4th slot) for both UP and DOWN branches.
- [x] 4.3 Update `V1_NOTE` to drop the "latency_ms is currently null pending ... phase 2" caveat.

## 5. New v1 endpoints

- [x] 5.1 `GET /api/v1/nodes/{node_id}/latency/?hours=N` — validate `1 <= N <= 168`, 404 when unknown node, 200 with `latency: []` for known-but-no-samples.
- [x] 5.2 `GET /api/v1/leaderboard/?country=&asn=&limit=` — join latest snapshot rows with `medians_in_window`, filter, sort by `latency_ms` asc, cap at `limit` (default 50, max 500).
- [x] 5.3 `GET /api/v1/rankings/countries/` — group latest snapshot by country, attach median RTT computed from that country's nodes' samples; return `country` + `country_iso3` (via existing `iso2_to_iso3`).
- [x] 5.4 `GET /api/v1/rankings/asns/` — analogous; key on `asn` and include `asn_name`.
- [x] 5.5 `GET /api/v1/rankings/user-agents/` — analogous; key on the raw UA string.
- [x] 5.6 `GET /api/v1/groups/by-ip/` — group latest snapshot by `address`, keep groups with `>= 2` nodes, sort by count desc.
- [x] 5.7 `GET /api/v1/groups/by-ip/{address}/` — detail per port with `latency_ms`, 404 when absent.

## 6. Dashboard surface (optional polish)

- [x] 6.1 Add a "Latency" KPI card to `templates/index.html` showing the network-wide median RTT for the current snapshot.
- [x] 6.2 Add a "Fastest nodes" table fed by `/api/v1/leaderboard/?limit=20`.

## 7. Tests & manual verification

- [x] 7.1 Add a smoke test (or manual `curl` checklist in `deploy/`) that hits each new endpoint and asserts shape + non-null `latency_ms` after one ingest cycle.
- [x] 7.2 Verify with `sqlite3 rtt.sqlite 'SELECT count(*), min(ts), max(ts) FROM rtt_samples'` that ingest is producing rows at the expected cadence.
- [x] 7.3 Confirm `latency_ms` populates in `/api/v1/snapshots/latest/` and `/api/v1/nodes/{node_id}/`, and that the response shape is unchanged for clients that previously parsed `null`.

## 8. Docs

- [x] 8.1 Update README (or create `deploy/RTT.md`) with the new env vars, ingest cadence guidance vs. upstream `rtt_ttl`, and rollback steps.
