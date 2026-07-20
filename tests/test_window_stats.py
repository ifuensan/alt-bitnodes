import datetime as dt

from queries import window_stats as ws
from tests.conftest import make_row
from tests.test_archives import ts_at, TODAY


def _win(result, days):
    return next(w for w in result["windows"] if w["days"] == days)


def test_empty_when_no_snapshots():
    result = ws.compute_window_stats()
    assert all(w["total"] == 0 and w["snapshots"] == 0 for w in result["windows"])


def test_union_dedupes_across_snapshots(write_snapshot):
    now = ts_at(TODAY)
    # Same node in two snapshots on different days → counted once.
    node = make_row(address="1.2.3.4", port=8333)
    write_snapshot(ts_at(TODAY - dt.timedelta(days=1)), [node])
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=2)), [node])
    w1 = _win(ws.compute_window_stats(now=now), 1)
    assert w1["ipv4"] == 1
    assert w1["snapshots"] == 2


def test_network_classification(write_snapshot):
    now = ts_at(TODAY)
    rows = [
        make_row(address="1.2.3.4", port=8333),
        make_row(address="2001:db8::1", port=8333),
        make_row(address="abc.onion", port=8333),
        make_row(address="abc.b32.i2p", port=8333),
    ]
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), rows)
    w = _win(ws.compute_window_stats(now=now), 1)
    assert (w["ipv4"], w["ipv6"], w["tor"], w["i2p"]) == (1, 1, 1, 1)
    assert w["clearnet"] == 2
    assert w["total"] == 4


def test_window_cutoffs(write_snapshot):
    now = ts_at(TODAY)
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=12)), [make_row(address="1.1.1.1")])
    write_snapshot(ts_at(TODAY - dt.timedelta(days=2)), [make_row(address="2.2.2.2")])
    write_snapshot(ts_at(TODAY - dt.timedelta(days=6)), [make_row(address="3.3.3.3")])
    r = ws.compute_window_stats(now=now)
    assert _win(r, 1)["ipv4"] == 1   # only the 12h-old one
    assert _win(r, 3)["ipv4"] == 2   # 12h + 2d
    assert _win(r, 8)["ipv4"] == 3   # all three


def test_write_and_load_roundtrip(write_snapshot, tmp_path):
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), [make_row()])
    path = tmp_path / "window-stats.json"
    written = ws.write_window_stats(now=ts_at(TODAY), path=path)
    loaded = ws.load_window_stats(path=path)
    assert loaded == written
    assert _win(loaded, 1)["total"] == 1


def test_generated_at_is_set_without_now(write_snapshot):
    # In production the timer calls with now=None; generated_at must still be
    # populated (anchored to the latest snapshot), not null.
    ts = ts_at(TODAY - dt.timedelta(hours=1))
    write_snapshot(ts, [make_row()])
    result = ws.compute_window_stats()  # now=None, like production
    assert result["generated_at"] == ts


def test_load_missing_cache_is_empty(tmp_path):
    assert ws.load_window_stats(path=tmp_path / "nope.json") == {
        "generated_at": None, "windows": []
    }
