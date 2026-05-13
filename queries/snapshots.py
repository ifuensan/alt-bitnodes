"""Snapshot file loading and summary stats."""

import json
import statistics
from collections import Counter
from functools import lru_cache

from queries.config import EXPORT_DIR, FIELDS
from queries.util import iso2_to_iso3


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


def snapshot_stats(timestamp: int, medians_now: list[int] | None = None) -> dict:
    """Compute distribution stats over one snapshot.

    `medians_now` is the list of in-window median RTTs across nodes, used to
    derive the overall `median_latency_ms`. Caller passes it in to avoid pulling
    `queries.rtt` from inside `queries.snapshots` (keeps deps acyclic).
    """
    rows = load_snapshot(timestamp)

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

    median_latency_ms = (
        int(statistics.median(medians_now)) if medians_now else None
    )

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
