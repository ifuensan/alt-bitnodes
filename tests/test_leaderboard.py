import pytest

from queries import leaderboard
from queries.leaderboard import (
    NoSnapshotsError,
    SnapshotMissingError,
    group_by_ip_detail,
    groups_by_ip,
    rankings_by_asn,
    rankings_by_country,
    rankings_by_user_agent,
)
from tests.conftest import make_row


def test_no_snapshots_raises():
    with pytest.raises(NoSnapshotsError):
        rankings_by_country()


def test_missing_snapshot_file_raises(monkeypatch):
    monkeypatch.setattr(leaderboard, "list_snapshots", lambda: [123])
    with pytest.raises(SnapshotMissingError):
        rankings_by_country()


def test_uses_latest_snapshot(write_snapshot):
    write_snapshot(100, [make_row(country="US")])
    write_snapshot(200, [make_row(country="DE")])
    results = rankings_by_country()
    assert results == [{"country": "DE", "country_iso3": "DEU", "total_nodes": 1}]


def test_rankings_by_country_sorted_and_skips_empty(write_snapshot):
    rows = [
        make_row(country="US"),
        make_row(port=8334, country="US"),
        make_row(port=8335, country="DE"),
        make_row(port=8336, country=None),
        make_row(port=8337, country=""),
    ]
    write_snapshot(100, rows)
    results = rankings_by_country()
    assert results == [
        {"country": "US", "country_iso3": "USA", "total_nodes": 2},
        {"country": "DE", "country_iso3": "DEU", "total_nodes": 1},
    ]


def test_rankings_by_asn_keeps_first_name(write_snapshot):
    rows = [
        make_row(asn="AS1", asn_name="One Networks"),
        make_row(port=8334, asn="AS1", asn_name="Renamed Later"),
        make_row(port=8335, asn="AS2", asn_name=None),
        make_row(port=8336, asn=None, asn_name=None),
    ]
    write_snapshot(100, rows)
    results = rankings_by_asn()
    assert results == [
        {"asn": "AS1", "asn_name": "One Networks", "total_nodes": 2},
        {"asn": "AS2", "asn_name": "", "total_nodes": 1},
    ]


def test_rankings_by_user_agent(write_snapshot):
    rows = [
        make_row(user_agent="/Satoshi:27.0.0/"),
        make_row(port=8334, user_agent="/Satoshi:27.0.0/"),
        make_row(port=8335, user_agent="/btcd:0.24.0/"),
    ]
    write_snapshot(100, rows)
    results = rankings_by_user_agent()
    assert results[0] == {"user_agent": "/Satoshi:27.0.0/", "total_nodes": 2}
    assert len(results) == 2


def test_groups_by_ip_requires_two_ports(write_snapshot):
    rows = [
        make_row(address="1.1.1.1", port=8334),
        make_row(address="1.1.1.1", port=8333),
        make_row(address="2.2.2.2", port=8333),
        make_row(address="3.3.3.3", port=8333),
        make_row(address="3.3.3.3", port=8334),
        make_row(address="3.3.3.3", port=8335),
    ]
    write_snapshot(100, rows)
    results = groups_by_ip()
    assert results == [
        {"address": "3.3.3.3", "total_nodes": 3, "ports": [8333, 8334, 8335]},
        {"address": "1.1.1.1", "total_nodes": 2, "ports": [8333, 8334]},
    ]


def test_group_by_ip_detail(write_snapshot):
    rows = [
        make_row(address="1.1.1.1", port=8334, user_agent="/b/"),
        make_row(address="1.1.1.1", port=8333, user_agent="/a/"),
        make_row(address="2.2.2.2", port=8333),
    ]
    write_snapshot(100, rows)
    detail = group_by_ip_detail("1.1.1.1")
    assert detail["total_nodes"] == 2
    assert [n["port"] for n in detail["nodes"]] == [8333, 8334]
    assert detail["nodes"][0]["user_agent"] == "/a/"


def test_group_by_ip_detail_unknown_address(write_snapshot):
    write_snapshot(100, [make_row()])
    assert group_by_ip_detail("203.0.113.7") is None
