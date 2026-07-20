# mcp-service

## MODIFIED Requirements

### Requirement: Tools cover the v1 REST surface for read access

The server SHALL expose at minimum the following tools, each backed by `queries/` and accepting validated input:

- `get_latest_snapshot()`
- `get_snapshot_by_timestamp(timestamp: int)`
- `list_snapshots(limit: int = 20)`
- `get_node_details(address: str, port: int)`
- `search_nodes(country: str | None = None, asn: int | None = None, version: str | None = None, network: "ipv4" | "ipv6" | "onion" | "i2p" | None = None)`
- `get_chart_data(chart: "reachable" | "by_country" | "by_version" | "by_network", window: "24h" | "7d" | "30d" = "24h")`
- `get_rankings(by: "country" | "asn" | "user_agent")`
- `get_ip_groups(min_nodes: int = 2)`
- `get_ip_group_detail(address: str)`
- `get_network_breakdown()` — clearnet/tor/i2p counts of the latest snapshot
- `get_window_stats()` — rolling-window unique-node union per network (cached)
- `list_archives()` — available archived snapshot photos (tier, date, formats, URLs)
- `get_archive_url(timestamp: int, fmt: "csv" | "parquet")` — download URL for one archived photo

There SHALL be no `get_leaderboard` or `get_node_rtt` tool — the RTT/latency data they served has been removed.

#### Scenario: Latest snapshot
- **WHEN** the client calls `get_latest_snapshot()`
- **THEN** the server returns the most recent snapshot metadata and node count as a JSON object

#### Scenario: Windowed union
- **WHEN** the client calls `get_window_stats()`
- **THEN** the server returns the cached per-network unique-node union for each configured window (empty result if the cache is not yet populated, never a slow recompute)

#### Scenario: Network breakdown
- **WHEN** the client calls `get_network_breakdown()`
- **THEN** the server returns clearnet, tor and i2p counts for the latest snapshot summing to its total

#### Scenario: Archive access
- **WHEN** the client calls `list_archives()` or `get_archive_url()`
- **THEN** the server returns archive metadata and download URLs (not binary contents), or an error for an unknown timestamp/format

#### Scenario: No RTT or leaderboard tools
- **WHEN** the client lists tools
- **THEN** the tool list SHALL NOT include `get_leaderboard` or `get_node_rtt`

#### Scenario: Invalid input
- **WHEN** the client calls a tool with arguments that violate the declared schema (e.g. negative `hours`)
- **THEN** the server returns an MCP error response without invoking the data layer
