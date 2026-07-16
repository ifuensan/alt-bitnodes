import json

import pytest
import redis

from queries import nodes
from queries.nodes import node_status, opendata_index, parse_node_id
from tests.conftest import make_row


def _opendata_entry(addr="1.2.3.4", port=8333, proto=70016,
                    ua="/Satoshi:27.0.0/", last_seen=1700000000, services=1033,
                    score=1700000000.0):
    raw = json.dumps([addr, port, proto, ua, last_seen, services]).encode()
    return (raw, score)


class TestParseNodeId:
    def test_ipv4(self):
        assert parse_node_id("1.2.3.4-8333") == ("1.2.3.4", 8333)

    def test_ipv6_brackets_stripped(self):
        assert parse_node_id("[2001:db8::1]-8333") == ("2001:db8::1", 8333)

    def test_onion(self):
        addr = "abcdef0123456789.onion"
        assert parse_node_id(f"{addr}-8333") == (addr, 8333)

    def test_missing_dash_raises(self):
        with pytest.raises(ValueError):
            parse_node_id("1.2.3.4")

    def test_non_numeric_port_raises(self):
        with pytest.raises(ValueError):
            parse_node_id("1.2.3.4-abc")


class TestOpendataIndex:
    def test_parses_entries(self, fake_redis):
        fake_redis.zsets["opendata"] = [_opendata_entry()]
        index = opendata_index()
        data, score = index["1.2.3.4:8333"]
        assert data[3] == "/Satoshi:27.0.0/"
        assert score == 1700000000.0

    def test_skips_malformed_entries(self, fake_redis):
        fake_redis.zsets["opendata"] = [
            (b"not json", 1.0),
            (json.dumps({"addr": "x"}).encode(), 1.0),  # not a list
            (json.dumps(["only-addr"]).encode(), 1.0),  # too short
            _opendata_entry(addr="5.6.7.8"),
        ]
        index = opendata_index()
        assert list(index) == ["5.6.7.8:8333"]

    def test_result_is_cached_within_ttl(self, fake_redis):
        fake_redis.zsets["opendata"] = [_opendata_entry()]
        opendata_index()
        fake_redis.zsets["opendata"] = [_opendata_entry(addr="9.9.9.9")]
        assert "1.2.3.4:8333" in opendata_index()

    def test_redis_error_returns_empty(self, fake_redis, monkeypatch):
        def boom(*args, **kwargs):
            raise redis.RedisError("down")

        monkeypatch.setattr(fake_redis, "zrange", boom)
        assert opendata_index() == {}


class TestNodeStatus:
    def test_up_node(self, fake_redis):
        fake_redis.zsets["opendata"] = [_opendata_entry()]
        fake_redis.kv["height:1.2.3.4-8333-1033"] = b"800123"
        status = node_status("1.2.3.4", 8333)
        assert status == {
            "address": "1.2.3.4",
            "status": "UP",
            "data": [70016, "/Satoshi:27.0.0/", 1700000000, 800123],
        }

    def test_up_node_without_height(self, fake_redis):
        fake_redis.zsets["opendata"] = [_opendata_entry()]
        status = node_status("1.2.3.4", 8333)
        assert status["data"][3] is None

    def test_down_node_known_from_snapshots(self, fake_redis, write_snapshot):
        write_snapshot(100, [make_row(address="9.9.9.9", port=8333)])
        status = node_status("9.9.9.9", 8333)
        assert status == {
            "address": "9.9.9.9",
            "status": "DOWN",
            "data": [None, None, None, None],
        }

    def test_unknown_node_returns_none(self, fake_redis):
        assert node_status("203.0.113.7", 8333) is None
