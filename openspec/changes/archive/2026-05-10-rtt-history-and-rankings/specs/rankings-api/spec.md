## ADDED Requirements

### Requirement: Fastest-nodes leaderboard
The system SHALL expose `GET /api/v1/leaderboard/` returning the top-N nodes by lowest median RTT within the configured latency window, with optional country and ASN filters.

#### Scenario: Default leaderboard
- **WHEN** a client requests `/api/v1/leaderboard/` with no query parameters
- **THEN** the response SHALL be `{"count": N, "results": [{"address", "port", "country", "asn", "asn_name", "user_agent", "latency_ms"}, ...]}` containing up to 50 entries, sorted by `latency_ms` ascending, where every entry has a non-null `latency_ms`.

#### Scenario: Country filter
- **WHEN** a client passes `?country=US` (ISO-2)
- **THEN** the response SHALL contain only nodes whose latest-snapshot country matches `US`.

#### Scenario: ASN filter
- **WHEN** a client passes `?asn=AS13335`
- **THEN** the response SHALL contain only nodes whose latest-snapshot ASN matches `AS13335`.

#### Scenario: Limit parameter
- **WHEN** a client passes `?limit=K` with `1 <= K <= 500`
- **THEN** the response SHALL contain at most `K` entries.

#### Scenario: Limit out of range
- **WHEN** a client passes `?limit=0` or `?limit=1000`
- **THEN** the response SHALL be HTTP 422 with a description of the allowed range (FastAPI default for query-parameter validation errors).

### Requirement: Ranking by country
The system SHALL expose `GET /api/v1/rankings/countries/` returning per-country aggregates over the latest snapshot joined with the latency window.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/countries/`
- **THEN** the response SHALL be `{"count": N, "results": [{"country", "country_iso3", "total_nodes", "median_rtt_ms"}, ...]}` sorted by `total_nodes` descending, where `median_rtt_ms` is `null` for countries whose nodes have no samples in the window.

### Requirement: Ranking by ASN
The system SHALL expose `GET /api/v1/rankings/asns/` returning per-ASN aggregates with the same shape and ordering rules as the country ranking.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/asns/`
- **THEN** the response SHALL be `{"count": N, "results": [{"asn", "asn_name", "total_nodes", "median_rtt_ms"}, ...]}` sorted by `total_nodes` descending.

### Requirement: Ranking by user-agent
The system SHALL expose `GET /api/v1/rankings/user-agents/` returning per-UA aggregates with the same shape and ordering rules as the country ranking.

#### Scenario: Default ranking
- **WHEN** a client requests `/api/v1/rankings/user-agents/`
- **THEN** the response SHALL be `{"count": N, "results": [{"user_agent", "total_nodes", "median_rtt_ms"}, ...]}` sorted by `total_nodes` descending.

### Requirement: Same-IP group listing
The system SHALL expose `GET /api/v1/groups/by-ip/` listing IP addresses that host more than one node in the latest snapshot.

#### Scenario: Group listing
- **WHEN** a client requests `/api/v1/groups/by-ip/`
- **THEN** the response SHALL be `{"count": N, "results": [{"address", "total_nodes", "ports": [int, ...]}, ...]}` containing only addresses with `total_nodes >= 2`, sorted by `total_nodes` descending.

### Requirement: Same-IP group detail
The system SHALL expose `GET /api/v1/groups/by-ip/{address}/` returning per-port detail for one IP.

#### Scenario: Detail for known address
- **WHEN** a client requests `/api/v1/groups/by-ip/{address}/` for an address present in the latest snapshot
- **THEN** the response SHALL be `{"address", "total_nodes", "nodes": [{"port", "user_agent", "height", "country", "asn", "latency_ms"}, ...]}` ordered by `port` ascending.

#### Scenario: Detail for unknown address
- **WHEN** the address is not present in the latest snapshot
- **THEN** the response SHALL be HTTP 404.
