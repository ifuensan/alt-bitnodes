"""Rolling-window union of unique nodes per network type.

Trackers like bitnod.es count the union of unique nodes seen over a window
(8 days), not the simultaneously-reachable set a single snapshot holds. This
computes that union from the snapshots on disk. It is expensive (reads every
snapshot in the widest window), so it is precomputed by a timer and cached to
JSON; the API serves the cache via `load_window_stats`.

Two caches come out of one pass:

- `WINDOW_STATS_FILE` — per-window counts plus a `distribution` block in the
  same shape as `snapshot_stats` (top countries / user agents / ASNs, ISO-3
  choropleth data, median height), so the dashboard can draw the union view
  with the live view's renderers.
- `WINDOW_NODES_FILE` — every node of the widest window with its last-seen
  timestamp and the row it carried then. A node's window membership is "last
  seen on or after the cutoff", so narrower windows are filtered out of this
  one file at read time.
"""

import json
from functools import lru_cache
from pathlib import Path

from queries.config import EXPORT_DIR, FIELDS, WINDOW_NODES_FILE, WINDOW_STATS_FILE
from queries.snapshots import distribution_stats, list_snapshots, load_snapshot
from queries.util import classify_network as _classify

# 5 days matches the upstream crawler's max node-age (max_age up to 432000s),
# so it's the exact apples-to-apples window vs bitnodes-style trackers; 8 days
# matches bitnod.es's stated pruning; 1/3 bracket the recent-config figure;
# 24 shows how much of the 8-day population persists (raw exports are kept
# 90 days, so the data is on disk).
WINDOWS_DAYS = (1, 3, 5, 8, 24)
DAY_SECONDS = 86400
NETWORKS = ("ipv4", "ipv6", "tor", "i2p")


class WindowMissingError(LookupError):
    """No cached union exists for the requested window (cache absent or the
    window is not one of the configured ones)."""


def compute_window_stats(windows_days=WINDOWS_DAYS, now: int = None) -> dict:
    """Union of unique (address, port) per network over each window.

    Single pass over the snapshots, keeping the latest row seen per node. A
    node belongs to every window whose cutoff its last sighting satisfies,
    so one dict serves all windows (the widest is the superset). Returns the
    stats payload and, under ``"_nodes"``, the latest rows of the widest
    window — ``write_window_stats`` splits them into their own file.
    """
    snaps = list_snapshots()
    windows = sorted(windows_days)
    # generated_at = the snapshot the windows are anchored to (the latest, or
    # the explicit `now`), so consumers can detect staleness. In production the
    # timer calls this with now=None, so anchoring to snaps[-1] keeps the field
    # meaningful instead of the null it used to be.
    reference = now if now is not None else (snaps[-1] if snaps else None)
    result = {
        "generated_at": reference,
        "windows": [],
        "_nodes": [],
    }
    if not snaps:
        for d in windows:
            result["windows"].append(_empty_window(d))
        return result
    cutoffs = {d: reference - d * DAY_SECONDS for d in windows}
    counts = {d: 0 for d in windows}
    # (address, port) -> (last_seen, row) over the widest window.
    latest: dict[tuple, tuple[int, list]] = {}

    widest_cutoff = min(cutoffs.values())
    for ts in snaps:
        if ts < widest_cutoff:
            continue
        try:
            rows = load_snapshot(ts)
        except FileNotFoundError:
            continue
        for d in windows:
            if ts >= cutoffs[d]:
                counts[d] += 1
        for r in rows:
            key = (r[0], r[1])
            seen = latest.get(key)
            if seen is None or ts >= seen[0]:
                latest[key] = (ts, r)

    for d in windows:
        rows = [row for last_seen, row in latest.values() if last_seen >= cutoffs[d]]
        result["windows"].append(_window_entry(d, counts[d], cutoffs[d], rows))

    result["_nodes"] = [
        [*row, last_seen] for last_seen, row in latest.values()
    ]
    return result


def _window_entry(days: int, snapshots: int, since: int, rows: list) -> dict:
    """Counts per network plus the distribution for one window's rows."""
    per_net = dict.fromkeys(NETWORKS, 0)
    for r in rows:
        per_net[_classify(r[0])] += 1
    clearnet = per_net["ipv4"] + per_net["ipv6"]
    return {
        "days": days,
        "snapshots": snapshots,
        "since": since,
        "ipv4": per_net["ipv4"],
        "ipv6": per_net["ipv6"],
        "clearnet": clearnet,
        "tor": per_net["tor"],
        "i2p": per_net["i2p"],
        "total": clearnet + per_net["tor"] + per_net["i2p"],
        "distribution": distribution_stats(rows),
    }


