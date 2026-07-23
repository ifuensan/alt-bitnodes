## ADDED Requirements

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
