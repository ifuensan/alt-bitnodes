"""Per-node status queries: opendata index, node lookups."""

import json
import time

import redis

from queries.config import OPENDATA_TTL_SECONDS
from queries.redis_client import get_redis
from queries.rtt import median_rtt_for
from queries.snapshots import known_addresses_set


def parse_node_id(node_id: str) -> tuple[str, int]:
    if "-" not in node_id:
        raise ValueError("missing '-'")
    addr, _, port_s = node_id.rpartition("-")
    if not port_s.isdigit():
        raise ValueError("port must be numeric")
    if addr.startswith("[") and addr.endswith("]"):
        addr = addr[1:-1]
    return addr, int(port_s)


_opendata_cache: dict = {"ts": 0.0, "index": {}}


def opendata_index() -> dict:
    """Map "<addr>:<port>" -> (raw_data_list, score). Cached briefly."""
    now = time.time()
    if now - _opendata_cache["ts"] < OPENDATA_TTL_SECONDS and _opendata_cache["index"]:
        return _opendata_cache["index"]
    try:
        items = get_redis().zrange("opendata", 0, -1, withscores=True)
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


def _node_height(addr: str, port: int, services) -> int | None:
    if services is None:
        return None
    try:
        raw = get_redis().get(f"height:{addr}-{port}-{services}")
        return int(raw) if raw is not None else None
    except (redis.RedisError, ValueError):
        return None


def _node_up_payload(item, addr: str, port: int) -> dict:
    # opendata zset entry: [addr, port, protocol_version, user_agent, last_seen, services]
    data, _score = item
    proto = data[2] if len(data) > 2 else None
    ua = data[3] if len(data) > 3 else None
    last_seen = int(data[4]) if len(data) > 4 else None
    services = data[5] if len(data) > 5 else None
    return {
        "address": addr,
        "status": "UP",
        "data": [proto, ua, last_seen, median_rtt_for(addr, port), _node_height(addr, port, services)],
    }


def node_status(addr: str, port: int) -> dict | None:
    """Current status for a node. Returns None if unknown to the system."""
    item = opendata_index().get(f"{addr}:{port}")
    if item is not None:
        return _node_up_payload(item, addr, port)

    if (addr, port) in known_addresses_set():
        return {
            "address": addr,
            "status": "DOWN",
            "data": [None, None, None, median_rtt_for(addr, port), None],
        }
    return None
