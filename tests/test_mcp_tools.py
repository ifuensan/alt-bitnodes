"""The MCP tools are read-only wrappers over queries/; register them on a
FastMCP instance and call the underlying functions directly."""

import datetime as dt

from mcp.server.fastmcp import FastMCP

from alt_bitnodes_mcp import tools as mcp_tools
from queries import window_stats as ws
from tests.conftest import make_row
from tests.test_archives import ts_at, TODAY


def _registered():
    """Register tools on a FastMCP and return {name: callable}."""
    captured = {}
    mcp = FastMCP("test")
    orig = mcp.tool

    def wrapper(*a, **k):
        deco = orig(*a, **k)

        def take(fn):
            captured[fn.__name__] = fn
            return deco(fn)

        return take

    mcp.tool = wrapper
    mcp_tools.register(mcp)
    return captured


def test_new_tools_registered():
    fns = _registered()
    for name in ("get_window_stats", "get_network_breakdown",
                 "list_archives", "get_archive_url"):
        assert name in fns


def test_network_breakdown(write_snapshot):
    ts = ts_at(TODAY - dt.timedelta(hours=1))
    write_snapshot(ts, [
        make_row(address="1.2.3.4"),
        make_row(address="abc.onion", port=8333),
        make_row(address="abc.b32.i2p", port=0),
    ])
    out = _registered()["get_network_breakdown"]()
    assert out["clearnet"] == 1 and out["tor"] == 1 and out["i2p"] == 1
    assert out["total"] == 3


def test_window_stats_tool(write_snapshot, tmp_path, monkeypatch):
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), [make_row()])
    cache = tmp_path / "window-stats.json"
    monkeypatch.setattr(ws, "WINDOW_STATS_FILE", cache)
    ws.write_window_stats(now=ts_at(TODAY), path=cache)
    out = _registered()["get_window_stats"]()
    assert any(w["total"] == 1 for w in out["windows"])


def test_archive_tools(write_snapshot, archive_dir):
    import archiver
    ts = ts_at(TODAY - dt.timedelta(days=1))
    write_snapshot(ts, [make_row()])
    archiver.run(today=TODAY)
    fns = _registered()
    listing = fns["list_archives"]()
    assert listing["count"] >= 1
    url = fns["get_archive_url"](timestamp=ts, fmt="csv")
    assert url["url"].endswith(f"{ts}.csv")
    assert "error" in fns["get_archive_url"](timestamp=1, fmt="csv")


def test_chart_by_network(write_snapshot):
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)),
                   [make_row(), make_row(address="x.onion", port=8333)])
    out = _registered()["get_chart_data"](chart="by_network")
    assert out["results"]["tor"] == 1 and out["results"]["clearnet"] == 1
