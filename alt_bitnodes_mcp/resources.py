"""MCP resources — snapshots exposed as `bitcoin://` URIs."""

import json

from mcp.server.fastmcp import FastMCP

from queries import (
    list_snapshots,
    load_snapshot,
)


def _snapshot_json(timestamp: int) -> str:
    rows = load_snapshot(timestamp)
    heights = [r[6] for r in rows if isinstance(r[6], int) and r[6] > 0]
    nodes: dict[str, list] = {}
    for r in rows:
        addr, port, proto, ua, ts, _services, height = r[0], r[1], r[2], r[3], r[4], r[5], r[6]
        nodes[f"{addr}:{port}"] = [proto, ua, ts, height]
    return json.dumps(
        {
            "timestamp": timestamp,
            "total_nodes": len(rows),
            "latest_height": max(heights) if heights else 0,
            "nodes": nodes,
        },
        separators=(",", ":"),
    )


def register(mcp: FastMCP) -> None:
    @mcp.resource("bitcoin://snapshot/latest", mime_type="application/json")
    def snapshot_latest() -> str:
        """Latest snapshot (same payload as /api/v1/snapshots/latest/)."""
        snaps = list_snapshots()
        if not snaps:
            return json.dumps({"error": "no snapshots available yet"})
        try:
            return _snapshot_json(snaps[-1])
        except FileNotFoundError:
            return json.dumps({"error": "latest snapshot missing on disk"})

    @mcp.resource("bitcoin://snapshot/{timestamp}", mime_type="application/json")
    def snapshot_by_ts(timestamp: str) -> str:
        """Specific snapshot by unix timestamp."""
        try:
            ts_int = int(timestamp)
        except (TypeError, ValueError):
            return json.dumps({"error": f"invalid timestamp: {timestamp}"})
        try:
            return _snapshot_json(ts_int)
        except FileNotFoundError:
            return json.dumps({"error": f"snapshot {ts_int} not found"})
