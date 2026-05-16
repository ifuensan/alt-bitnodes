## REMOVED Requirements

### Requirement: Persistent RTT sample store
**Reason**: The `rtt:*` Redis lists this store ingested are no longer consumed by anything in `alt-bitnodes`. With the pcap pipeline gone and RTT removed from the API, MCP and frontend, there is no reader for a persistent RTT store. `queries/rtt.py` and `data/rtt.sqlite` are deleted.

**Migration**: No action for API consumers. Operators SHOULD delete the now-orphaned `data/rtt.sqlite` file once.

### Requirement: Bounded retention
**Reason**: The retention pass operated on the RTT store, which no longer exists.

**Migration**: None. The retention task is removed along with the store.

### Requirement: Ingest cadence is shorter than upstream TTL
**Reason**: There is no ingest task — nothing reads the upstream `rtt:*` lists into a local store anymore.

**Migration**: None.

### Requirement: Ingest can be disabled for read replicas
**Reason**: The ingest task is removed entirely, so the `RTT_INGEST_ENABLED` flag that toggled it is also removed.

**Migration**: Operators SHOULD remove any `RTT_INGEST_ENABLED` / `RTT_INGEST_INTERVAL_SECONDS` environment variables from systemd units or config — they are no longer read.
