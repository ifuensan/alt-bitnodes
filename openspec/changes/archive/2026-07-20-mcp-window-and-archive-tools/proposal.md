# MCP: expose windowed stats, network breakdown, and the archive

## Why

The MCP server is a first-class goal — an agent-facing consultation interface
for the crawler's data. But it was built before I2P, the network breakdown,
the windowed-union metric, and the Parquet/CSV archive existed, so agents
can't query the project's most distinctive data (e.g. "how many unique nodes
over 8 days" or "give me the CSV of last week's snapshot"). This closes the
gap so the MCP surface matches the REST surface.

## What Changes

- New tool `get_window_stats()` → the rolling-window unique-node union
  (1/3/5/8 days, per network), from the cached `/api/v1/stats/window` data.
- New tool `get_network_breakdown()` → clearnet/tor/i2p counts of the latest
  snapshot (the KPI-strip figures).
- New tools `list_archives()` and `get_archive_url(timestamp, fmt)` → the
  tiered Parquet/CSV archive (agents get pointers/URLs, not binary blobs).
- `get_chart_data` gains a `by_network` chart returning the breakdown.

## Capabilities

### New Capabilities

<!-- none -->

### Modified Capabilities
- `mcp-service`: the tool set grows to cover windowed stats, the network
  breakdown, and the archive — matching the REST v1 surface.

## Impact

- `alt_bitnodes_mcp/tools.py` only (read-only wrappers over `queries/`); no
  new deps. The MCP service restarts on deploy (stateless); crawler
  fingerprint untouched.
- Agents/clients gain query access to the windowed metric and archive.
