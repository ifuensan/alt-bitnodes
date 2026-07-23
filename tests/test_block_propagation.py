"""block_propagation: collection, hot-block skip, pruning, aggregate, loading."""

import json

from tests.conftest import make_row

from queries import block_propagation as bp

HASH_A = "a" * 64
HASH_B = "b" * 64


class FakeInvRedis:
    def __init__(self, zsets: dict[str, list[tuple[bytes, float]]]):
        self.zsets = zsets

    def scan_iter(self, match=None, count=None):
        return iter(k.encode() for k in self.zsets)

    def zrange(self, key, start, end, withscores=False):
        items = self.zsets[key.decode() if isinstance(key, bytes) else key]
        assert withscores
        return list(items)


def _zset(base_ms: float, members: list[tuple[str, float]]):
    return [(f"{addr}-8333".encode(), base_ms + rel) for addr, rel in members]


def test_collects_completed_block_with_stats(data_dir):
    base = 1_000_000_000.0
    fake = FakeInvRedis({
        f"binv:{HASH_A}": _zset(base, [
            ("1.2.3.4", 0), ("5.6.7.8", 100), ("abc.onion", 400),
            ("def.b32.i2p", 900),
        ]),
    })
    root = data_dir / "propagation"
    summary = bp.collect_propagation(redis_conn=fake, root=root,
                                     now_ms=base + bp.HOT_MS + 1)
    assert summary["collected"] == 1
    doc = json.loads((root / f"{HASH_A}.json").read_text())
    assert doc["count"] == 4
    assert doc["networks"]["ipv4"]["count"] == 2
    assert doc["networks"]["ipv4"]["p50"] == 50
    assert doc["networks"]["tor"]["ecdf"] == [[400, 1.0]]
    agg = bp.load_propagation(root=root)
    assert len(agg["blocks"]) == 1
    assert agg["blocks"][0]["hash"] == HASH_A
    assert agg["ecdf"]["ipv4"]


def test_hot_block_is_deferred(data_dir):
    base = 1_000_000_000.0
    fake = FakeInvRedis({f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0)])})
    root = data_dir / "propagation"
    summary = bp.collect_propagation(redis_conn=fake, root=root,
                                     now_ms=base + 1000)
    assert summary == {"collected": 0, "skipped_hot": 1, "failed": 0, "pruned": 0}
    assert not (root / f"{HASH_A}.json").exists()


def test_collected_block_not_rewritten(data_dir):
    base = 1_000_000_000.0
    root = data_dir / "propagation"
    fake = FakeInvRedis({f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0)])})
    now = base + bp.HOT_MS + 1
    bp.collect_propagation(redis_conn=fake, root=root, now_ms=now)
    summary = bp.collect_propagation(redis_conn=fake, root=root, now_ms=now)
    assert summary["collected"] == 0


def test_prunes_blocks_older_than_retention(data_dir):
    base = 1_000_000_000.0
    root = data_dir / "propagation"
    fake = FakeInvRedis({f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0)])})
    bp.collect_propagation(redis_conn=fake, root=root, now_ms=base + bp.HOT_MS + 1)
    later = base + (bp.RETENTION_DAYS * 86400 + 10) * 1000
    summary = bp.collect_propagation(redis_conn=FakeInvRedis({}), root=root,
                                     now_ms=later)
    assert summary["pruned"] == 1
    assert bp.load_propagation(root=root)["blocks"] == []


def test_height_estimate_from_first_later_snapshot(write_snapshot, data_dir):
    base_s = 1_000_000
    write_snapshot(base_s - 100, [make_row(height=899_000)])
    write_snapshot(base_s + 60, [make_row(height=900_123)])
    root = data_dir / "propagation"
    fake = FakeInvRedis({
        f"binv:{HASH_B}": _zset(base_s * 1000, [("1.2.3.4", 0)]),
    })
    bp.collect_propagation(redis_conn=fake, root=root,
                           now_ms=base_s * 1000 + bp.HOT_MS + 1)
    doc = bp.load_block(HASH_B, root=root)
    assert doc["height_estimate"] == 900_123


def test_load_block_validates_hash(data_dir):
    root = data_dir / "propagation"
    assert bp.load_block("../../etc/passwd", root=root) is None
    assert bp.load_block("zz" * 32, root=root) is None
    assert bp.load_block(HASH_A, root=root) is None  # not collected


def test_empty_state(data_dir):
    agg = bp.load_propagation(root=data_dir / "propagation")
    assert agg["blocks"] == [] and agg["generated_at"] is None


def test_one_poison_key_does_not_abort_the_sweep(data_dir):
    base = 1_000_000_000.0

    class PoisonRedis(FakeInvRedis):
        def zrange(self, key, start, end, withscores=False):
            if HASH_B in key.decode():
                raise RuntimeError("WRONGTYPE Operation against a key")
            return super().zrange(key, start, end, withscores=withscores)

    fake = PoisonRedis({
        f"binv:{HASH_B}": [],  # poison: zrange raises
        f"binv:{HASH_A}": _zset(base, [("1.2.3.4", 0)]),
    })
    root = data_dir / "propagation"
    summary = bp.collect_propagation(redis_conn=fake, root=root,
                                     now_ms=base + bp.HOT_MS + 1)
    assert summary["failed"] == 1
    assert summary["collected"] == 1  # the good block still landed
    assert bp.load_propagation(root=root)["blocks"]  # aggregate still rebuilt


def test_aggregate_median_weights_blocks_equally(data_dir):
    base = 1_000_000_000.0
    root = data_dir / "propagation"
    # Block A: 3 slow ipv4 announcers; Block B: 3 fast ones. The median
    # curve at each fraction must sit between them, not be dominated by
    # either block's announcer count.
    fake = FakeInvRedis({
        f"binv:{HASH_A}": _zset(base, [("1.1.1.1", 0), ("2.2.2.2", 1000), ("3.3.3.3", 2000)]),
        f"binv:{HASH_B}": _zset(base, [("4.4.4.4", 0), ("5.5.5.5", 10), ("6.6.6.6", 20)]),
    })
    bp.collect_propagation(redis_conn=fake, root=root, now_ms=base + bp.HOT_MS + 1)
    agg = bp.load_propagation(root=root)
    ecdf = agg["ecdf"]["ipv4"]
    assert ecdf, "median curve exists"
    assert ecdf[-1][1] == 1.0
    # At 100% the two blocks reach 2000 and 20; median of two = upper-middle
    assert ecdf[-1][0] in (20, 2000)


def test_load_propagation_rejects_wrong_shape(data_dir):
    root = data_dir / "propagation"
    root.mkdir(parents=True, exist_ok=True)
    (root / "aggregate.json").write_text(json.dumps(["not", "a", "dict"]))
    assert bp.load_propagation(root=root)["blocks"] == []
