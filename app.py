import asyncio
import json
import logging
import os
import sqlite3
import statistics
import threading
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import pycountry
import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger("alt-bitnodes")

EXPORT_DIR = Path(
    os.environ.get(
        "BITNODES_EXPORT_DIR",
        "/mnt/datos/home_data/Work/myprojects/research/bitnodes/data/export/f9beb4d9",
    )
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
OPENDATA_TTL_SECONDS = 10

RTT_DB_PATH = Path(
    os.environ.get("RTT_DB_PATH", str(Path(__file__).resolve().parent / "data" / "rtt.sqlite"))
)
RTT_INGEST_INTERVAL_SECONDS = int(os.environ.get("RTT_INGEST_INTERVAL_SECONDS", "30"))
RTT_WINDOW_SECONDS = int(os.environ.get("RTT_WINDOW_SECONDS", "1800"))
RTT_RETENTION_DAYS = int(os.environ.get("RTT_RETENTION_DAYS", "30"))
RTT_INGEST_ENABLED = os.environ.get("RTT_INGEST_ENABLED", "true").lower() in ("1", "true", "yes", "on")

FIELDS = [
    "address", "port", "protocol_version", "user_agent", "timestamp",
    "services", "height", "hostname", "city", "country",
    "latitude", "longitude", "timezone", "asn", "asn_name",
]

app = FastAPI(title="alt-bitnodes")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def iso2_to_iso3(code: str) -> str | None:
    if not code:
        return None
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None


def list_snapshots() -> list[int]:
    if not EXPORT_DIR.exists():
        return []
    return sorted(
        int(p.stem) for p in EXPORT_DIR.glob("*.json") if p.stem.isdigit()
    )


@lru_cache(maxsize=32)
def load_snapshot(timestamp: int) -> list[list]:
    path = EXPORT_DIR / f"{timestamp}.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


@lru_cache(maxsize=4096)
def snapshot_meta(timestamp: int) -> dict:
    rows = load_snapshot(timestamp)
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    return {
        "timestamp": timestamp,
        "total_nodes": len(rows),
        "latest_height": max(heights) if heights else 0,
    }


def to_dict(row: list) -> dict:
    return dict(zip(FIELDS, row))


def parse_node_id(node_id: str) -> tuple[str, int]:
    if "-" not in node_id:
        raise ValueError("missing '-'")
    addr, _, port_s = node_id.rpartition("-")
    if not port_s.isdigit():
        raise ValueError("port must be numeric")
    if addr.startswith("[") and addr.endswith("]"):
        addr = addr[1:-1]
    return addr, int(port_s)


_addresses_state: dict = {"last_ts": 0, "set": set()}


def known_addresses_set() -> set:
    snaps = list_snapshots()
    new_ts = [t for t in snaps if t > _addresses_state["last_ts"]]
    for t in new_ts:
        try:
            rows = load_snapshot(t)
        except FileNotFoundError:
            continue
        for r in rows:
            _addresses_state["set"].add((r[0], r[1]))
    if new_ts:
        _addresses_state["last_ts"] = max(new_ts)
    return _addresses_state["set"]


@lru_cache(maxsize=1)
def _redis():
    return redis.Redis.from_url(REDIS_URL, decode_responses=False)


_opendata_cache: dict = {"ts": 0.0, "index": {}}


def opendata_index() -> dict:
    """Map "<addr>:<port>" -> (raw_data_list, score). Cached for OPENDATA_TTL_SECONDS."""
    now = time.time()
    if now - _opendata_cache["ts"] < OPENDATA_TTL_SECONDS and _opendata_cache["index"]:
        return _opendata_cache["index"]
    try:
        items = _redis().zrange("opendata", 0, -1, withscores=True)
    except redis.RedisError:
        return {}
    index: dict = {}
    for raw, score in items:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list) or len(data) < 2:
            continue
        index[f"{data[0]}:{data[1]}"] = (data, score)
    _opendata_cache.update({"ts": now, "index": index})
    return index


