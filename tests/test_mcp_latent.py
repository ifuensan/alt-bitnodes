"""MCP tools for the latent-crawler-data features mirror the v1 endpoints."""

from tests.conftest import make_row
from tests.test_block_propagation import HASH_A, FakeInvRedis, _zset
from tests.test_mcp_tools import _registered
from tests.test_unique_nodes import FakePeerRedis, _gossip

from queries import block_propagation as bp
from queries import unique_nodes as un


def test_latent_tools_registered():
    fns = _registered()
    for name in ("get_block_propagation", "get_services_breakdown",
                 "get_unique_nodes_estimate"):
        assert name in fns


def test_empty_states_return_notes_not_errors():
    fns = _registered()
    prop = fns["get_block_propagation"]()
    assert prop["blocks"] == [] and "note" in prop
    services = fns["get_services_breakdown"]()
    assert services["latest"] is None and "note" in services
    unique = fns["get_unique_nodes_estimate"]()
    assert unique["estimate"] is None and "note" in unique


def test_tools_mirror_collected_state(write_snapshot, data_dir):
    fns = _registered()
    write_snapshot(1000, [make_row(address="1.2.3.4", services=1 | 2048)])

    base = 1_000_000_000.0
    fake_inv = FakeInvRedis({f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0)])})
    bp.collect_propagation(redis_conn=fake_inv, root=bp.PROPAGATION_DIR,
                           now_ms=base + bp.HOT_MS + 1)
    un.write_unique_estimate(
        redis_conn=FakePeerRedis({"peer:1.2.3.4-8333": _gossip("9.9.9.9", "z.onion")}))

    assert fns["get_block_propagation"]()["blocks"][0]["hash"] == HASH_A
    flags = {f["flag"]: f for f in fns["get_services_breakdown"]()["latest"]["flags"]}
    assert flags["NODE_P2P_V2"]["pct"] == 100.0
    assert fns["get_unique_nodes_estimate"]()["estimate"] == 0.5
