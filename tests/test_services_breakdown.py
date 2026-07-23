"""services_breakdown: bitmask decoding, per-snapshot stats, daily series."""

import datetime as dt
import json

from tests.conftest import make_row

import queries.services as sb


def test_decode_services_named_bits():
    # 3081 = NETWORK(1) + WITNESS(8) + NETWORK_LIMITED(1024) + P2P_V2(2048)
    assert sb.decode_services(3081) == [
        "NODE_NETWORK", "NODE_WITNESS", "NODE_NETWORK_LIMITED", "NODE_P2P_V2",
    ]
    assert sb.decode_services(0) == []
    assert sb.decode_services("garbage") == []


def test_breakdown_counts_and_networks(write_snapshot):
    ts = write_snapshot(1000, [
        make_row(address="1.2.3.4", services=1 | 8),
        make_row(address="abc.onion", services=1 | 2048),
        make_row(address="def.b32.i2p", services=1),
        make_row(address="2001:db8::1", services=8),
    ])
    b = sb.services_breakdown(ts)
    flags = {f["flag"]: f for f in b["flags"]}
    assert b["total"] == 4
    assert flags["NODE_NETWORK"]["count"] == 3
    assert flags["NODE_NETWORK"]["by_network"] == {
        "ipv4": 1, "ipv6": 0, "tor": 1, "i2p": 1,
    }
    assert flags["NODE_WITNESS"]["count"] == 2
    assert flags["NODE_P2P_V2"]["count"] == 1
    assert flags["NODE_P2P_V2"]["pct"] == 25.0


def test_breakdown_unknown_bits_surface_in_other(write_snapshot):
    unknown = 1 << 26
    ts = write_snapshot(1000, [
        make_row(address="1.2.3.4", services=1 | unknown),
        make_row(address="5.6.7.8", services=1),
    ])
    b = sb.services_breakdown(ts)
    assert b["other"]["count"] == 1
    assert b["other"]["masks"] == {str(unknown): 1}


def _day_ts(date: dt.date, hour: int) -> int:
    return int(dt.datetime(date.year, date.month, date.day, hour,
                           tzinfo=dt.timezone.utc).timestamp())


def test_series_samples_last_snapshot_per_complete_day(write_snapshot, data_dir):
    today = dt.date(2026, 7, 23)
    d1, d2 = dt.date(2026, 7, 21), dt.date(2026, 7, 22)
    write_snapshot(_day_ts(d1, 3), [make_row(services=1)])
    write_snapshot(_day_ts(d1, 20), [make_row(services=1 | 2048)])  # last of d1
    write_snapshot(_day_ts(d2, 12), [make_row(services=1)])
    write_snapshot(_day_ts(today, 1), [make_row(services=1)])  # today: excluded

    series = sb.refresh_services_series(today=today)
    assert [d["date"] for d in series["days"]] == ["2026-07-21", "2026-07-22"]
    assert series["days"][0]["flags"]["NODE_P2P_V2"] == 100.0
    assert series["days"][1]["flags"]["NODE_P2P_V2"] == 0.0


def test_series_keeps_existing_days_and_skips_missing(write_snapshot, data_dir):
    today = dt.date(2026, 7, 23)
    path = data_dir / "services-series.json"
    path.write_text(json.dumps({
        "generated_at": 1,
        "days": [{"date": "2026-07-20", "timestamp": 1, "total": 5,
                  "flags": {"NODE_P2P_V2": 40.0}}],
    }))
    # 2026-07-21 has no snapshots (pruned) -> absent, no interpolation.
    write_snapshot(_day_ts(dt.date(2026, 7, 22), 12), [make_row(services=2048)])
    series = sb.refresh_services_series(path=path, today=today)
    assert [d["date"] for d in series["days"]] == ["2026-07-20", "2026-07-22"]
    assert series["days"][0]["flags"]["NODE_P2P_V2"] == 40.0


def test_latest_payload_empty_state():
    payload = sb.latest_services_payload()
    assert payload["latest"] is None
    assert payload["series"]["days"] == []


def test_derived_pruned_is_limited_without_network(write_snapshot):
    ts = write_snapshot(1000, [
        make_row(address="1.2.3.4", services=1024),        # truly pruned
        make_row(address="5.6.7.8", services=1 | 1024),    # full node, BIP159
        make_row(address="9.9.9.9", services=1),
    ])
    b = sb.services_breakdown(ts)
    assert b["derived"]["pruned"] == {"count": 1, "pct": 33.33}
    flags = {f["flag"]: f for f in b["flags"]}
    assert flags["NODE_NETWORK_LIMITED"]["count"] == 2  # raw flag unchanged


def test_corrupt_latest_snapshot_degrades_to_empty(export_dir, write_snapshot):
    write_snapshot(1000, [make_row()])
    (export_dir / "2000.json").write_text("{truncated")
    payload = sb.latest_services_payload()
    assert payload["latest"] is None


def test_corrupt_day_snapshot_skipped_in_series(export_dir, data_dir):
    today = dt.date(2026, 7, 23)
    good = _day_ts(dt.date(2026, 7, 21), 12)
    bad = _day_ts(dt.date(2026, 7, 22), 12)
    (export_dir / f"{good}.json").write_text(json.dumps([make_row(services=1)]))
    (export_dir / f"{bad}.json").write_text("{truncated")
    series = sb.refresh_services_series(today=today)
    assert [d["date"] for d in series["days"]] == ["2026-07-21"]


def test_malformed_series_entries_dropped_on_load(data_dir):
    path = data_dir / "services-series.json"
    path.write_text(json.dumps({"generated_at": 1, "days": [
        {"date": "2026-07-20", "timestamp": 1, "total": 5, "flags": {}},
        {"no_date": True}, "garbage", 42,
    ]}))
    series = sb.load_services_series(path)
    assert [d["date"] for d in series["days"]] == ["2026-07-20"]