def paginate(items: list, page: int, limit: int, base_path: str) -> dict:
    count = len(items)
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]
    next_url = f"{base_path}?page={page+1}&limit={limit}" if end < count else None
    prev_url = f"{base_path}?page={page-1}&limit={limit}" if page > 1 else None
    return {
        "count": count,
        "next": next_url,
        "previous": prev_url,
        "page_items": page_items,
    }


# ---------------------------------------------------------------------------
# RTT history (SQLite)
# ---------------------------------------------------------------------------

class _MedianAgg:
    def __init__(self) -> None:
        self.values: list[int] = []

    def step(self, value) -> None:
        if value is not None:
            self.values.append(int(value))

    def finalize(self):
        if not self.values:
            return None
        return int(statistics.median(self.values))


_db_lock = threading.Lock()


@lru_cache(maxsize=1)
def _db() -> sqlite3.Connection:
    RTT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(RTT_DB_PATH), check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rtt_samples (
            address TEXT NOT NULL,
            port    INTEGER NOT NULL,
            ts      INTEGER NOT NULL,
            rtt_ms  INTEGER NOT NULL,
            PRIMARY KEY (address, port, ts, rtt_ms)
        ) WITHOUT ROWID;
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rtt_node_ts ON rtt_samples(address, port, ts DESC);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rtt_ts ON rtt_samples(ts);")
    conn.create_aggregate("median", 1, _MedianAgg)
    return conn


def _parse_rtt_key(key: bytes) -> tuple[str, int] | None:
    """rtt:<addr>-<port> → (addr, port). addr may contain ':' (IPv6)."""
    try:
        s = key.decode("ascii", "replace")
    except Exception:
        return None
    if not s.startswith("rtt:"):
        return None
    rest = s[4:]
    addr, _, port_s = rest.rpartition("-")
    if not addr or not port_s.isdigit():
        return None
    return addr, int(port_s)


def ingest_once(redis_conn: redis.Redis, prev_state: dict) -> dict:
    """Pull fresh RTT samples from Redis into SQLite. Returns updated state."""
    now = int(time.time())
    new_state: dict = {}
    inserts: list[tuple[str, int, int, int]] = []

    cursor = 0
    while True:
        cursor, batch = redis_conn.scan(cursor=cursor, match="rtt:*", count=1000)
        for key in batch:
            parsed = _parse_rtt_key(key)
            if parsed is None:
                continue
            addr, port = parsed
            try:
                items = redis_conn.lrange(key, 0, -1)  # head first (newest)
            except redis.RedisError:
                continue
            if not items:
                continue

            new_len = len(items)
            prev_head, prev_len = prev_state.get((addr, port), (None, 0))
            if prev_head is None:
                new_count = new_len
            elif new_len > prev_len:
                new_count = new_len - prev_len
            elif items[0] == prev_head:
                new_count = 0
            else:
                try:
                    new_count = items.index(prev_head)
                except ValueError:
                    new_count = new_len

            for v in items[:new_count]:
                try:
                    rtt_ms = int(v)
                except (ValueError, TypeError):
                    continue
                inserts.append((addr, port, now, rtt_ms))

            new_state[(addr, port)] = (items[0], new_len)
        if cursor == 0:
            break

    if inserts:
        with _db_lock:
            _db().executemany(
                "INSERT OR IGNORE INTO rtt_samples(address, port, ts, rtt_ms) VALUES (?, ?, ?, ?)",
                inserts,
            )
    return new_state


def retention_pass() -> int:
    cutoff = int(time.time()) - RTT_RETENTION_DAYS * 86400
    with _db_lock:
        cur = _db().execute("DELETE FROM rtt_samples WHERE ts < ?", (cutoff,))
        return cur.rowcount or 0


