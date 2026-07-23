"""Per-block propagation stats from the crawler's `binv:*` Redis zsets.

The crawler's cache_inv processes record, for every block hash, which node
announced the inv and at what millisecond (zset member = `addr-port`,
score = ms timestamp). Those zsets rotate out of Redis, so a timer-driven
collector persists per-block JSON documents (and a precomputed aggregate)
before the data disappears; the APIs serve the files, never Redis.

Definition: all times are relative to the *first announcement our crawler
observed* for that block — this measures our crawler's view of relative
propagation across network classes, not absolute network latency.
"""

import json
import logging
import re
import time
from pathlib import Path

from queries.config import PROPAGATION_DIR
from queries.redis_client import get_redis
from queries.snapshots import list_snapshots, snapshot_meta
from queries.util import classify_network as _classify

DEFINITION = (
    "Times are milliseconds since the first announcement observed by this "
    "crawler for each block — relative propagation as seen from one vantage "
    "point, not absolute network latency."
)

NETWORKS = ("ipv4", "ipv6", "tor", "i2p")
HOT_MS = 30 * 60 * 1000
RETENTION_DAYS = 30
ECDF_POINTS = 50
RECENT_BLOCKS = 100
AGGREGATE_FILE = "aggregate.json"

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _percentile(sorted_values: list, q: float):
    if not sorted_values:
        return None
    idx = (len(sorted_values) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = idx - lo
    return round(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _ecdf(sorted_values: list, points: int = ECDF_POINTS) -> list:
    """Downsampled ECDF as [t_ms, cumulative_fraction] pairs."""
    n = len(sorted_values)
    if n == 0:
        return []
    count = min(n, points)
    out = []
    for i in range(count):
        idx = round(i * (n - 1) / (count - 1)) if count > 1 else n - 1
        out.append([round(sorted_values[idx]), round((idx + 1) / n, 4)])
    return out


def _height_estimate(first_ms: float):
    """latest_height of the first snapshot at/after the block's first sighting.

    Nodes report their height in the version handshake, so the first snapshot
    exported after the block appeared carries a tip that includes it. An
    estimate (±1 when several blocks land between snapshots), labeled as such.
    """
    first_s = first_ms / 1000
    later = [ts for ts in list_snapshots() if ts >= first_s]
    if not later:
        return None
    try:
        return snapshot_meta(min(later))["latest_height"]
    except Exception:
        # Cosmetic, explicitly estimated field — never worth failing a block.
        return None


def _block_doc(block_hash: str, items: list) -> dict:
    """items: [(member_bytes, score_ms)] from the zset."""
    first = min(score for _m, score in items)
    rel_by_net: dict[str, list] = {n: [] for n in NETWORKS}
    for member, score in items:
        addr = member.decode(errors="replace").rsplit("-", 1)[0]
        rel_by_net[_classify(addr)].append(score - first)

    networks = {}
    for net, rels in rel_by_net.items():
        rels.sort()
        networks[net] = {
            "count": len(rels),
            "p50": _percentile(rels, 0.5),
            "p90": _percentile(rels, 0.9),
            "ecdf": _ecdf(rels),
        }
    return {
        "hash": block_hash,
        "first_ms": round(first),
        "count": len(items),
        "height_estimate": _height_estimate(first),
        "networks": networks,
    }


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def collect_propagation(redis_conn=None, root: Path = None, now_ms: float = None) -> dict:
    """Persist completed blocks, prune old files, rebuild the aggregate.

    Returns a summary {collected, skipped_hot, failed, pruned}. Read-only
    against Redis; a failure on one block (WRONGTYPE key, corrupt snapshot
    behind the height estimate, write error) is logged and skips only that
    block — the sweep, the prune, and the aggregate always run.
    """
    root = root or PROPAGATION_DIR
    root.mkdir(parents=True, exist_ok=True)
    r = redis_conn or get_redis()
    now_ms = now_ms if now_ms is not None else time.time() * 1000

    existing = {p.stem for p in root.glob("*.json") if _HASH_RE.match(p.stem)}
    collected = skipped_hot = failed = 0
    for key in r.scan_iter(match=b"binv:*", count=100):
        try:
            block_hash = key.decode().split(":", 1)[1]
            if not _HASH_RE.match(block_hash) or block_hash in existing:
                continue
            items = r.zrange(key, 0, -1, withscores=True)
            if not items:
                continue
            first = min(score for _m, score in items)
            if now_ms - first < HOT_MS:
                skipped_hot += 1
                continue
            _write_json(root / f"{block_hash}.json", _block_doc(block_hash, items))
            collected += 1
        except Exception:
            logging.exception("propagation: failed on %r, skipping block", key)
            failed += 1

    pruned = _prune(root, now_ms)
    _write_aggregate(root)
    return {"collected": collected, "skipped_hot": skipped_hot,
            "failed": failed, "pruned": pruned}


def _prune(root: Path, now_ms: float) -> int:
    cutoff = now_ms - RETENTION_DAYS * 86400 * 1000
    pruned = 0
    for p in root.glob("*.json"):
        if not _HASH_RE.match(p.stem):
            continue
        try:
            doc = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            p.unlink(missing_ok=True)
            pruned += 1
            continue
        if doc.get("first_ms", 0) < cutoff:
            p.unlink(missing_ok=True)
            pruned += 1
    return pruned


# Fraction grid for the aggregate median curve: 2% steps up to 100%.
FRACTION_GRID = [round(i / 50, 2) for i in range(1, 51)]


def _t_at_fraction(ecdf_points: list, fraction: float):
    """Time by which a block's ECDF reaches `fraction` (step function)."""
    for t, frac in ecdf_points:
        if frac >= fraction:
            return t
    return ecdf_points[-1][0]


def _median_ecdf(curves: list[list]) -> list:
    """Median-across-blocks curve: for each grid fraction, the median time
    at which blocks reached it. Equal weight per block, so a 5-announcer
    block cannot skew the curve against a 5,000-announcer one."""
    if not curves:
        return []
    points = []
    for fraction in FRACTION_GRID:
        ts = sorted(_t_at_fraction(c, fraction) for c in curves)
        points.append([ts[len(ts) // 2], fraction])
    return points


def _write_aggregate(root: Path) -> None:
    """Median ECDF + recent-block table over the newest RECENT_BLOCKS files."""
    docs = []
    for p in root.glob("*.json"):
        if not _HASH_RE.match(p.stem):
            continue
        try:
            docs.append(json.loads(p.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    docs.sort(key=lambda d: d.get("first_ms", 0), reverse=True)
    docs = docs[:RECENT_BLOCKS]

    curves: dict[str, list] = {n: [] for n in NETWORKS}
    blocks = []
    for doc in docs:
        nets = doc.get("networks", {})
        for net in NETWORKS:
            ecdf_points = nets.get(net, {}).get("ecdf") or []
            if ecdf_points:
                curves[net].append(ecdf_points)
        blocks.append(
            {
                "hash": doc["hash"],
                "first_ms": doc["first_ms"],
                "count": doc["count"],
                "height_estimate": doc.get("height_estimate"),
                "networks": {
                    net: {
                        "count": nets.get(net, {}).get("count", 0),
                        "p50": nets.get(net, {}).get("p50"),
                        "p90": nets.get(net, {}).get("p90"),
                    }
                    for net in NETWORKS
                },
            }
        )

    ecdf = {net: _median_ecdf(curves[net]) for net in NETWORKS}
    _write_json(
        root / AGGREGATE_FILE,
        {
            "generated_at": int(time.time()),
            "definition": DEFINITION,
            "blocks": blocks,
            "ecdf": ecdf,
        },
    )


def _empty_aggregate() -> dict:
    return {"generated_at": None, "definition": DEFINITION, "blocks": [], "ecdf": {}}


def load_propagation(root: Path = None) -> dict:
    """The precomputed aggregate. Empty result if absent or wrong-shaped."""
    root = root or PROPAGATION_DIR
    path = root / AGGREGATE_FILE
    if not path.exists():
        return _empty_aggregate()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return _empty_aggregate()
    if (not isinstance(data, dict) or not isinstance(data.get("blocks"), list)
            or not isinstance(data.get("ecdf"), dict)):
        return _empty_aggregate()
    return data


def load_block(block_hash: str, root: Path = None) -> dict | None:
    """One collected block document, or None. Hash is validated (hex64)."""
    if not _HASH_RE.match(block_hash or ""):
        return None
    root = root or PROPAGATION_DIR
    path = root / f"{block_hash}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
