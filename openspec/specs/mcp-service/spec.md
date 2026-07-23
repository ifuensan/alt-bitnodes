# mcp-service

## Purpose

Defines the MCP (Model Context Protocol) server `alt_bitnodes_mcp` that exposes alt-bitnodes network data (snapshots, charts, node details, rankings, IP groups) to MCP clients as tools, resources, and prompts. Covers transports (stdio + Streamable HTTP), bearer-token auth, the public edge integration, deployment, and the contract that the REST API v1 stays unchanged. RTT/latency data is intentionally not exposed — that subsystem was removed in the `remove-rtt-pipeline` change.
## Requirements
### Requirement: MCP server exposes Bitcoin network data via Model Context Protocol

The system SHALL provide an MCP server (`alt_bitnodes_mcp`) that exposes alt-bitnodes data (snapshots, charts, node details, rankings, IP groups) to MCP clients. The server SHALL use the official Python `mcp` SDK (FastMCP) and SHALL reuse the same data layer as the REST API v1 (via the shared `queries/` package), with no duplicated business logic. The server SHALL NOT expose RTT/latency data — that subsystem has been removed.

#### Scenario: Server starts and registers MCP primitives
- **WHEN** the server process starts
- **THEN** it registers all defined tools, resources, and prompts and responds successfully to MCP `initialize` requests advertising those capabilities

#### Scenario: Read-only contract
- **WHEN** an MCP client invokes any tool
- **THEN** the tool reads from read-only sources and SHALL NOT mutate persistent state, write to Redis keys consumed by the crawler, trigger network crawls, or alter user data

### Requirement: MCP server supports stdio and Streamable HTTP transports

The MCP server SHALL support two transports selectable at launch:
- `stdio` for local client integrations (Claude Desktop, `claude mcp add` local)
- `Streamable HTTP` for remote authenticated access on `127.0.0.1:8001` (proxied by nginx at `/mcp/` behind CloudFront)

#### Scenario: stdio mode
- **WHEN** the server is invoked as `python -m alt_bitnodes_mcp --stdio`
- **THEN** it speaks the MCP protocol over stdin/stdout and exits cleanly when the client disconnects

#### Scenario: HTTP mode
- **WHEN** the server is invoked as `python -m alt_bitnodes_mcp --http --host 127.0.0.1 --port 8001`
- **THEN** it serves Streamable HTTP at `/` on that port and SHALL stream Server-Sent Events without buffering

### Requirement: HTTP transport requires bearer token authentication

When running in HTTP mode, the server SHALL require every incoming request to carry `Authorization: Bearer <token>` where `<token>` matches the secret stored in `/etc/alt-bitnodes/mcp-token`. Requests missing or with an invalid token SHALL be rejected with HTTP 401.

#### Scenario: Valid token
- **WHEN** an MCP client sends a request with `Authorization: Bearer <valid-token>`
- **THEN** the request proceeds to MCP protocol handling

#### Scenario: Missing or invalid token
- **WHEN** an MCP client sends a request without `Authorization` header or with an incorrect token
- **THEN** the server SHALL respond with HTTP 401 and SHALL NOT process the MCP message

#### Scenario: stdio mode bypasses bearer
- **WHEN** the server runs in stdio mode
- **THEN** bearer authentication SHALL NOT be enforced (local-process trust boundary)

### Requirement: Public edge exposes MCP HTTP via CloudFront with origin auth and no caching

The public edge (nginx + CloudFront) SHALL expose the MCP HTTP endpoint at `https://pesquisa.hacknodes.xyz/mcp/`, applying the same `X-Origin-Auth` header gate between CloudFront and the EC2 origin that the REST API uses, with cache disabled and SSE-compatible proxying.

#### Scenario: Request through CloudFront
- **WHEN** an MCP client sends a request to `https://pesquisa.hacknodes.xyz/mcp/`
- **THEN** CloudFront forwards it to the EC2 origin injecting `X-Origin-Auth`, nginx validates the header and proxies to `127.0.0.1:8001` without buffering, the MCP server validates the bearer token, and the response is streamed back without being cached

#### Scenario: Direct origin access without `X-Origin-Auth`
- **WHEN** any client connects directly to the EC2 origin (bypassing CloudFront) on `/mcp/` without the correct `X-Origin-Auth` header
- **THEN** nginx SHALL respond with HTTP 403

