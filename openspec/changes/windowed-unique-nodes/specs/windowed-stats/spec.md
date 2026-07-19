# windowed-stats

## ADDED Requirements

### Requirement: Unique nodes are counted per network over rolling windows

The system SHALL compute, for each configured window (default 1, 3 and 8
days), the count of unique `(address, port)` pairs seen across all snapshots
in that window, split by network type: clearnet (IPv4 + IPv6, reported
separately too), tor (`.onion`), and i2p (`.b32.i2p`). Each window result
SHALL include the number of snapshots it covered and the union total.

#### Scenario: Union across the window
- **WHEN** the windowed compute runs over the snapshots on disk
- **THEN** for each window it reports ipv4/ipv6/tor/i2p unique counts, the
  clearnet and grand totals, and the snapshot count, deduplicating a node
  that appears in many snapshots to a single unit

### Requirement: The windowed counts are precomputed and cached

Because the union reads hundreds of snapshot files, it SHALL be precomputed
by a scheduled job and cached to a JSON file; the API SHALL serve the cached
file rather than computing on request. A missing or unreadable cache SHALL
yield an empty/last-known result, never a slow synchronous recompute in the
request path.

#### Scenario: API serves the cache
- **WHEN** a client requests the windowed counts
- **THEN** the response is served from the cached file without triggering a
  full recompute

#### Scenario: Cache absent
- **WHEN** no cache file exists yet
- **THEN** the endpoint responds with an empty result and a clear indication
  that no windowed data is available yet, not an error or a hang

### Requirement: The dashboard shows instantaneous and windowed totals

The dashboard SHALL present the windowed unique-node totals alongside the
instantaneous snapshot count, so a visitor can see both "reachable now" and
"unique over N days".

#### Scenario: Both figures visible
- **WHEN** windowed data is available
- **THEN** the dashboard shows the N-day unique total next to the
  instantaneous reachable-nodes figure
