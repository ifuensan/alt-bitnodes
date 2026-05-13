"""MCP tools — read-only wrappers around `queries/`."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from queries import (
    NoSnapshotsError,
    SnapshotMissingError,
    group_by_ip_detail,
    groups_by_ip,
    leaderboard,
    list_snapshots as _list_snapshots,
    load_snapshot,
    medians_in_window,
    node_status,
    parse_node_id,
    rankings_by_asn,
    rankings_by_country,
    rankings_by_user_agent,
    samples_for,
    snapshot_meta,
    snapshot_stats,
    to_dict,
)
from queries.rtt import has_samples


def _snapshot_payload(timestamp: int) -> dict:
    """Same shape as `/api/v1/snapshots/{ts}/`."""
    rows = load_snapshot(timestamp)
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


def _network_classifier(addr: str) -> str:
    if addr.endswith(".onion"):
        return "onion"
    if addr.endswith(".b32.i2p") or addr.endswith(".i2p"):
        return "i2p"
    if ":" in addr:
        return "ipv6"
    return "ipv4"


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_latest_snapshot() -> dict:
        """Return metadata and node count for the most recent snapshot."""
        snaps = _list_snapshots()
        if not snaps:
            return {"error": "no snapshots available yet"}
        return snapshot_meta(snaps[-1])

    @mcp.tool()
    def get_snapshot_by_timestamp(timestamp: int) -> dict:
        """Return the full snapshot payload (nodes dict) for a given timestamp."""
        try:
            return _snapshot_payload(timestamp)
        except FileNotFoundError:
            return {"error": f"snapshot {timestamp} not found"}

    @mcp.tool()
    def list_snapshots(limit: int = 20) -> dict:
        """List the most recent snapshots, newest first, with metadata."""
        if limit < 1 or limit > 200:
            return {"error": "limit must be between 1 and 200"}
        snaps = sorted(_list_snapshots(), reverse=True)[:limit]
        results = []
        for ts in snaps:
            try:
                results.append(snapshot_meta(ts))
            except FileNotFoundError:
                continue
        return {"count": len(results), "results": results}

    @mcp.tool()
    def get_leaderboard(
        limit: int = 50,
        by: Literal["latency", "uptime"] = "latency",
        country: str | None = None,
        asn: str | None = None,
    ) -> dict:
        """Return the fastest nodes by median RTT (latency). `by="uptime"` is
        accepted for forward-compat but currently sorts identically to latency."""
        if limit < 1 or limit > 500:
            return {"error": "limit must be between 1 and 500"}
        try:
            results = leaderboard(country=country, asn=asn, limit=limit)
        except NoSnapshotsError:
            return {"error": "no snapshots available yet"}
        except SnapshotMissingError:
            return {"error": "latest snapshot missing on disk"}
        return {"count": len(results), "by": by, "results": results}

    @mcp.tool()
    def get_node_rtt(address: str, port: int, hours: int = 24) -> dict:
        """Return the RTT time series for a node over the last `hours` hours."""
        if hours < 1 or hours > 168:
            return {"error": "hours must be between 1 and 168"}
        if port < 1 or port > 65535:
            return {"error": "port must be 1-65535"}
        from queries.snapshots import known_addresses_set
        if (address, port) not in known_addresses_set() and not has_samples(address, port):
            return {"error": "node not found"}
        return {
            "address": address,
            "port": port,
            "hours": hours,
            "latency": samples_for(address, port, hours),
        }

    @mcp.tool()
    def get_node_details(address: str, port: int) -> dict:
        """Return current status (UP/DOWN) and last-known metadata for a node."""
        if port < 1 or port > 65535:
            return {"error": "port must be 1-65535"}
        status = node_status(address, port)
        if status is None:
            return {"error": "node not found"}
        return status

    @mcp.tool()
    def search_nodes(
        country: str | None = None,
        asn: str | None = None,
        version: str | None = None,
        network: Literal["ipv4", "ipv6", "onion", "i2p"] | None = None,
        limit: int = 100,
    ) -> dict:
        """Filter nodes in the latest snapshot by country / ASN / version / network."""
        if limit < 1 or limit > 1000:
            return {"error": "limit must be between 1 and 1000"}
        snaps = _list_snapshots()
        if not snaps:
            return {"error": "no snapshots available yet"}
        try:
            rows = load_snapshot(snaps[-1])
        except FileNotFoundError:
            return {"error": "latest snapshot missing on disk"}
        results: list[dict] = []
        for r in rows:
            d = to_dict(r)
            if country and d.get("country") != country:
                continue
            if asn and d.get("asn") != asn:
                continue
            if version and version not in (d.get("user_agent") or ""):
                continue
            if network and _network_classifier(d.get("address") or "") != network:
                continue
            results.append(d)
            if len(results) >= limit:
                break
        return {"count": len(results), "results": results}

    @mcp.tool()
    def get_chart_data(
        chart: Literal["reachable", "by_country", "by_version"],
        window: Literal["24h", "7d", "30d"] = "24h",
    ) -> dict:
        """Aggregate chart data computed over the latest snapshot.

        `window` is reserved for future use (snapshots-over-time series); today
        all charts return the latest-snapshot view since per-snapshot history
        beyond the latest is not aggregated server-side.
        """
        snaps = _list_snapshots()
        if not snaps:
            return {"error": "no snapshots available yet"}
        try:
            stats = snapshot_stats(snaps[-1], medians_now=list(medians_in_window().values()))
        except FileNotFoundError:
            return {"error": "latest snapshot missing on disk"}

        if chart == "reachable":
            return {"chart": chart, "window": window, "total": stats["total"]}
        if chart == "by_country":
            return {
                "chart": chart,
                "window": window,
                "results": stats["top_countries"],
                "iso3": stats["countries_iso3"],
            }
        if chart == "by_version":
            return {
                "chart": chart,
                "window": window,
                "results": stats["top_user_agents"],
            }
        return {"error": f"unknown chart {chart}"}

    @mcp.tool()
    def get_ip_groups(min_nodes: int = 2) -> dict:
        """List IPs hosting more than one node in the latest snapshot."""
        if min_nodes < 2:
            return {"error": "min_nodes must be >= 2"}
        try:
            results = groups_by_ip()
        except NoSnapshotsError:
            return {"error": "no snapshots available yet"}
        except SnapshotMissingError:
            return {"error": "latest snapshot missing on disk"}
        filtered = [g for g in results if g["total_nodes"] >= min_nodes]
        return {"count": len(filtered), "results": filtered}

    @mcp.tool()
    def get_ip_group_detail(address: str) -> dict:
        """Detail (ports + per-port metadata) for one IP's group."""
        try:
            result = group_by_ip_detail(address)
        except NoSnapshotsError:
            return {"error": "no snapshots available yet"}
        except SnapshotMissingError:
            return {"error": "latest snapshot missing on disk"}
        if result is None:
            return {"error": "address not found in latest snapshot"}
        return result

    @mcp.tool()
    def get_rankings(by: Literal["country", "asn", "user_agent"]) -> dict:
        """Aggregate rankings over the latest snapshot, grouped by `by`."""
        try:
            if by == "country":
                results = rankings_by_country()
            elif by == "asn":
                results = rankings_by_asn()
            elif by == "user_agent":
                results = rankings_by_user_agent()
            else:
                return {"error": f"unknown ranking {by}"}
        except NoSnapshotsError:
            return {"error": "no snapshots available yet"}
        except SnapshotMissingError:
            return {"error": "latest snapshot missing on disk"}
        return {"by": by, "count": len(results), "results": results}

    # node id helper (echo): handy for clients that have `<addr>-<port>` strings
    @mcp.tool()
    def parse_node_id_str(node_id: str) -> dict:
        """Parse a `<address>-<port>` node id string into address and port."""
        try:
            addr, port = parse_node_id(node_id)
        except ValueError as e:
            return {"error": f"invalid node id: {e}"}
        return {"address": addr, "port": port}
