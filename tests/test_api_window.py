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
