"""MCP prompts — pre-built analysis flows that embed live data."""

import json

from mcp.server.fastmcp import FastMCP

from queries import (
    NoSnapshotsError,
    SnapshotMissingError,
    list_snapshots,
    load_snapshot,
    rankings_by_country,
    snapshot_meta,
    snapshot_stats,
)


def _safe_latest_stats() -> dict | None:
    snaps = list_snapshots()
    if not snaps:
        return None
    try:
        return snapshot_stats(snaps[-1])
    except FileNotFoundError:
        return None


def register(mcp: FastMCP) -> None:
    @mcp.prompt(title="Analyse Bitcoin network health")
    def analyze_network_health() -> str:
        """Embed latest snapshot summary and ask for a health analysis."""
        stats = _safe_latest_stats()
        if stats is None:
            return "No snapshots are available yet on alt-bitnodes. Try again later."
        payload = {"stats": stats}
        return (
            "You are analysing the current health of the Bitcoin peer-to-peer network "
            "using a snapshot from alt-bitnodes.\n\n"
            f"Snapshot data:\n```json\n{json.dumps(payload, separators=(',',':'))}\n```\n\n"
            "Produce a concise report covering:\n"
            "1. Reachable node count and how it compares to the median Bitcoin network of recent years (~15k).\n"
            "2. Geographic distribution (top countries, concentration).\n"
            "3. Client diversity (top user agents, share of Core vs. forks/knots).\n"
            "4. Any red flags (e.g. one ASN >50%, single country dominance).\n"
        )

    @mcp.prompt(title="Compare two snapshots")
    def compare_snapshots(t1: str, t2: str) -> str:
        """Diff two snapshots by timestamp."""
        try:
            ts1, ts2 = int(t1), int(t2)
        except (TypeError, ValueError):
            return f"Invalid timestamps: t1={t1!r}, t2={t2!r}. Provide unix timestamps."
        try:
            rows1 = load_snapshot(ts1)
            rows2 = load_snapshot(ts2)
        except FileNotFoundError as e:
            return f"Snapshot not found: {e}"

        keys1 = {(r[0], r[1]) for r in rows1}
        keys2 = {(r[0], r[1]) for r in rows2}
        appeared = list(keys2 - keys1)[:50]
        disappeared = list(keys1 - keys2)[:50]
        meta1 = snapshot_meta(ts1)
        meta2 = snapshot_meta(ts2)
        payload = {
            "t1": meta1,
            "t2": meta2,
            "delta_total": meta2["total_nodes"] - meta1["total_nodes"],
            "appeared_sample": [f"{a}:{p}" for a, p in appeared],
            "disappeared_sample": [f"{a}:{p}" for a, p in disappeared],
        }
        return (
            f"Compare two Bitcoin network snapshots taken at t1={ts1} and t2={ts2}.\n\n"
            f"```json\n{json.dumps(payload, separators=(',',':'))}\n```\n\n"
            "Discuss: net change in reachable count, churn (appeared vs disappeared), "
            "and whether the delta is consistent with normal node turnover or suggests "
            "an external event (Tor outage, geographic incident, fork)."
        )

    @mcp.prompt(title="Network distribution summary")
    def network_distribution_summary() -> str:
        """Country / ASN / version / network-type breakdown of the latest snapshot."""
        stats = _safe_latest_stats()
        if stats is None:
            return "No snapshots available yet."
        try:
            countries = rankings_by_country()[:15]
        except (NoSnapshotsError, SnapshotMissingError):
            countries = []
        payload = {
            "total_nodes": stats["total"],
            "countries_total": stats["countries_total"],
            "asns_total": stats["asns_total"],
            "top_countries": countries,
            "top_user_agents": stats["top_user_agents"],
            "top_asns": stats["top_asns"],
        }
        return (
            "Summarise the geographic, ASN, and client-software distribution of the "
            "current Bitcoin reachable node set.\n\n"
            f"```json\n{json.dumps(payload, separators=(',',':'))}\n```\n\n"
            "Emphasise: concentration ratios (top-3 share), notable absences "
            "(if a usual top country is missing), and client-diversity health.\n"
        )
