## REMOVED Requirements

### Requirement: Fastest-nodes leaderboard
**Reason**: The leaderboard ranked nodes by median RTT, which came from the deleted RTT store. With no RTT data, there is no leaderboard. `GET /api/v1/nodes/leaderboard/` is removed.

**Migration**: API consumers SHALL no longer call `/api/v1/nodes/leaderboard/`; it returns 404. There is no replacement.

## MODIFIED Requirements

### Requirement: Ranking by country
The system SHALL expose `GET /api/v1/rankings/countries/` returning per-country node-count aggregates over the latest snapshot.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/countries/`
- **THEN** the response SHALL be `{"count": N, "results": [{"country", "country_iso3", "total_nodes"}, ...]}` sorted by `total_nodes` descending

### Requirement: Ranking by ASN
The system SHALL expose `GET /api/v1/rankings/asns/` returning per-ASN node-count aggregates with the same shape and ordering rules as the country ranking.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/asns/`
- **THEN** the response SHALL be `{"count": N, "results": [{"asn", "asn_name", "total_nodes"}, ...]}` sorted by `total_nodes` descending

### Requirement: Ranking by user-agent
The system SHALL expose `GET /api/v1/rankings/user-agents/` returning per-UA node-count aggregates with the same shape and ordering rules as the country ranking.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/user-agents/`
- **THEN** the response SHALL be `{"count": N, "results": [{"user_agent", "total_nodes"}, ...]}` sorted by `total_nodes` descending

### Requirement: Same-IP group detail
The system SHALL expose `GET /api/v1/groups/by-ip/{address}/` returning per-port detail for one IP.

#### Scenario: Detail for known address
- **WHEN** a client requests `/api/v1/groups/by-ip/{address}/` for an address present in the latest snapshot
- **THEN** the response SHALL be `{"address", "total_nodes", "nodes": [{"port", "user_agent", "height", "country", "asn"}, ...]}` ordered by `port` ascending

#### Scenario: Detail for unknown address
- **WHEN** the address is not present in the latest snapshot
- **THEN** the response SHALL be HTTP 404
