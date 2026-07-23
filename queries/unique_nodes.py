"""Weighted unique-node estimate from advertised addr-gossip composition.

A node reachable over several network types contributes one address per
type to the reachable count. Following the 1/N method (as documented by
21.ninja): infer the network types a peer supports from the composition of
the addresses it advertises via `addr` gossip (the crawler's `peer:*` Redis
keys), and weight each reachable address 1/N so a dual-stack+Tor node sums
to 1.0 instead of 3. Known limitation: multiple addresses of the same
network type cannot be deduplicated, and sparse gossip biases N low — the
composition histogram published alongside makes that visible.

Computed by the collector timer (a snapshot-wide sweep of `peer:*` GETs is
not request-path work) and persisted to JSON; the APIs serve the cache.
"""

import json
import time
from pathlib import Path

from queries.config import UNIQUE_STATS_FILE
from queries.redis_client import get_redis
from queries.snapshots import list_snapshots, load_snapshot
from queries.util import classify_network as _classify

METHOD = (
    "Each reachable address is weighted 1/N, where N is the number of "
    "distinct network types (ipv4, ipv6, tor, i2p) present in the addresses "
    "that peer advertises via addr gossip (N=1 when no gossip is known). "
    "Limitation: multiple addresses of the same network type cannot be "
    "deduplicated, so the estimate is an upper bound on that axis."
)

PIPELINE_CHUNK = 500


def _band(net: str) -> str:
    return "clearnet" if net in ("ipv4", "ipv6") else net


def _gossip_types(raw: bytes | None) -> int:
    """Distinct network types in one peer's advertised gossip (0 if none)."""
    if not raw:
        return 0
    try:
        entries = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(entries, list):
        # Valid JSON but not gossip (e.g. b"null") — treat as no data.
        return 0
    types = set()
    for e in entries:
        if isinstance(e, (list, tuple)) and e and isinstance(e[0], str):
            types.add(_classify(e[0]))
    return len(types)


def compute_unique_estimate(redis_conn=None, timestamp: int = None) -> dict:
    """1/N-weighted estimate over the latest (or given) snapshot."""
    snaps = list_snapshots()
    ts = timestamp if timestamp is not None else (snaps[-1] if snaps else None)
    if ts is None:
        return _empty_estimate()
    try:
        rows = load_snapshot(ts)
    except (FileNotFoundError, ValueError):
        # ValueError covers JSONDecodeError: degrade, don't fail the section.
        return _empty_estimate()

    r = redis_conn or get_redis()
    keys = [f"peer:{row[0]}-{row[1]}" for row in rows]
    raws: list[bytes | None] = []
    for start in range(0, len(keys), PIPELINE_CHUNK):
        chunk = keys[start:start + PIPELINE_CHUNK]
        pipe = r.pipeline(transaction=False)
        for k in chunk:
            pipe.get(k)
        raws.extend(pipe.execute())

    total = 0.0
    bands = {"clearnet": 0.0, "tor": 0.0, "i2p": 0.0}
    composition = {"n1": 0, "n2": 0, "n3plus": 0}
    for row, raw in zip(rows, raws):
        n = max(1, _gossip_types(raw))
        weight = 1.0 / n
        total += weight
        bands[_band(_classify(row[0]))] += weight
        if n == 1:
            composition["n1"] += 1
        elif n == 2:
            composition["n2"] += 1
        else:
            composition["n3plus"] += 1

    return {
        "generated_at": int(time.time()),
        "snapshot": ts,
        "reachable": len(rows),
        "estimate": round(total, 1),
        "clearnet": round(bands["clearnet"], 1),
        "tor": round(bands["tor"], 1),
        "i2p": round(bands["i2p"], 1),
        "composition": composition,
        "method": METHOD,
    }


def _empty_estimate() -> dict:
    return {
        "generated_at": None,
        "snapshot": None,
        "reachable": 0,
        "estimate": None,
        "clearnet": None,
        "tor": None,
        "i2p": None,
        "composition": {"n1": 0, "n2": 0, "n3plus": 0},
        "method": METHOD,
    }


def write_unique_estimate(path: Path = None, redis_conn=None) -> dict:
    path = path or UNIQUE_STATS_FILE
    data = compute_unique_estimate(redis_conn=redis_conn)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
    return data


def load_unique_estimate(path: Path = None) -> dict:
    """Read the cached estimate. Empty result if absent/unreadable."""
    path = path or UNIQUE_STATS_FILE
    if not path.exists():
        return _empty_estimate()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return _empty_estimate()
    if not isinstance(data, dict) or "estimate" not in data:
        return _empty_estimate()
    return data
