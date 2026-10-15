import datetime as dt

from fastapi.testclient import TestClient

import app as app_module
from queries import window_stats as ws
from tests.conftest import make_row
from tests.test_archives import ts_at, TODAY

client = TestClient(app_module.app)


def test_window_endpoint_empty_when_no_cache():
    # conftest wipes the archive dir but the window cache lives under data/;
    # ensure a missing cache yields an empty, non-error response.
    res = client.get("/api/v1/stats/window")
    assert res.status_code == 200
    assert "windows" in res.json()


def test_window_endpoint_serves_cache(write_snapshot, tmp_path, monkeypatch):
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)),
                   [make_row(address="1.2.3.4"), make_row(address="abc.b32.i2p", port=0)])
    cache = tmp_path / "window-stats.json"
    monkeypatch.setattr(ws, "WINDOW_STATS_FILE", cache)
    ws.write_window_stats(now=ts_at(TODAY), path=cache)

    res = client.get("/api/v1/stats/window")
    assert res.status_code == 200
    w8 = next(w for w in res.json()["windows"] if w["days"] == 8)
    assert w8["ipv4"] == 1 and w8["i2p"] == 1 and w8["total"] == 2


def test_window_view_404_without_cache():
    assert client.get("/api/window/8/stats").status_code == 404
    assert client.get("/api/window/8").status_code == 404


def test_window_view_endpoints_serve_cache(write_snapshot, data_dir):
    write_snapshot(ts_at(TODAY - dt.timedelta(days=2)),
                   [make_row(address="1.2.3.4", country="DE")])
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)),
                   [make_row(address="1.2.3.4", country="US"),
                    make_row(address="abc.onion", port=8333, country=None, asn="TOR", asn_name="Tor")])
    ws.write_window_stats(now=ts_at(TODAY))

    stats = client.get("/api/window/8/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["days"] == 8
    assert body["snapshots"] == 2
    assert body["total"] == 2
    assert body["tor"] == 1
    assert body["clearnet"] == 1
    # Same shape as /api/snapshot/{ts}/stats so the dashboard shares renderers.
    assert body["top_countries"] == [["US", 1]]
    assert body["countries_iso3"] == [["USA", 1]]

    nodes = client.get("/api/window/8")
    assert nodes.status_code == 200
    payload = nodes.json()
    assert payload["count"] == 2
    assert {n["address"] for n in payload["nodes"]} == {"1.2.3.4", "abc.onion"}
    assert all("last_seen" in n for n in payload["nodes"])

    # A 1-day window is served from the same file.
    assert client.get("/api/window/1/stats").json()["total"] == 2
    # Not a configured window → 404, not an error.
    assert client.get("/api/window/30/stats").status_code == 404
    assert client.get("/api/window/30").status_code == 404
