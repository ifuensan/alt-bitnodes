## ADDED Requirements

### Requirement: RTT samples come from active pings, not passive capture
Per-node RTT samples SHALL be produced by the crawler's active `ping`/`pong` cycle (`ping.py`), not by a passive network-capture pipeline (tcpdump / pcap files / `cache_inv`). The deployment SHALL contain no packet-sniffing component.

#### Scenario: ping.py is the RTT producer
- **WHEN** the crawler sends a `ping` to a peer and receives the matching `pong`
- **THEN** `ping.py` SHALL compute the round-trip time and write it to Redis, so RTT data exists without any pcap capture running

#### Scenario: No sniffer in the deployment
- **WHEN** the crawler stack is deployed and running
- **THEN** there SHALL be no `tcpdump`, pcap file producer, or `cache_inv` process — RTT collection does not depend on, and is not coupled to, network sniffing

### Requirement: RTT Redis contract is unchanged for the dashboard
`ping.py` SHALL write RTT samples to `rtt:<address>-<port>` Redis lists using the same shape, ordering, trim count, and TTL that the previous `cache_inv` producer used, so the dashboard's ingest layer (`rtt-history`) consumes them without modification.

#### Scenario: Dashboard ingest is transparent to the producer swap
- **WHEN** `ping.py` writes RTT samples and the dashboard's ingest cycle runs
- **THEN** samples SHALL be persisted to the dashboard's SQLite store exactly as before, and `latency-api` endpoints SHALL serve non-null `latency_ms` and a populated leaderboard

#### Scenario: Sample list stays bounded
- **WHEN** `ping.py` records a new RTT sample for a node
- **THEN** the `rtt:<address>-<port>` list SHALL be trimmed to the configured count and given the configured TTL, matching the previous producer's behaviour

### Requirement: Block-inv propagation measurement is dropped
With the pcap pipeline removed, the crawler SHALL no longer cache `inv` messages for block/transaction propagation measurement. This is an accepted, explicit trade-off — `alt-bitnodes` exposes no endpoint for that data.

#### Scenario: No inv propagation data is produced
- **WHEN** the crawler stack runs after this change
- **THEN** no `inv:*` propagation keys are produced, and `alt-bitnodes` continues to function because no endpoint consumed them

#### Scenario: Snapshot block height is unaffected
- **WHEN** a snapshot is exported
- **THEN** each node's block height SHALL still be present, sourced as before from the `version` handshake in `crawl.py` — it never depended on the pcap pipeline
