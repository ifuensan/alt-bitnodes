"""The BEST view: a frozen union of every node seen up to a fixed date.

The rolling windows only reach back as far as the raw exports (90 days) and
say nothing about the era when the crawler also reached Tor and I2P. This
builds, once, the union of every snapshot on record up to a cutoff day — raw
exports still on disk plus the archived photos — and freezes it next to the
window caches. No timer rewrites it; `best_union.py` refuses to overwrite it
without --force, so it survives the raw-export pruning.
"""

import datetime as dt
import json
from pathlib import Path

import pyarrow.parquet as pq

from queries.archives import PINNED_TIMESTAMPS, photo_path, scan_archive
from queries.config import ARCHIVE_DIR, BEST_NODES_FILE, BEST_STATS_FILE, FIELDS
from queries.snapshots import list_snapshots, load_snapshot
from queries.window_stats import (
    WindowMissingError,
    _read_window_nodes,
    _window_entry,
    _write_atomic,
)

DAY_SECONDS = 86400


def _until(cutoff: dt.date) -> int:
    """Last second of the cutoff day (UTC)."""
    end = dt.datetime.combine(cutoff + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    return int(end.timestamp()) - 1


def _photo_rows(ts: int, tier: str, root: Path) -> list[list]:
    table = pq.read_table(photo_path(tier, ts, "parquet", root))
    return [[rec[f] for f in FIELDS] for rec in table.to_pylist()]


def compute_best_union(cutoff: dt.date, archive_root: Path = None, now: int = None) -> dict:
    """Union of (address, port) over every snapshot with ts <= end of `cutoff`.

    Returns the stats payload plus, under ``"_nodes"``, the latest row of
    every node with its last-seen timestamp.
    """
    root = archive_root or ARCHIVE_DIR
    until = _until(cutoff)
    raw = {ts for ts in list_snapshots() if ts <= until}
    photos = {ts: tier for ts, tier in scan_archive(root).items()
              if ts <= until and ts not in raw}

    latest: dict[tuple, tuple[int, list]] = {}
    used = []
    for ts in sorted(raw | photos.keys()):
        try:
            rows = load_snapshot(ts) if ts in raw else _photo_rows(ts, photos[ts], root)
        except (FileNotFoundError, OSError, ValueError):
            continue
        used.append(ts)
        for r in rows:
            latest[(r[0], r[1])] = (ts, r)  # ascending ts: later sighting wins

    rows = [row for _, row in latest.values()]
    entry = _window_entry(0, len(used), used[0] if used else None, rows)
    entry.pop("days")
    return {
        "as_of": cutoff.isoformat(),
        "until": used[-1] if used else None,
        "built_at": now if now is not None else int(dt.datetime.now(dt.timezone.utc).timestamp()),
        "sources": {"raw": len(raw), "photos": len(photos)},
        "pinned": sorted(PINNED_TIMESTAMPS),
        **entry,
        "_nodes": [[*row, ts] for ts, row in latest.values()],
    }


def write_best_union(cutoff: dt.date, stats_path: Path = None, nodes_path: Path = None,
                     archive_root: Path = None, now: int = None) -> dict:
    stats_path = stats_path or BEST_STATS_FILE
    nodes_path = nodes_path or BEST_NODES_FILE
    data = compute_best_union(cutoff, archive_root, now)
    nodes = data.pop("_nodes")
    _write_atomic(nodes_path, {"as_of": data["as_of"], "fields": [*FIELDS, "last_seen"],
                               "nodes": nodes})
    _write_atomic(stats_path, data)
    return json.loads(json.dumps(data))


def best_view_stats(path: Path = None) -> dict:
    """The frozen union flattened to the `snapshot_stats` shape (plus meta).
    Raises WindowMissingError if it has not been built."""
    path = path or BEST_STATS_FILE
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise WindowMissingError("no frozen best union built yet")
    if not data.get("snapshots") or "distribution" not in data:
        raise WindowMissingError("no frozen best union built yet")
    meta = {k: v for k, v in data.items() if k != "distribution"}
    return {**meta, **data["distribution"]}


def load_best_nodes(path: Path = None) -> dict:
    path = path or BEST_NODES_FILE
    try:
        data = _read_window_nodes(str(path), path.stat().st_mtime_ns)
    except (OSError, json.JSONDecodeError):
        raise WindowMissingError("no frozen best union built yet")
    fields = data.get("fields") or [*FIELDS, "last_seen"]
    nodes = [dict(zip(fields, row)) for row in data.get("nodes", [])]
    nodes.sort(key=lambda n: n["last_seen"], reverse=True)
    return {"as_of": data.get("as_of"), "count": len(nodes), "nodes": nodes}
