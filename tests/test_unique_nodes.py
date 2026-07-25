"""unique_nodes: 1/N weighting, composition histogram, persistence."""

import json

from tests.conftest import make_row

from queries import unique_nodes as un


class FakePeerRedis:
    """GET-over-pipeline fake for the peer:* sweep."""

    def __init__(self, kv: dict[str, bytes]):
        self.kv = kv

    def pipeline(self, transaction=True):
        outer = self

        class _Pipe:
            def __init__(self):
                self.keys = []

            def get(self, key):
                self.keys.append(key)

            def execute(self):
                return [outer.kv.get(k) for k in self.keys]

        return _Pipe()


def _gossip(*addresses) -> bytes:
    return json.dumps([[a, 8333, 1, 1700000000] for a in addresses]).encode()


def test_weights_by_advertised_network_types(write_snapshot):
    write_snapshot(1000, [
        make_row(address="1.2.3.4"),
        make_row(address="abc.onion"),
        make_row(address="def.b32.i2p"),
    ])
    fake = FakePeerRedis({
        # advertises ipv4 + tor -> N=2 -> weight 0.5
        "peer:1.2.3.4-8333": _gossip("9.9.9.9", "zzz.onion"),
        # advertises tor + i2p + ipv4 -> N=3 -> weight 1/3
        "peer:abc.onion-8333": _gossip("q.onion", "w.b32.i2p", "8.8.8.8"),
        # no gossip for def.b32.i2p -> N=1 -> weight 1
    })
    est = un.compute_unique_estimate(redis_conn=fake)
    assert est["reachable"] == 3
    assert est["estimate"] == round(0.5 + 1 / 3 + 1.0, 1)
    assert est["clearnet"] == 0.5
    assert est["tor"] == 0.3
    assert est["i2p"] == 1.0
    assert est["composition"] == {"n1": 1, "n2": 1, "n3plus": 1}
    assert "1/N" in est["method"]


def test_malformed_gossip_counts_as_n1(write_snapshot):
    write_snapshot(1000, [make_row(address="1.2.3.4")])
    for raw in (b"not-json", b"null", b"5", b"true", b"{}"):
        fake = FakePeerRedis({"peer:1.2.3.4-8333": raw})
        est = un.compute_unique_estimate(redis_conn=fake)
        assert est["estimate"] == 1.0, raw
        assert est["composition"]["n1"] == 1


def test_per_class_sums_equal_total_after_rounding(write_snapshot):
    # Three N=3 addresses, one per class -> each band weight 1/3. Rounded
    # independently they'd be 0.3+0.3+0.3=0.9 beside a 1.0 total; the fix
    # derives the total from the rounded bands so they always match.
    write_snapshot(1000, [
        make_row(address="1.2.3.4"),
        make_row(address="a.onion"),
        make_row(address="b.b32.i2p"),
    ])
    tri = _gossip("9.9.9.9", "z.onion", "w.b32.i2p")  # ipv4+tor+i2p -> N=3
    fake = FakePeerRedis({
        "peer:1.2.3.4-8333": tri,
        "peer:a.onion-8333": tri,
        "peer:b.b32.i2p-8333": tri,
    })
    est = un.compute_unique_estimate(redis_conn=fake)
    # Consistent at display precision (1 decimal); the bare float sum
    # carries an IEEE-754 artifact (0.3+0.3+0.3 = 0.9000…1).
    assert round(est["clearnet"] + est["tor"] + est["i2p"], 1) == est["estimate"]
    assert est["estimate"] == 0.9  # not the 1.0 an independent round would give


def test_corrupt_snapshot_degrades_to_empty(export_dir):
    (export_dir / "1000.json").write_text("{truncated")
    est = un.compute_unique_estimate(redis_conn=FakePeerRedis({}))
    assert est["estimate"] is None


def test_load_rejects_wrong_shape(data_dir):
    path = data_dir / "unique-nodes.json"
    path.write_text(json.dumps([1, 2, 3]))
    assert un.load_unique_estimate(path=path)["estimate"] is None


def test_empty_snapshot_dir_gives_empty_estimate():
    est = un.compute_unique_estimate(redis_conn=FakePeerRedis({}))
    assert est["estimate"] is None
    assert est["snapshot"] is None


def test_write_and_load_roundtrip(write_snapshot, data_dir):
    write_snapshot(1000, [make_row(address="1.2.3.4")])
    path = data_dir / "unique-nodes.json"
    written = un.write_unique_estimate(path=path, redis_conn=FakePeerRedis({}))
    assert un.load_unique_estimate(path=path) == written


def test_load_missing_file_is_empty(data_dir):
    est = un.load_unique_estimate(path=data_dir / "absent.json")
    assert est["estimate"] is None
