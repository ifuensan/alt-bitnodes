## MODIFIED Requirements

### Requirement: MCP server exposes Bitcoin network data via Model Context Protocol

The system SHALL provide an MCP server (`alt_bitnodes_mcp`) that exposes alt-bitnodes data (snapshots, charts, node details, rankings, IP groups) to MCP clients. The server SHALL use the official Python `mcp` SDK (FastMCP) and SHALL reuse the same data layer as the REST API v1 (via the shared `queries/` package), with no duplicated business logic. The server SHALL NOT expose RTT/latency data — that subsystem has been removed.

#### Scenario: Server starts and registers MCP primitives
- **WHEN** the server process starts
- **THEN** it registers all defined tools, resources, and prompts and responds successfully to MCP `initialize` requests advertising those capabilities

#### Scenario: Read-only contract
- **WHEN** an MCP client invokes any tool
- **THEN** the tool reads from read-only sources and SHALL NOT mutate persistent state, write to Redis keys consumed by the crawler, trigger network crawls, or alter user data

### Requirement: Tools cover the v1 REST surface for read access

The server SHALL expose at minimum the following tools, each backed by `queries/` and accepting validated input:

- `get_latest_snapshot()`
- `get_snapshot_by_timestamp(timestamp: int)`
- `list_snapshots(limit: int = 20)`
- `get_node_details(address: str, port: int)`
- `search_nodes(country: str | None = None, asn: int | None = None, version: str | None = None, network: "ipv4" | "ipv6" | "onion" | "i2p" | None = None)`
- `get_chart_data(chart: "reachable" | "by_country" | "by_version", window: "24h" | "7d" | "30d" = "24h")`
- `get_rankings(by: "country" | "asn" | "user_agent")`
- `get_ip_groups(min_nodes: int = 2)`
- `get_ip_group_detail(address: str)`

There SHALL be no `get_leaderboard` or `get_node_rtt` tool — the RTT/latency data they served has been removed.

#### Scenario: Latest snapshot
- **WHEN** the client calls `get_latest_snapshot()`
- **THEN** the server returns the most recent snapshot metadata and node count as a JSON object

#### Scenario: No RTT or leaderboard tools
- **WHEN** the client lists tools
- **THEN** the tool list SHALL NOT include `get_leaderboard` or `get_node_rtt`

#### Scenario: Invalid input
- **WHEN** the client calls a tool with arguments that violate the declared schema (e.g. negative `hours`)
- **THEN** the server returns an MCP error response without invoking the data layer

### Requirement: Resources expose snapshots by URI

The server SHALL expose the following MCP resources with URIs:
- `bitcoin://snapshot/latest`
- `bitcoin://snapshot/{timestamp}`

Each resource SHALL return JSON whose schema matches the corresponding REST endpoint payload. There SHALL be no `bitcoin://leaderboard/*` resources.

#### Scenario: Read latest snapshot resource
- **WHEN** the client reads `bitcoin://snapshot/latest`
- **THEN** the server returns the latest snapshot as JSON identical to what `get_latest_snapshot()` would produce

#### Scenario: List resources
- **WHEN** the client lists resources
- **THEN** the server enumerates the snapshot URI patterns above, including the parameterised `bitcoin://snapshot/{timestamp}` as a resource template, and SHALL NOT enumerate any `bitcoin://leaderboard/*` resource

### Requirement: Prompts provide pre-built analysis flows

The server SHALL expose at minimum the following prompts:
- `analyze-network-health`
- `compare-snapshots(t1, t2)`
- `network-distribution-summary`

Each prompt SHALL produce a structured message sequence suitable for handing to an LLM, embedding relevant data fetched via the same `queries/` helpers. There SHALL be no `latency-report` prompt.

#### Scenario: analyze-network-health
- **WHEN** the client invokes `analyze-network-health` with no arguments
- **THEN** the server returns a prompt that includes the latest snapshot summary and asks the model to analyse network health (counts trend, top countries, version mix) — with no latency/RTT content

#### Scenario: No latency-report prompt
- **WHEN** the client lists prompts
- **THEN** the prompt list SHALL NOT include `latency-report`

### Requirement: REST API v1 remains unchanged in public behaviour

The MCP server SHALL NOT alter the URLs, request shapes, response payloads, or status codes of the REST API v1 endpoints served by `app.py` (excluding the RTT/latency endpoints removed by the `remove-rtt-pipeline` change). The shared `queries/` package SHALL remain transparent to REST consumers.

#### Scenario: REST contract preserved
- **WHEN** a REST client requests `/api/v1/snapshots/`, `/api/v1/nodes/{addr}-{port}/`, `/api/v1/rankings/countries/`, `/api/v1/groups/by-ip/`, or any other surviving v1 endpoint
- **THEN** the response status code, headers, and JSON shape SHALL be identical to the pre-change behaviour (minus the removed `latency_ms` / `median_rtt_ms` fields)
