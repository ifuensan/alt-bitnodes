"""Shared fixtures for the queries/ test suite.

queries.config resolves EXPORT_DIR at import time, so BITNODES_EXPORT_DIR
must be set before anything imports `queries`. pytest loads this conftest
before the test modules, which is early enough.
"""

import json
import os
import tempfile
from pathlib import Path

_EXPORT_DIR = Path(tempfile.mkdtemp(prefix="alt-bitnodes-test-export-"))
os.environ["BITNODES_EXPORT_DIR"] = str(_EXPORT_DIR)

import pytest

from queries import config, nodes, snapshots


def make_row(**overrides) -> list:
    """A snapshot row (see config.FIELDS) with sensible defaults."""
    row = {
        "address": "1.2.3.4",
        "port": 8333,
        "protocol_version": 70016,
        "user_agent": "/Satoshi:27.0.0/",
        "timestamp": 1700000000,
        "services": 1033,
        "height": 800000,
        "hostname": "",
        "city": "",
        "country": "US",
        "latitude": 0.0,
        "longitude": 0.0,
        "timezone": "",
        "asn": "AS1",
        "asn_name": "One Networks",
    }
    row.update(overrides)
    return [row[f] for f in config.FIELDS]


@pytest.fixture()
def export_dir() -> Path:
    return _EXPORT_DIR


@pytest.fixture()
def write_snapshot(export_dir):
    def _write(timestamp: int, rows: list) -> int:
        (export_dir / f"{timestamp}.json").write_text(json.dumps(rows))
        return timestamp

    return _write


@pytest.fixture(autouse=True)
def _clean_state(export_dir):
    """Reset snapshot files and every module-level cache between tests."""
    for p in export_dir.iterdir():
        p.unlink()
    snapshots.load_snapshot.cache_clear()
    snapshots.snapshot_meta.cache_clear()
    snapshots._addresses_state["last_ts"] = 0
    snapshots._addresses_state["set"] = set()
    nodes._opendata_cache["ts"] = 0.0
    nodes._opendata_cache["index"] = {}
    yield


class FakeRedis:
    """Minimal stand-in for the two redis calls the data layer makes."""

    def __init__(self):
        self.zsets: dict[str, list[tuple[bytes, float]]] = {}
        self.kv: dict[str, bytes] = {}

    def zrange(self, key, start, end, withscores=False):
        items = self.zsets.get(key, [])
        if withscores:
            return list(items)
        return [member for member, _score in items]

    def get(self, key):
        return self.kv.get(key)


@pytest.fixture()
def fake_redis(monkeypatch) -> FakeRedis:
    fr = FakeRedis()
    monkeypatch.setattr(nodes, "get_redis", lambda: fr)
    return fr
