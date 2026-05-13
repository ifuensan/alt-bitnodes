import asyncio
import logging
import time
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from queries import (
    EXPORT_DIR,
    NoSnapshotsError,
    SnapshotMissingError,
    group_by_ip_detail,
    groups_by_ip,
    ingest_once,
    known_addresses_set,
    leaderboard,
    list_snapshots,
    load_snapshot,
    median_rtt_for,
    medians_in_window,
    node_status,
    parse_node_id,
    rankings_by_asn,
    rankings_by_country,
    rankings_by_user_agent,
    retention_pass,
    rtt_db,
    samples_for,
    snapshot_meta,
    snapshot_stats,
    to_dict,
)
from queries.redis_client import get_redis
from queries.rtt import has_samples

import os

logger = logging.getLogger("alt-bitnodes")

RTT_INGEST_INTERVAL_SECONDS = int(os.environ.get("RTT_INGEST_INTERVAL_SECONDS", "30"))
RTT_INGEST_ENABLED = os.environ.get("RTT_INGEST_ENABLED", "true").lower() in ("1", "true", "yes", "on")

ERR_SNAPSHOT_NOT_FOUND = "snapshot not found"
ERR_NO_SNAPSHOTS = "no snapshots available yet"

_rtt_ingest_task: asyncio.Task | None = None

app = FastAPI(title="alt-bitnodes")
app.mount("/static", StaticFiles(directory="static"), name="static")


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
# RTT ingest background loop (binds queries.rtt.ingest_once to FastAPI lifecycle)
# ---------------------------------------------------------------------------

_ingest_state: dict = {}


async def _ingest_loop() -> None:
    last_retention = 0
    while True:
        try:
            global _ingest_state
            _ingest_state = await asyncio.to_thread(ingest_once, get_redis(), _ingest_state)
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
    rtt_db()  # ensure schema exists even when ingest is disabled
    if RTT_INGEST_ENABLED:
        global _rtt_ingest_task
        _rtt_ingest_task = asyncio.create_task(_ingest_loop())
        logger.info("rtt ingest started: interval=%ds", RTT_INGEST_INTERVAL_SECONDS)
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


@app.get("/api/snapshot/{timestamp}", responses={404: {"description": ERR_SNAPSHOT_NOT_FOUND}})
def snapshot(timestamp: int) -> dict:
    try:
        rows = load_snapshot(timestamp)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=ERR_SNAPSHOT_NOT_FOUND)
    return {"timestamp": timestamp, "count": len(rows), "nodes": [to_dict(r) for r in rows]}


@app.get("/api/snapshot/{timestamp}/stats", responses={404: {"description": ERR_SNAPSHOT_NOT_FOUND}})
def snapshot_stats_endpoint(timestamp: int) -> dict:
    try:
        medians_now = list(medians_in_window().values())
        return snapshot_stats(timestamp, medians_now=medians_now)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=ERR_SNAPSHOT_NOT_FOUND)


@app.get("/api/latest", responses={404: {"description": ERR_NO_SNAPSHOTS}})
def latest() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail=ERR_NO_SNAPSHOTS)
    return snapshot(snaps[-1])


@app.get("/api/latest/stats", responses={404: {"description": ERR_NO_SNAPSHOTS}})
def latest_stats() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail=ERR_NO_SNAPSHOTS)
    return snapshot_stats_endpoint(snaps[-1])


# ---------------------------------------------------------------------------
# Public API v1 (bitnodes.io-compatible schema)
# ---------------------------------------------------------------------------

