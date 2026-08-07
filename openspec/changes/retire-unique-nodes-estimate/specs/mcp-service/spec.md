## MODIFIED Requirements

### Requirement: Tools expose propagation, services, and unique-node data
The MCP server SHALL provide two additional read-only tools wrapping the
same `queries/` functions as the REST endpoints, with no duplicated
business logic: `get_block_propagation` (aggregate ECDF and recent blocks
with per-class percentiles) and `get_services_breakdown` (latest-snapshot
per-flag breakdown and daily adoption series). The server SHALL NOT expose
a unique-node estimate tool: an agent cannot see a chart caveat, so a tool
returning an unsound number is more dangerous here than on a page.

#### Scenario: Tools registered
- **WHEN** the MCP server starts
- **THEN** `get_block_propagation` and `get_services_breakdown` are
  registered and advertised, and no `get_unique_nodes_estimate` tool is

#### Scenario: Tool results mirror the v1 endpoints
- **WHEN** a client calls one of the two tools
- **THEN** the returned data matches the corresponding
  `/api/v1/stats/...` response for the same underlying state

#### Scenario: No data yet
- **WHEN** a tool is called before the collector has produced its dataset
- **THEN** the tool returns an empty result with an explanatory note, not
  an error
