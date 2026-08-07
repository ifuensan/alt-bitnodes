"""Endpoints for the latent-crawler-data features: propagation and services.
Empty datasets are 200s with empty payloads, never errors."""

from fastapi.testclient import TestClient

import app as app_module
from queries import block_propagation as bp
from tests.conftest import make_row
from tests.test_block_propagation import HASH_A, FakeInvRedis, _zset

client = TestClient(app_module.app)


def test_empty_states_are_200():
    for path in ("/api/propagation", "/api/services",
                 "/api/v1/stats/propagation/", "/api/v1/stats/services/"):
        res = client.get(path)
        assert res.status_code == 200, path
    assert client.get("/api/propagation").json()["blocks"] == []
    assert client.get("/api/services").json()["latest"] is None


def test_unique_nodes_v1_is_gone_with_a_pointer():
    res = client.get("/api/v1/stats/unique-nodes/")
    assert res.status_code == 410
    detail = res.json()["detail"]
    assert detail["alternative"] == "/api/v1/stats/window/"
    assert "not observable" in detail["reason"]


def test_unique_nodes_legacy_route_is_gone():
    assert client.get("/api/unique-nodes").status_code == 404


def test_propagation_served_from_collected_files(data_dir):
    base = 1_000_000_000.0
    fake = FakeInvRedis({f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0), ("x.onion", 500)])})
    bp.collect_propagation(redis_conn=fake, root=bp.PROPAGATION_DIR,
                           now_ms=base + bp.HOT_MS + 1)
    agg = client.get("/api/v1/stats/propagation/").json()
    assert agg["blocks"][0]["hash"] == HASH_A
    assert "first announcement" in agg["definition"]
    block = client.get(f"/api/propagation/block/{HASH_A}").json()
    assert block["networks"]["tor"]["count"] == 1


def test_propagation_block_404s():
    assert client.get(f"/api/propagation/block/{'c' * 64}").status_code == 404
    assert client.get("/api/propagation/block/nothex").status_code == 404


def test_services_endpoint_serves_latest_and_series(write_snapshot):
    write_snapshot(1000, [make_row(services=1 | 2048)])
    payload = client.get("/api/v1/stats/services/").json()
    flags = {f["flag"]: f for f in payload["latest"]["flags"]}
    assert flags["NODE_P2P_V2"]["pct"] == 100.0
    assert payload["series"]["days"] == []