def median_rtt_for(addr: str, port: int, window_seconds: int = RTT_WINDOW_SECONDS) -> int | None:
    cutoff = int(time.time()) - window_seconds
    row = _db().execute(
        "SELECT median(rtt_ms) FROM rtt_samples WHERE address=? AND port=? AND ts>=?",
        (addr, port, cutoff),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def medians_in_window(window_seconds: int = RTT_WINDOW_SECONDS) -> dict[tuple[str, int], int]:
    cutoff = int(time.time()) - window_seconds
    rows = _db().execute(
        "SELECT address, port, median(rtt_ms) FROM rtt_samples WHERE ts>=? GROUP BY address, port",
        (cutoff,),
    ).fetchall()
    return {(r[0], r[1]): r[2] for r in rows if r[2] is not None}


def samples_for(addr: str, port: int, hours: int) -> list[tuple[int, int]]:
    cutoff = int(time.time()) - hours * 3600
    rows = _db().execute(
        "SELECT ts, rtt_ms FROM rtt_samples WHERE address=? AND port=? AND ts>=? ORDER BY ts ASC",
        (addr, port, cutoff),
    ).fetchall()
    return [(int(r[0]), int(r[1])) for r in rows]


_ingest_state: dict = {}


async def _ingest_loop() -> None:
    last_retention = 0
    while True:
        try:
            global _ingest_state
            _ingest_state = await asyncio.to_thread(ingest_once, _redis(), _ingest_state)
        except Exception:
            logger.exception("rtt ingest cycle failed")
        if time.time() - last_retention > 86400:
            try:
                deleted = await asyncio.to_thread(retention_pass)
                if deleted:
                    logger.info("rtt retention deleted %d rows", deleted)
                last_retention = time.time()
            except Exception:
                logger.exception("rtt retention pass failed")
        await asyncio.sleep(RTT_INGEST_INTERVAL_SECONDS)


@app.on_event("startup")
async def _start_rtt_ingest() -> None:
    _db()  # ensure schema exists even when ingest is disabled
    if RTT_INGEST_ENABLED:
        asyncio.create_task(_ingest_loop())
        logger.info(
            "rtt ingest started: interval=%ds db=%s", RTT_INGEST_INTERVAL_SECONDS, RTT_DB_PATH
        )
    else:
        logger.info("rtt ingest disabled (RTT_INGEST_ENABLED=false)")


# ---------------------------------------------------------------------------
# Internal API (used by the dashboard frontend)
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse("templates/index.html")


@app.get("/api/snapshots")
def snapshots() -> dict:
    return {"timestamps": list_snapshots(), "export_dir": str(EXPORT_DIR)}


@app.get("/api/snapshot/{timestamp}")
def snapshot(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")
    return {"timestamp": timestamp, "count": len(rows), "nodes": [to_dict(r) for r in rows]}


@app.get("/api/snapshot/{timestamp}/stats")
def snapshot_stats(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")

    countries = Counter(r[9] for r in rows if r[9])
    user_agents = Counter(r[3] for r in rows if r[3])
    asns = Counter(f"{r[13]} {r[14]}" for r in rows if r[13])
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    heights_sorted = sorted(heights)
    median_height = heights_sorted[len(heights_sorted) // 2] if heights_sorted else None

    countries_iso3 = []
    for cc, count in countries.items():
        iso3 = iso2_to_iso3(cc)
        if iso3:
            countries_iso3.append([iso3, count])

    medians_now = list(medians_in_window().values())
    median_latency_ms = int(statistics.median(medians_now)) if medians_now else None

    return {
        "timestamp": timestamp,
        "total": len(rows),
        "countries_total": len(countries),
        "asns_total": len(asns),
        "user_agents_total": len(user_agents),
        "median_height": median_height,
        "median_latency_ms": median_latency_ms,
        "top_countries": countries.most_common(15),
        "top_user_agents": user_agents.most_common(15),
        "top_asns": asns.most_common(15),
        "countries_iso3": countries_iso3,
        "height_histogram": dict(Counter(heights).most_common(10)),
    }


@app.get("/api/latest")
def latest() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    return snapshot(snaps[-1])


@app.get("/api/latest/stats")
def latest_stats() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    return snapshot_stats(snaps[-1])


# ---------------------------------------------------------------------------
# Public API v1 (bitnodes.io-compatible schema)
# ---------------------------------------------------------------------------

V1_NOTE = "bitnodes.io-compatible schema."


@app.get("/api/v1/snapshots/", tags=["v1"], summary="List snapshots (paginated, newest first)")
def v1_snapshots(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
) -> dict:
    snaps = sorted(list_snapshots(), reverse=True)
    pag = paginate(snaps, page, limit, "/api/v1/snapshots/")
    results = []
    for ts in pag["page_items"]:
        try:
            meta = snapshot_meta(ts)
        except FileNotFoundError:
            continue
        results.append({
            "url": f"/api/v1/snapshots/{ts}/",
            **meta,
        })
    return {
        "count": pag["count"],
        "next": pag["next"],
        "previous": pag["previous"],
        "results": results,
    }


def _v1_snapshot_payload(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="snapshot not found")
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    medians = medians_in_window()
    nodes: dict[str, list] = {}
    for r in rows:
        # FIELDS: [address, port, proto, ua, timestamp, services, height, ...]
        addr, port, proto, ua, ts, _services, height = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        nodes[f"{addr}:{port}"] = [proto, ua, ts, medians.get((addr, port)), height]
    return {
        "timestamp": timestamp,
        "total_nodes": len(rows),
        "latest_height": max(heights) if heights else 0,
        "nodes": nodes,
    }


@app.get("/api/v1/snapshots/latest/", tags=["v1"], summary="Latest snapshot (full node dump)")
def v1_snapshot_latest() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    return _v1_snapshot_payload(snaps[-1])


@app.get("/api/v1/snapshots/{timestamp}/", tags=["v1"], summary="Specific snapshot (full node dump)")
def v1_snapshot(timestamp: int) -> dict:
    return _v1_snapshot_payload(timestamp)


@app.get("/api/v1/addresses/", tags=["v1"], summary="All addresses ever observed")
def v1_addresses(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=1000),
) -> dict:
    addrs = sorted(known_addresses_set())
    pag = paginate(addrs, page, limit, "/api/v1/addresses/")
    return {
        "count": pag["count"],
        "next": pag["next"],
        "previous": pag["previous"],
        "results": [{"address": a, "port": p} for a, p in pag["page_items"]],
    }


@app.get("/api/v1/nodes/{node_id}/", tags=["v1"], summary="Current status of a node")
def v1_node(node_id: str) -> dict:
    try:
        addr, port = parse_node_id(node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid node id: {e}")

    key = f"{addr}:{port}"
    idx = opendata_index()
    item = idx.get(key)
    if item is not None:
        data, _score = item
        # data layout (from ping.py opendata zset):
        #   [addr, port, protocol_version, user_agent, last_seen, services]
        proto = data[2] if len(data) > 2 else None
        ua = data[3] if len(data) > 3 else None
        last_seen = int(data[4]) if len(data) > 4 else None
        services = data[5] if len(data) > 5 else None
        height = None
        if services is not None:
            try:
                raw = _redis().get(f"height:{addr}-{port}-{services}")
                if raw is not None:
                    height = int(raw)
            except (redis.RedisError, ValueError):
                pass
        return {
            "address": addr,
            "status": "UP",
            "data": [proto, ua, last_seen, median_rtt_for(addr, port), height],
        }

    if (addr, port) in known_addresses_set():
        return {
            "address": addr,
            "status": "DOWN",
            "data": [None, None, None, median_rtt_for(addr, port), None],
        }

    raise HTTPException(status_code=404, detail="node not found")


# ---------------------------------------------------------------------------
# v1 latency / leaderboard / rankings / groups
# ---------------------------------------------------------------------------

def _latest_snapshot_rows() -> list[list]:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail="no snapshots available yet")
    try:
        return load_snapshot(snaps[-1])
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="latest snapshot missing on disk")


@app.get("/api/v1/nodes/{node_id}/latency/", tags=["v1"], summary="RTT time series for a node")
def v1_node_latency(
    node_id: str,
    hours: int = Query(24, ge=1, le=168),
) -> dict:
    try:
        addr, port = parse_node_id(node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid node id: {e}")

    known = (addr, port) in known_addresses_set()
    if not known:
        row = _db().execute(
            "SELECT 1 FROM rtt_samples WHERE address=? AND port=? LIMIT 1",
            (addr, port),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="node not found")

    return {"address": addr, "port": port, "latency": samples_for(addr, port, hours)}


@app.get("/api/v1/leaderboard/", tags=["v1"], summary="Fastest nodes by median RTT")
def v1_leaderboard(
    country: str | None = Query(None, description="ISO-2 country code filter"),
    asn: str | None = Query(None, description="ASN filter, e.g. 'AS13335'"),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    results: list[dict] = []
    for r in rows:
        addr, port = r[0], r[1]
        latency = medians.get((addr, port))
        if latency is None:
            continue
        node_country = r[9]
        node_asn = r[13]
        if country and node_country != country:
            continue
        if asn and node_asn != asn:
            continue
        results.append({
            "address": addr,
            "port": port,
            "country": node_country,
            "asn": node_asn,
            "asn_name": r[14],
            "user_agent": r[3],
            "latency_ms": latency,
        })
    results.sort(key=lambda x: x["latency_ms"])
    results = results[:limit]
    return {"count": len(results), "results": results}


def _group_ranking(rows: list[list], key_fn, medians: dict) -> list[dict]:
    """Group snapshot rows by key_fn(row) → bucket label, return list of buckets."""
    buckets: dict = defaultdict(list)
    for r in rows:
        label = key_fn(r)
        if label is None or label == "":
            continue
        latency = medians.get((r[0], r[1]))
        buckets[label].append(latency)
    out: list[dict] = []
    for label, latencies in buckets.items():
        present = [v for v in latencies if v is not None]
        median_val = int(statistics.median(present)) if present else None
        out.append({"label": label, "total_nodes": len(latencies), "median_rtt_ms": median_val})
    out.sort(key=lambda x: x["total_nodes"], reverse=True)
    return out


@app.get("/api/v1/rankings/countries/", tags=["v1"], summary="Per-country aggregate")
def v1_rankings_countries() -> dict:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    grouped = _group_ranking(rows, lambda r: r[9], medians)
    results = [
        {
            "country": g["label"],
            "country_iso3": iso2_to_iso3(g["label"]),
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]
    return {"count": len(results), "results": results}


@app.get("/api/v1/rankings/asns/", tags=["v1"], summary="Per-ASN aggregate")
def v1_rankings_asns() -> dict:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    asn_names: dict[str, str] = {}
    for r in rows:
        if r[13] and r[13] not in asn_names:
            asn_names[r[13]] = r[14] or ""
    grouped = _group_ranking(rows, lambda r: r[13], medians)
    results = [
        {
            "asn": g["label"],
            "asn_name": asn_names.get(g["label"], ""),
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]
    return {"count": len(results), "results": results}


@app.get("/api/v1/rankings/user-agents/", tags=["v1"], summary="Per-user-agent aggregate")
def v1_rankings_user_agents() -> dict:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    grouped = _group_ranking(rows, lambda r: r[3], medians)
    results = [
        {
            "user_agent": g["label"],
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]
    return {"count": len(results), "results": results}


@app.get("/api/v1/groups/by-ip/", tags=["v1"], summary="IPs hosting more than one node")
def v1_groups_by_ip() -> dict:
    rows = _latest_snapshot_rows()
    by_addr: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_addr[r[0]].append(r[1])
    results = [
        {"address": a, "total_nodes": len(ports), "ports": sorted(ports)}
        for a, ports in by_addr.items()
        if len(ports) >= 2
    ]
    results.sort(key=lambda x: x["total_nodes"], reverse=True)
    return {"count": len(results), "results": results}


@app.get("/api/v1/groups/by-ip/{address}/", tags=["v1"], summary="Nodes sharing one IP")
def v1_group_by_ip_detail(address: str) -> dict:
    rows = _latest_snapshot_rows()
    matching = [r for r in rows if r[0] == address]
    if not matching:
        raise HTTPException(status_code=404, detail="address not found in latest snapshot")
    medians = medians_in_window()
    matching.sort(key=lambda r: r[1])
    nodes = [
        {
            "port": r[1],
            "user_agent": r[3],
            "height": r[6],
            "country": r[9],
            "asn": r[13],
            "latency_ms": medians.get((r[0], r[1])),
        }
        for r in matching
    ]
    return {"address": address, "total_nodes": len(nodes), "nodes": nodes}
