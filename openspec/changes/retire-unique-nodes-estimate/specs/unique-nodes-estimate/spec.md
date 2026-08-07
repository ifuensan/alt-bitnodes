## REMOVED Requirements

### Requirement: Weighted unique-node estimate from advertised gossip
**Reason**: The computation does not measure what it claims, and what it
claims to measure is not observable. N is read from the crawler's `peer:*`
Redis keys, which cache the response to a `GETADDR` — the addresses a peer
knows about *other* nodes, not its own. N therefore reflects the network
diversity of a node's address book, so a clearnet-only node with a varied
addrman is weighted 1/3 or 1/4 and counted as a fraction of a node,
deflating the estimate silently. Correcting the input would not rescue it:
cross-network deduplication requires linking a node's IPv4 address to its
`.onion` or `.b32.i2p` address, and Bitcoin Core self-advertises through
`GetLocalAddrForPeer()`, which selects an address belonging to the network
of the peer being talked to. The link is never disclosed, by design of Tor
and I2P.

**Migration**: Use the windowed unique-node counts (`windowed-stats`), which
count distinct addresses observed per network over a rolling window and make
no claim to deduplicate machines. Consumers that treated the estimate as a
machine count had a wrong number; there is no corrected value to migrate to.

### Requirement: Unique estimate served with its limitations stated
**Reason**: Removed together with the computation that produced it. A stated
limitation does not repair a metric whose input is the wrong data.

**Migration**: `GET /api/v1/stats/unique-nodes/` and `GET /api/unique-nodes`
are withdrawn. Use `GET /api/v1/stats/window/` for per-network unique counts
over rolling windows.

### Requirement: Estimate is the middle band of the main-page KPI matrix
**Reason**: The band published the invalid estimate as a headline figure
next to two sound ones, which is where it did most damage: read vertically,
it invited the comparison "reachable now vs unique now" that the number
could not support.

**Migration**: The KPI matrix keeps two bands — reachable now, and windowed
unique counts. No replacement band is introduced.

## ADDED Requirements

### Requirement: The withdrawn endpoint explains itself
The public surface is the data, so the explanation SHALL live where a data
consumer meets it: `GET /api/v1/stats/unique-nodes/` SHALL answer 410 Gone
with a body stating that no deduplicated node count is published, why
(reachable addresses are not machines, a node reachable over several
networks contributes one address per network, and the link between a
node's clearnet address and its overlay addresses is not observable), and
naming `GET /api/v1/stats/window/` as the comparable published figure. The
body SHALL NOT promise a future deduplicated count. No dashboard page is
required to carry this explanation; the narrative account belongs in the
project's write-ups.

#### Scenario: Withdrawn endpoint answers a consumer
- **WHEN** a client requests `GET /api/v1/stats/unique-nodes/`
- **THEN** the response is 410 with the reason and the pointer to the
  windowed endpoint

#### Scenario: Legacy endpoint is simply gone
- **WHEN** a client requests `GET /api/unique-nodes`
- **THEN** the route does not exist
