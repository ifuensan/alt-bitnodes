import datetime as dt

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

import app as app_module
from queries import archives
from queries.archives import compute_keep, photo_path
from queries.best_union import best_view_stats, load_best_nodes, write_best_union
from queries.config import FIELDS
from queries.window_stats import WindowMissingError
from tests.conftest import make_row
from tests.test_archives import ts_at

client = TestClient(app_module.app)
CUTOFF = dt.date(2026, 7, 26)


def write_photo(archive_dir, tier, ts, rows):
    path = photo_path(tier, ts, "parquet", archive_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({f: [r[i] for r in rows] for i, f in enumerate(FIELDS)}), path)


def test_unions_raw_and_photos_up_to_the_cutoff_day(write_snapshot, archive_dir):
    write_photo(archive_dir, "monthly", ts_at(dt.date(2026, 6, 11)),
                [make_row(address="old.onion", port=8333, country=None, asn="TOR")])
    write_snapshot(ts_at(dt.date(2026, 7, 26), 23),
                   [make_row(address="1.1.1.1"), make_row(address="abc.b32.i2p", port=0)])
    write_snapshot(ts_at(dt.date(2026, 7, 27), 0), [make_row(address="9.9.9.9")])

    out = write_best_union(CUTOFF)

    assert out["as_of"] == "2026-07-26"
    assert out["snapshots"] == 2 and out["sources"] == {"raw": 1, "photos": 1}
    assert (out["ipv4"], out["tor"], out["i2p"], out["total"]) == (1, 1, 1, 3)
    nodes = load_best_nodes()["nodes"]
    assert {n["address"] for n in nodes} == {"1.1.1.1", "old.onion", "abc.b32.i2p"}
    assert "9.9.9.9" not in {n["address"] for n in nodes}


def test_latest_sighting_wins_and_sets_last_seen(write_snapshot, archive_dir):
    early = ts_at(dt.date(2026, 7, 1))
    late = ts_at(dt.date(2026, 7, 20))
    write_photo(archive_dir, "weekly", early, [make_row(address="1.1.1.1", country="DE")])
    write_snapshot(late, [make_row(address="1.1.1.1", country="FR")])

    write_best_union(CUTOFF)

    (node,) = load_best_nodes()["nodes"]
    assert node["country"] == "FR" and node["last_seen"] == late


def test_view_stats_carry_the_distribution(write_snapshot):
    write_snapshot(ts_at(dt.date(2026, 7, 20)), [make_row(address="1.1.1.1", country="DE")])
    write_best_union(CUTOFF)
    stats = best_view_stats()
    assert stats["total"] == 1 and stats["as_of"] == "2026-07-26"
    assert stats["top_countries"][0][0] == "DE"


def test_missing_union_is_a_404_not_an_error():
    with pytest.raises(WindowMissingError):
        best_view_stats()
    with pytest.raises(WindowMissingError):
        load_best_nodes()
    assert client.get("/api/best").status_code == 404
    assert client.get("/api/best/stats").status_code == 404


def test_endpoints_serve_the_frozen_union(write_snapshot):
    write_snapshot(ts_at(dt.date(2026, 7, 20)), [make_row(address="1.1.1.1")])
    write_best_union(CUTOFF)
    stats = client.get("/api/best/stats")
    nodes = client.get("/api/best")
    assert stats.status_code == 200 and stats.json()["total"] == 1
    assert nodes.status_code == 200 and nodes.json()["count"] == 1


def test_pinned_photo_is_kept_when_it_would_rotate(monkeypatch):
    pinned = ts_at(dt.date(2026, 7, 26))
    monkeypatch.setattr(archives, "PINNED_TIMESTAMPS", frozenset({pinned}))
    later = ts_at(dt.date(2026, 7, 29))  # same month: would normally win it
    today = dt.date(2026, 12, 1)         # both are monthly by now
    keep = compute_keep([pinned, later], today)
    assert keep[pinned] == "monthly" and keep[later] == "monthly"


def test_pinned_photo_is_ignored_when_not_archived_yet(monkeypatch):
    pinned = ts_at(dt.date(2026, 7, 26))
    monkeypatch.setattr(archives, "PINNED_TIMESTAMPS", frozenset({pinned}))
    assert compute_keep([], dt.date(2026, 12, 1)) == {}


def test_photo_stands_in_for_an_unreadable_raw_twin(write_snapshot, export_dir, archive_dir):
    ts = ts_at(dt.date(2026, 7, 20))
    (export_dir / f"{ts}.json").write_text("{not json")
    write_photo(archive_dir, "weekly", ts, [make_row(address="1.1.1.1")])

    out = write_best_union(CUTOFF)

    assert out["sources"] == {"raw": 0, "photos": 1}
    assert out["snapshots"] == 1 and out["total"] == 1
