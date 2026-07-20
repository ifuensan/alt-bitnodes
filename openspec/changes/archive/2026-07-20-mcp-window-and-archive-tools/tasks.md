# Tasks — mcp-window-and-archive-tools

## 1. Implementation

- [x] 1.1 `tools.py`: add `get_window_stats()` (wraps `load_window_stats`)
      and `get_network_breakdown()` (from `snapshot_stats` clearnet/tor/i2p).
- [x] 1.2 `tools.py`: add `list_archives()` and `get_archive_url(timestamp, fmt)`
      (wrap `list_archives`/`find_archive_file`; return URLs, not blobs).
- [x] 1.3 `tools.py`: extend `get_chart_data` with a `by_network` chart.
- [x] 1.4 Tests: register the tools on a FastMCP instance and assert each
      returns the expected shape (with fixture snapshots + a window cache).

## 2. Deploy

- [x] 2.1 Commit, push, CI green, "Crawler unchanged" in deploy log.
- [x] 2.2 Verify on production: MCP lists the new tools and they return data.

## 3. Bookkeeping

- [x] 3.1 Archive change, sync `mcp-service` spec.
