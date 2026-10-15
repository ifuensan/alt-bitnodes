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


def test_distribution_uses_latest_row_per_node(write_snapshot):
    now = ts_at(TODAY)
    # A node that moved country between sightings is counted once, with
    # the attributes of its most recent sighting.
    old = make_row(address="1.2.3.4", port=8333, country="DE", user_agent="/Satoshi:26.0.0/")
    new = make_row(address="1.2.3.4", port=8333, country="US", user_agent="/Satoshi:27.0.0/")
    other = make_row(address="5.6.7.8", port=8333, country="US", asn="AS2", asn_name="Two")
    write_snapshot(ts_at(TODAY - dt.timedelta(days=2)), [old, other])
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), [new])
    result = ws.compute_window_stats(now=now)
    w3 = _win(result, 3)
    assert w3["total"] == 2
    assert w3["distribution"]["total"] == 2
    assert w3["distribution"]["top_countries"] == [("US", 2)]
    # The superseded user agent of the old sighting is gone; `other` carries
    # the default 27.0.0 agent too.
    assert w3["distribution"]["top_user_agents"] == [("/Satoshi:27.0.0/", 2)]
    assert w3["distribution"]["asns_total"] == 2
    # The 1-day window only holds the fresh sighting.
    w1 = _win(result, 1)
    assert w1["total"] == 1
    assert w1["distribution"]["countries_total"] == 1
    assert w1["since"] == now - ws.DAY_SECONDS


def test_write_splits_nodes_file_and_view_helpers(write_snapshot, tmp_path):
    now = ts_at(TODAY)
    stale = make_row(address="9.9.9.9", port=8333)
    fresh = make_row(address="1.2.3.4", port=8333)
    write_snapshot(ts_at(TODAY - dt.timedelta(days=6)), [stale])
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), [fresh, stale])
    stats_path = tmp_path / "window-stats.json"
    nodes_path = tmp_path / "window-nodes.json"
    data = ws.write_window_stats(now=now, path=stats_path, nodes_path=nodes_path)
    assert "_nodes" not in data
    assert "_nodes" not in ws.load_window_stats(stats_path)
    import pytest
    # A day count the stats cache does not hold is unavailable for nodes too.
    with pytest.raises(ws.WindowMissingError):
        ws.load_window_nodes(2, path=nodes_path, stats_path=stats_path)

    view = ws.window_view_stats(8, path=stats_path)
    assert view["days"] == 8
    assert view["snapshots"] == 2
    assert view["total"] == 2
    assert view["generated_at"] == now
    assert "top_countries" in view
    assert "distribution" not in view

    nodes8 = ws.load_window_nodes(8, path=nodes_path, stats_path=stats_path)
    assert nodes8["count"] == 2
    assert {n["address"] for n in nodes8["nodes"]} == {"1.2.3.4", "9.9.9.9"}
    # The stale node was last seen an hour ago (it was in the fresh snapshot
    # too), so it is in the 1-day window as well; last_seen is the latest.
    nodes1 = ws.load_window_nodes(1, path=nodes_path, stats_path=stats_path)
    assert nodes1["count"] == 2
    assert all(n["last_seen"] == ts_at(TODAY - dt.timedelta(hours=1)) for n in nodes1["nodes"])


def test_nodes_filter_by_last_seen(write_snapshot, tmp_path):
    now = ts_at(TODAY)
    write_snapshot(ts_at(TODAY - dt.timedelta(days=6)), [make_row(address="9.9.9.9")])
    write_snapshot(ts_at(TODAY - dt.timedelta(hours=1)), [make_row(address="1.2.3.4")])
    nodes_path = tmp_path / "window-nodes.json"
    stats_path = tmp_path / "s.json"
    ws.write_window_stats(now=now, path=stats_path, nodes_path=nodes_path)
    assert ws.load_window_nodes(1, path=nodes_path, stats_path=stats_path)["count"] == 1
    assert ws.load_window_nodes(8, path=nodes_path, stats_path=stats_path)["count"] == 2
    import pytest
    with pytest.raises(ws.WindowMissingError):
        ws.load_window_nodes(30, path=nodes_path, stats_path=stats_path)  # wider than the cache


def test_view_helpers_raise_when_cache_missing(tmp_path):
    import pytest
    with pytest.raises(ws.WindowMissingError):
        ws.window_view_stats(8, path=tmp_path / "missing.json")
    with pytest.raises(ws.WindowMissingError):
        ws.load_window_nodes(8, path=tmp_path / "missing.json")


def test_view_rejects_counts_only_cache(tmp_path):
    # Cache format from before the distribution block existed (e.g. the
    # file left on a host across the deploy): the view endpoint must 404.
    import json, pytest
    path = tmp_path / "window-stats.json"
    path.write_text(json.dumps({"generated_at": 1, "windows": [
        {"days": 8, "snapshots": 3, "ipv4": 1, "ipv6": 0, "clearnet": 1,
         "tor": 0, "i2p": 0, "total": 1},
    ]}))
    with pytest.raises(ws.WindowMissingError):
        ws.window_view_stats(8, path=path)
