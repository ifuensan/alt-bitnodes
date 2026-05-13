"""MCP server for alt-bitnodes — exposes Bitcoin network data
(snapshots, leaderboard, RTT, charts) as MCP tools, resources, and prompts.

Reuses the same Redis-backed query layer (`queries/`) that the REST API uses.
"""

from alt_bitnodes_mcp.server import build_server

__all__ = ["build_server"]
