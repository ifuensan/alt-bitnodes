import json
import os
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pycountry
import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


EXPORT_DIR = Path(
    os.environ.get(
        "BITNODES_EXPORT_DIR",
        "/mnt/datos/home_data/Work/myprojects/research/bitnodes/data/export/f9beb4d9",
    )
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
OPENDATA_TTL_SECONDS = 10

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

    return {
        "timestamp": timestamp,
        "total": len(rows),
        "countries_total": len(countries),
        "asns_total": len(asns),
        "user_agents_total": len(user_agents),
        "median_height": median_height,
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

V1_NOTE = (
    "bitnodes.io-compatible schema. Note: latency_ms is currently null pending "
    "RTT persistence (planned phase 2)."
)


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
    nodes: dict[str, list] = {}
    for r in rows:
        # FIELDS: [address, port, proto, ua, timestamp, services, height, ...]
        addr, port, proto, ua, ts, _services, height = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        nodes[f"{addr}:{port}"] = [proto, ua, ts, None, height]
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
            "data": [proto, ua, last_seen, None, height],
        }

    if (addr, port) in known_addresses_set():
        return {
            "address": addr,
            "status": "DOWN",
            "data": [None, None, None, None, None],
        }

    raise HTTPException(status_code=404, detail="node not found")
