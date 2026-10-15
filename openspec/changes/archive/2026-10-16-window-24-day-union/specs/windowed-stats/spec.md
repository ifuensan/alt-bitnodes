## MODIFIED Requirements

### Requirement: Unique nodes are counted per network over rolling windows

The system SHALL compute, for each configured window (1, 3, 5, 8 and 24
days), the count of unique `(address, port)` pairs seen across all snapshots
in that window, split by network type: clearnet (IPv4 + IPv6, reported
separately too), tor (`.onion`), and i2p (`.b32.i2p`). Each window result
SHALL include the number of snapshots it covered and the union total. The
widest window SHALL be bounded by the raw-export retention.

#### Scenario: Union across the window
- **WHEN** the windowed compute runs over the snapshots on disk
- **THEN** for each window it reports ipv4/ipv6/tor/i2p unique counts, the
  clearnet and grand totals, and the snapshot count, deduplicating a node
  that appears in many snapshots to a single unit

#### Scenario: The 24-day window is wider than the 8-day one
- **WHEN** a node's last sighting is 10 days before the reference time
- **THEN** it is counted in the 24-day window and not in the 8-day window
