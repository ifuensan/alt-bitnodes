"""Decode the services bitmask into named capability flags and adoption stats.

Every snapshot row carries the node's service-flag bitmask (field 5) from the
version handshake; this module turns it into named adoption metrics — what
share of the reachable network advertises BIP324 transport, serves compact
filters, signals limited block serving, and so on. Unknown bits are
aggregated as `other` with the raw masks preserved, never silently dropped.

BIP159 caveat: Bitcoin Core signals NODE_NETWORK_LIMITED on non-pruned full
nodes too, so the raw flag is NOT a pruned-node count. The `derived.pruned`
metric (NODE_NETWORK_LIMITED set, NODE_NETWORK clear) is the honest one.
"""

import datetime as dt
import json
from pathlib import Path

from queries.config import SERVICES_SERIES_FILE
from queries.snapshots import list_snapshots, load_snapshot
from queries.util import classify_network as _classify

SERVICE_FLAGS = [
    ("NODE_NETWORK", 1),
    ("NODE_BLOOM", 4),
    ("NODE_WITNESS", 8),
    ("NODE_COMPACT_FILTERS", 64),
    ("NODE_NETWORK_LIMITED", 1024),
    ("NODE_P2P_V2", 2048),
]
NAMED_MASK = 0
for _name, _bit in SERVICE_FLAGS:
    NAMED_MASK |= _bit

NETWORKS = ("ipv4", "ipv6", "tor", "i2p")

SERIES_BACKFILL_DAYS = 90
DAY_SECONDS = 86400


def decode_services(mask) -> list[str]:
    """Named flags present in a services bitmask."""
    try:
        mask = int(mask)
    except (TypeError, ValueError):
        return []
    return [name for name, bit in SERVICE_FLAGS if mask & bit]


def _pct(count: int, total: int) -> float:
    return round(100.0 * count / total, 2) if total else 0.0


def services_breakdown(timestamp: int) -> dict:
    """Per-flag adoption counts for one snapshot, total and per network."""
    rows = load_snapshot(timestamp)
    total = len(rows)
    flag_counts = {name: 0 for name, _bit in SERVICE_FLAGS}
    flag_networks = {name: {n: 0 for n in NETWORKS} for name, _bit in SERVICE_FLAGS}
    other_count = 0
    other_masks: dict[str, int] = {}
    pruned_count = 0

    for r in rows:
        try:
            mask = int(r[5])
        except (TypeError, ValueError):
            continue
        net = _classify(r[0])
        for name, bit in SERVICE_FLAGS:
            if mask & bit:
                flag_counts[name] += 1
                flag_networks[name][net] += 1
        # BIP159: LIMITED without NETWORK is what actually running pruned
        # looks like; LIMITED alone is signaled by full nodes too.
        if (mask & 1024) and not (mask & 1):
            pruned_count += 1
        extra = mask & ~NAMED_MASK
        if extra:
            other_count += 1
            key = str(extra)
            other_masks[key] = other_masks.get(key, 0) + 1

    flags = [
        {
            "flag": name,
            "bit": bit,
            "count": flag_counts[name],
            "pct": _pct(flag_counts[name], total),
            "by_network": flag_networks[name],
        }
        for name, bit in SERVICE_FLAGS
    ]
    return {
        "timestamp": timestamp,
        "total": total,
        "flags": flags,
        "derived": {
            "pruned": {"count": pruned_count, "pct": _pct(pruned_count, total)},
        },
        "other": {
            "count": other_count,
            "pct": _pct(other_count, total),
            "masks": other_masks,
        },
    }


def _utc_date(timestamp: int) -> dt.date:
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).date()


def _day_samples(today: dt.date, backfill_days: int) -> dict[str, int]:
    """date-iso -> last snapshot timestamp, for complete days only."""
    cutoff = today - dt.timedelta(days=backfill_days)
    samples: dict[str, int] = {}
    for ts in list_snapshots():
        date = _utc_date(ts)
        if date >= today or date < cutoff:
            continue
        key = date.isoformat()
        if key not in samples or ts > samples[key]:
            samples[key] = ts
    return samples


def refresh_services_series(path: Path = None, today: dt.date = None) -> dict:
    """Extend the persisted daily adoption series with any missing days.

    Days already in the series are kept as-is (their raw snapshots may have
    been pruned since); missing days with snapshots on disk are computed and
    added. Sampling is one snapshot per complete UTC day.
    """
    path = path or SERVICES_SERIES_FILE
    today = today or dt.datetime.now(dt.timezone.utc).date()
    series = load_services_series(path)
    have = {d["date"] for d in series["days"]}

    for date_iso, ts in sorted(_day_samples(today, SERIES_BACKFILL_DAYS).items()):
        if date_iso in have:
            continue
        try:
            breakdown = services_breakdown(ts)
        except (FileNotFoundError, ValueError):
            # ValueError covers JSONDecodeError: a corrupt day-snapshot must
            # not freeze the whole series (it would be re-picked every run).
            continue
        series["days"].append(
            {
                "date": date_iso,
                "timestamp": ts,
                "total": breakdown["total"],
                "flags": {f["flag"]: f["pct"] for f in breakdown["flags"]},
            }
        )
    series["days"].sort(key=lambda d: d["date"])
    series["generated_at"] = series["days"][-1]["timestamp"] if series["days"] else None

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(series))
    tmp.replace(path)
    return series


def load_services_series(path: Path = None) -> dict:
    """Read the cached daily series. Empty result if absent/unreadable."""
    path = path or SERVICES_SERIES_FILE
    if not path.exists():
        return {"generated_at": None, "days": []}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "days": []}
    if not isinstance(data, dict) or not isinstance(data.get("days"), list):
        return {"generated_at": None, "days": []}
    # Drop malformed day entries: one bad dict must not make the persisted
    # series permanently un-refreshable (load-modify-write cycle).
    data["days"] = [
        d for d in data["days"]
        if isinstance(d, dict) and "date" in d and "timestamp" in d
    ]
    return data


def latest_services_payload() -> dict:
    """Latest-snapshot breakdown + daily series, the shape both APIs serve."""
    snaps = list_snapshots()
    latest = None
    if snaps:
        try:
            latest = services_breakdown(snaps[-1])
        except (FileNotFoundError, ValueError):
            # ValueError covers JSONDecodeError: a half-written latest
            # snapshot must degrade to the empty state, not a 500.
            latest = None
    return {"latest": latest, "series": load_services_series()}
