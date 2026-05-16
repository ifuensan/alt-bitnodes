## REMOVED Requirements

### Requirement: latency_ms populated in existing v1 payloads
**Reason**: The RTT data layer (`queries/rtt.py`) is deleted. There is no RTT store to compute a median from, so `latency_ms` is removed from the v1 snapshot and node payloads entirely rather than always being `null`.

**Migration**: API consumers SHALL no longer expect a `latency_ms` field in `/api/v1/snapshots/*` or `/api/v1/nodes/{node_id}/` payloads. The field is gone, not nulled. This is an explicit, accepted loss of bitnodes.io parity for latency.

### Requirement: Per-node latency time series endpoint
**Reason**: With no RTT store, there is no time series to serve. `GET /api/v1/nodes/{node_id}/rtt/` is removed.

**Migration**: API consumers SHALL no longer call `/api/v1/nodes/{node_id}/rtt/`; it returns 404. There is no replacement.

### Requirement: V1_NOTE no longer claims latency is null
**Reason**: This requirement only made sense while `latency-api` was a planned-but-unimplemented capability. The capability is now removed, so the note about `latency_ms` is removed along with the field itself.

**Migration**: No action. The OpenAPI schema no longer mentions `latency_ms` at all.
