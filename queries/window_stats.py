"""Rolling-window union of unique nodes per network type.

Trackers like bitnod.es count the union of unique nodes seen over a window
(8 days), not the simultaneously-reachable set a single snapshot holds. This
computes that union from the snapshots on disk. It is expensive (reads every
snapshot in the widest window), so it is precomputed by a timer and cached to
JSON; the API serves the cache via `load_window_stats`.
"""

import json
from pathlib import Path

from queries.config import EXPORT_DIR, WINDOW_STATS_FILE
from queries.snapshots import list_snapshots, load_snapshot
from queries.util import classify_network as _classify

# 5 days matches the upstream crawler's max node-age (max_age up to 432000s),
# so it's the exact apples-to-apples window vs bitnodes-style trackers; 8 days
# matches bitnod.es's stated pruning; 1/3 bracket the recent-config figure.
WINDOWS_DAYS = (1, 3, 5, 8)
DAY_SECONDS = 86400


def compute_window_stats(windows_days=WINDOWS_DAYS, now: int = None) -> dict:
    """Union of unique (address, port) per network over each window.

    Single pass over the snapshots: each node is added to every window whose
    cutoff it satisfies (the widest window is the superset).
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
    }
    if not snaps:
        for d in windows:
            result["windows"].append(_empty_window(d))
        return result
    cutoffs = {d: reference - d * DAY_SECONDS for d in windows}
    # One set of unique (addr, port) per (window, network).
    sets = {d: {n: set() for n in ("ipv4", "ipv6", "tor", "i2p")} for d in windows}
    counts = {d: 0 for d in windows}

    widest_cutoff = min(cutoffs.values())
    for ts in snaps:
        if ts < widest_cutoff:
            continue
        try:
            rows = load_snapshot(ts)
        except FileNotFoundError:
            continue
        applicable = [d for d in windows if ts >= cutoffs[d]]
        for d in applicable:
            counts[d] += 1
        for r in rows:
            net = _classify(r[0])
            key = (r[0], r[1])
            for d in applicable:
                sets[d][net].add(key)

    for d in windows:
        s = sets[d]
        ipv4, ipv6 = len(s["ipv4"]), len(s["ipv6"])
        tor, i2p = len(s["tor"]), len(s["i2p"])
        clearnet = ipv4 + ipv6
        result["windows"].append({
            "days": d,
            "snapshots": counts[d],
            "ipv4": ipv4,
            "ipv6": ipv6,
            "clearnet": clearnet,
            "tor": tor,
            "i2p": i2p,
            "total": clearnet + tor + i2p,
        })
    return result


def _empty_window(days: int) -> dict:
    return {
        "days": days, "snapshots": 0, "ipv4": 0, "ipv6": 0,
        "clearnet": 0, "tor": 0, "i2p": 0, "total": 0,
    }


def write_window_stats(now: int = None, path: Path = None) -> dict:
    path = path or WINDOW_STATS_FILE
    data = compute_window_stats(now=now)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)  # atomic
    return data


def load_window_stats(path: Path = None) -> dict:
    """Read the cached windowed counts. Empty result if absent/unreadable."""
    path = path or WINDOW_STATS_FILE
    if not path.exists():
        return {"generated_at": None, "windows": []}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "windows": []}