#### Scenario: SSE streaming through CloudFront
- **WHEN** an MCP HTTP session opens a server-sent event stream
- **THEN** CloudFront and nginx SHALL forward events with no buffering and connections SHALL remain open for at least 1 hour before any edge-induced timeout

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

### Requirement: Tools expose propagation, services, and unique-node data
The MCP server SHALL provide three additional read-only tools wrapping the
same `queries/` functions as the REST endpoints, with no duplicated
business logic: `get_block_propagation` (aggregate ECDF and recent blocks
with per-class percentiles), `get_services_breakdown` (latest-snapshot
per-flag breakdown and daily adoption series), and
`get_unique_nodes_estimate` (weighted estimate, raw count, composition
histogram, and method description).

#### Scenario: Tools registered
- **WHEN** the MCP server starts
- **THEN** `get_block_propagation`, `get_services_breakdown`, and
  `get_unique_nodes_estimate` are registered and advertised

#### Scenario: Tool results mirror the v1 endpoints
- **WHEN** a client calls one of the three tools
- **THEN** the returned data matches the corresponding
  `/api/v1/stats/...` response for the same underlying state

#### Scenario: No data yet
- **WHEN** a tool is called before the collector has produced its dataset
- **THEN** the tool returns an empty result with an explanatory note, not
  an error

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

### Requirement: Deployment is automated via install.sh and systemd

`deploy/install.sh` SHALL install the MCP server, generate the bearer token on first run if missing, store it at `/etc/alt-bitnodes/mcp-token` with mode `0600` owned by root, and configure a systemd unit `alt-bitnodes-mcp.service` that runs the HTTP transport on `127.0.0.1:8001`. The installer SHALL be idempotent.

#### Scenario: Fresh install
- **WHEN** `install.sh` runs on a host with no prior installation
- **THEN** it generates `/etc/alt-bitnodes/mcp-token` (mode 0600, owner root), installs `alt-bitnodes-mcp.service`, enables and starts it, and the service SHALL bind to `127.0.0.1:8001`

#### Scenario: Re-run install
- **WHEN** `install.sh` runs on a host that already has the MCP server installed
- **THEN** it SHALL NOT regenerate the existing token, SHALL update the systemd unit if its template changed, and SHALL restart `alt-bitnodes-mcp.service` only if the unit or its dependencies changed

#### Scenario: Token rotation
- **WHEN** an operator deletes `/etc/alt-bitnodes/mcp-token` and re-runs `install.sh`
- **THEN** a new token SHALL be generated and the service SHALL be restarted to pick it up

### Requirement: Documentation describes how to connect MCP clients

`deploy/README.md` SHALL include a section explaining how to connect to the MCP service from Claude Desktop (stdio configuration JSON snippet) and from Claude Code / remote clients (`claude mcp add` example using the HTTPS URL with the bearer token).

#### Scenario: Operator follows README to connect Claude Desktop
- **WHEN** an operator reads the MCP section of `deploy/README.md`
- **THEN** the doc provides a copy-pasteable JSON snippet that registers the local stdio server with Claude Desktop

#### Scenario: Operator follows README to connect remotely
- **WHEN** an operator reads the MCP section of `deploy/README.md`
- **THEN** the doc provides a `claude mcp add` command that points at `https://pesquisa.hacknodes.xyz/mcp/` with bearer auth

### Requirement: REST API v1 remains unchanged in public behaviour

The MCP server SHALL NOT alter the URLs, request shapes, response payloads, or status codes of the REST API v1 endpoints served by `app.py` (excluding the RTT/latency endpoints removed by the `remove-rtt-pipeline` change). The shared `queries/` package SHALL remain transparent to REST consumers.

#### Scenario: REST contract preserved
- **WHEN** a REST client requests `/api/v1/snapshots/`, `/api/v1/nodes/{addr}-{port}/`, `/api/v1/rankings/countries/`, `/api/v1/groups/by-ip/`, or any other surviving v1 endpoint
- **THEN** the response status code, headers, and JSON shape SHALL be identical to the pre-change behaviour (minus the removed `latency_ms` / `median_rtt_ms` fields)

