"""Leaderboard, rankings (by country/ASN/UA), and IP groupings over the latest snapshot."""

import statistics
from collections import defaultdict

from queries.rtt import medians_in_window
from queries.snapshots import list_snapshots, load_snapshot
from queries.util import iso2_to_iso3


class NoSnapshotsError(LookupError):
    """No snapshots are available on disk."""


class SnapshotMissingError(FileNotFoundError):
    """The latest snapshot is referenced but its file is missing."""


def _latest_snapshot_rows() -> list[list]:
    snaps = list_snapshots()
    if not snaps:
        raise NoSnapshotsError("no snapshots available yet")
    try:
        return load_snapshot(snaps[-1])
    except FileNotFoundError as e:
        raise SnapshotMissingError("latest snapshot missing on disk") from e


def leaderboard(
    country: str | None = None,
    asn: str | None = None,
    limit: int = 50,
) -> list[dict]:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    results: list[dict] = []
    for r in rows:
        addr, port = r[0], r[1]
        latency = medians.get((addr, port))
        if latency is None:
            continue
        node_country = r[9]
        node_asn = r[13]
        if country and node_country != country:
            continue
        if asn and node_asn != asn:
            continue
        results.append({
            "address": addr,
            "port": port,
            "country": node_country,
            "asn": node_asn,
            "asn_name": r[14],
            "user_agent": r[3],
            "latency_ms": latency,
        })
    results.sort(key=lambda x: x["latency_ms"])
    return results[:limit]


def _group_ranking(rows: list[list], key_fn, medians: dict) -> list[dict]:
    buckets: dict = defaultdict(list)
    for r in rows:
        label = key_fn(r)
        if label is None or label == "":
            continue
        latency = medians.get((r[0], r[1]))
        buckets[label].append(latency)
    out: list[dict] = []
    for label, latencies in buckets.items():
        present = [v for v in latencies if v is not None]
        median_val = int(statistics.median(present)) if present else None
        out.append({"label": label, "total_nodes": len(latencies), "median_rtt_ms": median_val})
    out.sort(key=lambda x: x["total_nodes"], reverse=True)
    return out


def rankings_by_country() -> list[dict]:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    grouped = _group_ranking(rows, lambda r: r[9], medians)
    return [
        {
            "country": g["label"],
            "country_iso3": iso2_to_iso3(g["label"]),
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]


def rankings_by_asn() -> list[dict]:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    asn_names: dict[str, str] = {}
    for r in rows:
        if r[13] and r[13] not in asn_names:
            asn_names[r[13]] = r[14] or ""
    grouped = _group_ranking(rows, lambda r: r[13], medians)
    return [
        {
            "asn": g["label"],
            "asn_name": asn_names.get(g["label"], ""),
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]


def rankings_by_user_agent() -> list[dict]:
    rows = _latest_snapshot_rows()
    medians = medians_in_window()
    grouped = _group_ranking(rows, lambda r: r[3], medians)
    return [
        {
            "user_agent": g["label"],
            "total_nodes": g["total_nodes"],
            "median_rtt_ms": g["median_rtt_ms"],
        }
        for g in grouped
    ]


def groups_by_ip() -> list[dict]:
    rows = _latest_snapshot_rows()
    by_addr: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_addr[r[0]].append(r[1])
    results = [
        {"address": a, "total_nodes": len(ports), "ports": sorted(ports)}
        for a, ports in by_addr.items()
        if len(ports) >= 2
    ]
    results.sort(key=lambda x: x["total_nodes"], reverse=True)
    return results


def group_by_ip_detail(address: str) -> dict | None:
    """Returns None if the address isn't in the latest snapshot."""
    rows = _latest_snapshot_rows()
    matching = [r for r in rows if r[0] == address]
    if not matching:
        return None
    medians = medians_in_window()
    matching.sort(key=lambda r: r[1])
    nodes = [
        {
            "port": r[1],
            "user_agent": r[3],
            "height": r[6],
            "country": r[9],
            "asn": r[13],
            "latency_ms": medians.get((r[0], r[1])),
        }
        for r in matching
    ]
    return {"address": address, "total_nodes": len(nodes), "nodes": nodes}