def _empty_window(days: int) -> dict:
    """Entry for a window with no snapshots (fresh host, empty export dir)."""
    return {
        "days": days, "snapshots": 0, "since": None, "ipv4": 0, "ipv6": 0,
        "clearnet": 0, "tor": 0, "i2p": 0, "total": 0,
        "distribution": distribution_stats([]),
    }


def _write_atomic(path: Path, payload: dict) -> None:
    """Write JSON via a temp file + rename so readers never see a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(path)  # atomic


def write_window_stats(now: int = None, path: Path = None,
                       nodes_path: Path = None) -> dict:
    """Compute the union and write both caches (stats, widest-window nodes)."""
    path = path or WINDOW_STATS_FILE
    nodes_path = nodes_path or WINDOW_NODES_FILE
    data = compute_window_stats(now=now)
    nodes = data.pop("_nodes")
    widest = max(w["days"] for w in data["windows"]) if data["windows"] else None
    _write_atomic(nodes_path, {
        "generated_at": data["generated_at"],
        "days": widest,
        "fields": [*FIELDS, "last_seen"],
        "nodes": nodes,
    })
    _write_atomic(path, data)
    # Return what a reader will get back (Counter tuples become lists,
    # histogram keys become strings), so callers and tests see one shape.
    return json.loads(json.dumps(data))


def load_window_stats(path: Path = None) -> dict:
    """Read the cached windowed counts. Empty result if absent/unreadable."""
    path = path or WINDOW_STATS_FILE
    if not path.exists():
        return {"generated_at": None, "windows": []}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "windows": []}


def window_view_stats(days: int, path: Path = None) -> dict:
    """One window's entry flattened to the `snapshot_stats` shape (plus the
    window metadata) so the dashboard can render it with the same code.

    Raises WindowMissingError if the cache is absent, empty, or has no such
    window.
    """
    data = load_window_stats(path)
    entry = next((w for w in data.get("windows", []) if w.get("days") == days), None)
    # A cache written by the pre-distribution job (counts only) is not
    # renderable as a view: treat it like no cache until the timer rewrites it.
    if entry is None or not entry.get("snapshots") or "distribution" not in entry:
        raise WindowMissingError(f"no cached union for a {days}-day window")
    meta = {k: v for k, v in entry.items() if k != "distribution"}
    return {
        "generated_at": data.get("generated_at"),
        **meta,
        **entry.get("distribution", {}),
    }


@lru_cache(maxsize=4)
def _read_window_nodes(path: str, mtime_ns: int) -> dict:
    """Parse the node cache once per rewrite."""
    # mtime_ns is part of the key so a rewrite by the timer invalidates the
    # cached parse; the file is a few MB and is read once per rewrite.
    return json.loads(Path(path).read_text())


def load_window_nodes(days: int, path: Path = None, stats_path: Path = None) -> dict:
    """Nodes of the `days`-day union as dicts (row fields + `last_seen`).

    Served from the widest-window file, filtered by last-seen >= cutoff.
    Raises WindowMissingError if the cache is absent or `days` is not one of
    the windows the stats cache holds — so this endpoint and the stats one
    agree on which windows exist.
    """
    path = path or WINDOW_NODES_FILE
    if not path.exists():
        raise WindowMissingError("no cached union nodes yet")
    cached_days = {w.get("days") for w in load_window_stats(stats_path).get("windows", [])}
    if days not in cached_days:
        raise WindowMissingError(f"no cached union for a {days}-day window")
    try:
        data = _read_window_nodes(str(path), path.stat().st_mtime_ns)
    except (json.JSONDecodeError, OSError):
        raise WindowMissingError("union node cache unreadable")
    widest = data.get("days")
    reference = data.get("generated_at")
    if widest is None or reference is None or days > widest:
        raise WindowMissingError(f"no cached union for a {days}-day window")
    cutoff = reference - days * DAY_SECONDS
    fields = data.get("fields") or [*FIELDS, "last_seen"]
    nodes = [dict(zip(fields, row)) for row in data.get("nodes", []) if row[-1] >= cutoff]
    nodes.sort(key=lambda n: n["last_seen"], reverse=True)
    return {
        "days": days,
        "generated_at": reference,
        "since": cutoff,
        "count": len(nodes),
        "nodes": nodes,
    }
