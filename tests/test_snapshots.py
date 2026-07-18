import pytest

from queries import config
from queries.snapshots import (
    known_addresses_set,
    list_snapshots,
    load_snapshot,
    snapshot_meta,
    snapshot_stats,
    to_dict,
)
from tests.conftest import make_row


def test_list_snapshots_empty(export_dir):
    assert list_snapshots() == []


def test_list_snapshots_sorted_and_filtered(export_dir, write_snapshot):
    write_snapshot(200, [])
    write_snapshot(100, [])
    (export_dir / "notes.json").write_text("[]")
    (export_dir / "300.txt").write_text("[]")
    assert list_snapshots() == [100, 200]


def test_load_snapshot_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_snapshot(999)


def test_load_snapshot_roundtrip(write_snapshot):
    rows = [make_row(), make_row(port=8334)]
    write_snapshot(100, rows)
    assert load_snapshot(100) == rows


def test_snapshot_meta_counts_and_height(write_snapshot):
    rows = [
        make_row(height=800000),
        make_row(port=8334, height=800123),
        make_row(port=8335, height=0),
        make_row(port=8336, height=None),
    ]
    write_snapshot(100, rows)
    assert snapshot_meta(100) == {
        "timestamp": 100,
        "total_nodes": 4,
        "latest_height": 800123,
    }


def test_snapshot_meta_no_valid_heights(write_snapshot):
    write_snapshot(100, [make_row(height=None)])
    assert snapshot_meta(100)["latest_height"] == 0


def test_to_dict_maps_all_fields():
    d = to_dict(make_row(address="8.8.8.8", country="ES"))
    assert d["address"] == "8.8.8.8"
    assert d["country"] == "ES"
    assert list(d.keys()) == config.FIELDS


def test_known_addresses_accumulates_incrementally(write_snapshot):
    write_snapshot(100, [make_row(address="1.1.1.1"), make_row(address="2.2.2.2")])
    assert known_addresses_set() == {("1.1.1.1", 8333), ("2.2.2.2", 8333)}

    # A newer snapshot adds addresses; older ones are kept.
    write_snapshot(200, [make_row(address="3.3.3.3", port=8444)])
    assert known_addresses_set() == {
        ("1.1.1.1", 8333),
        ("2.2.2.2", 8333),
        ("3.3.3.3", 8444),
    }

    # Snapshots older than the high-water mark are not re-scanned.
    write_snapshot(150, [make_row(address="4.4.4.4")])
    assert ("4.4.4.4", 8333) not in known_addresses_set()


def test_snapshot_stats(write_snapshot):
    rows = [
        make_row(country="US", user_agent="/Satoshi:27.0.0/", asn="AS1",
                 asn_name="One", height=100),
        make_row(port=8334, country="US", user_agent="/Satoshi:26.0.0/",
                 asn="AS2", asn_name="Two", height=200),
        make_row(port=8335, country="DE", user_agent="/Satoshi:27.0.0/",
                 asn="AS1", asn_name="One", height=300),
        make_row(port=8336, country=None, user_agent=None, asn=None,
                 asn_name=None, height=None),
        make_row(address="abc.onion", port=8337, country=None, asn="TOR",
                 asn_name="Tor network", height=None),
        make_row(address="abc.b32.i2p", port=8338, country=None, asn="I2P",
                 asn_name="I2P network", height=None),
    ]
    write_snapshot(100, rows)
    stats = snapshot_stats(100)

    assert stats["total"] == 6
    assert stats["countries_total"] == 2
    # Pseudo-ASNs (TOR / I2P) are excluded: ASN stats are clearnet-only.
    assert stats["asns_total"] == 2
    assert not any("TOR" in label or "I2P" in label for label, _ in stats["top_asns"])
    assert stats["user_agents_total"] == 2
    assert stats["median_height"] == 200
    assert stats["top_countries"][0] == ("US", 2)
    assert ("AS1 One", 2) in stats["top_asns"]
    assert ["USA", 2] in stats["countries_iso3"]
    assert ["DEU", 1] in stats["countries_iso3"]
    assert stats["height_histogram"] == {100: 1, 200: 1, 300: 1}