@app.get("/api/v1/snapshots/", tags=["v1"], summary="List snapshots (paginated, newest first)")
def v1_snapshots(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> dict:
    snaps = sorted(list_snapshots(), reverse=True)
    pag = paginate(snaps, page, limit, "/api/v1/snapshots/")
    results = []
    for ts in pag["page_items"]:
        try:
            meta = snapshot_meta(ts)
        except FileNotFoundError:
            continue
        results.append({"url": f"/api/v1/snapshots/{ts}/", **meta})
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
        raise HTTPException(status_code=404, detail=ERR_SNAPSHOT_NOT_FOUND)
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    medians = medians_in_window()
    nodes: dict[str, list] = {}
    for r in rows:
        addr, port, proto, ua, ts, _services, height = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        nodes[f"{addr}:{port}"] = [proto, ua, ts, medians.get((addr, port)), height]
    return {
        "timestamp": timestamp,
        "total_nodes": len(rows),
        "latest_height": max(heights) if heights else 0,
        "nodes": nodes,
    }


@app.get("/api/v1/snapshots/latest/", tags=["v1"], summary="Latest snapshot (full node dump)",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_snapshot_latest() -> dict:
    snaps = list_snapshots()
    if not snaps:
        raise HTTPException(status_code=404, detail=ERR_NO_SNAPSHOTS)
    return _v1_snapshot_payload(snaps[-1])


@app.get("/api/v1/snapshots/{timestamp}/", tags=["v1"], summary="Specific snapshot (full node dump)",
         responses={404: {"description": ERR_SNAPSHOT_NOT_FOUND}})
def v1_snapshot(timestamp: int) -> dict:
    return _v1_snapshot_payload(timestamp)


@app.get("/api/v1/addresses/", tags=["v1"], summary="All addresses ever observed")
def v1_addresses(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=1000)] = 10,
) -> dict:
    addrs = sorted(known_addresses_set())
    pag = paginate(addrs, page, limit, "/api/v1/addresses/")
    return {
        "count": pag["count"],
        "next": pag["next"],
        "previous": pag["previous"],
        "results": [{"address": a, "port": p} for a, p in pag["page_items"]],
    }


@app.get("/api/v1/nodes/{node_id}/", tags=["v1"], summary="Current status of a node",
         responses={400: {"description": "invalid node id"}, 404: {"description": "node not found"}})
def v1_node(node_id: str) -> dict:
    try:
        addr, port = parse_node_id(node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid node id: {e}")
    status = node_status(addr, port)
    if status is None:
        raise HTTPException(status_code=404, detail="node not found")
    return status


@app.get("/api/v1/nodes/{node_id}/rtt/", tags=["v1"], summary="RTT time series for a node",
         responses={400: {"description": "invalid node id"}, 404: {"description": "node not found"}})
def v1_node_rtt(
    node_id: str,
    hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict:
    try:
        addr, port = parse_node_id(node_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"invalid node id: {e}")

    if (addr, port) not in known_addresses_set() and not has_samples(addr, port):
        raise HTTPException(status_code=404, detail="node not found")

    return {"address": addr, "port": port, "latency": samples_for(addr, port, hours)}


def _no_snapshots_404():
    return HTTPException(status_code=404, detail=ERR_NO_SNAPSHOTS)


def _missing_snapshot_404():
    return HTTPException(status_code=404, detail="latest snapshot missing on disk")


@app.get("/api/v1/nodes/leaderboard/", tags=["v1"], summary="Fastest nodes by median RTT",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_leaderboard(
    country: Annotated[str | None, Query(description="ISO-2 country code filter")] = None,
    asn: Annotated[str | None, Query(description="ASN filter, e.g. 'AS13335'")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    try:
        results = leaderboard(country=country, asn=asn, limit=limit)
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    return {"count": len(results), "results": results}


@app.get("/api/v1/rankings/countries/", tags=["v1"], summary="Per-country aggregate",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_rankings_countries() -> dict:
    try:
        results = rankings_by_country()
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    return {"count": len(results), "results": results}


@app.get("/api/v1/rankings/asns/", tags=["v1"], summary="Per-ASN aggregate",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_rankings_asns() -> dict:
    try:
        results = rankings_by_asn()
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    return {"count": len(results), "results": results}


@app.get("/api/v1/rankings/user-agents/", tags=["v1"], summary="Per-user-agent aggregate",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_rankings_user_agents() -> dict:
    try:
        results = rankings_by_user_agent()
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    return {"count": len(results), "results": results}


@app.get("/api/v1/groups/by-ip/", tags=["v1"], summary="IPs hosting more than one node",
         responses={404: {"description": ERR_NO_SNAPSHOTS}})
def v1_groups_by_ip() -> dict:
    try:
        results = groups_by_ip()
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    return {"count": len(results), "results": results}


@app.get("/api/v1/groups/by-ip/{address}/", tags=["v1"], summary="Nodes sharing one IP",
         responses={404: {"description": "address not found in latest snapshot"}})
def v1_group_by_ip_detail(address: str) -> dict:
    try:
        result = group_by_ip_detail(address)
    except NoSnapshotsError:
        raise _no_snapshots_404()
    except SnapshotMissingError:
        raise _missing_snapshot_404()
    if result is None:
        raise HTTPException(status_code=404, detail="address not found in latest snapshot")
    return result
