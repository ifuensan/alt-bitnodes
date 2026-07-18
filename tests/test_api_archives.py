import datetime as dt

from fastapi.testclient import TestClient

import app as app_module
import archiver
from tests.conftest import make_row
from tests.test_archives import TODAY, ts_at

client = TestClient(app_module.app)


def _archive_one(write_snapshot, n=3):
    ts = ts_at(TODAY - dt.timedelta(days=1))
    write_snapshot(ts, [make_row(port=8333 + i) for i in range(n)])
    archiver.run(today=TODAY)
    return ts


def test_empty_listing(archive_dir):
    res = client.get("/api/v1/archives/")
    assert res.status_code == 200
    assert res.json() == {"count": 0, "results": []}


def test_listing_and_csv_download(write_snapshot, archive_dir):
    ts = _archive_one(write_snapshot, n=4)
    listing = client.get("/api/v1/archives/").json()
    assert listing["count"] == 1
    entry = listing["results"][0]
    assert entry["tier"] == "daily"
    assert entry["total_nodes"] == 4

    res = client.get(entry["formats"]["csv"]["url"])
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.headers["cache-control"] == "public, max-age=31536000, immutable"
    lines = res.text.strip().splitlines()
    assert len(lines) == 5  # header + 4 nodes
    assert lines[0].startswith("address,port,")


def test_parquet_download(write_snapshot, archive_dir):
    ts = _archive_one(write_snapshot)
    res = client.get(f"/api/v1/archives/{ts}.parquet")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/vnd.apache.parquet"
    assert res.content[:4] == b"PAR1"


def test_unknown_timestamp_404(archive_dir):
    assert client.get("/api/v1/archives/1234567890.csv").status_code == 404


def test_unknown_format_404(write_snapshot, archive_dir):
    ts = _archive_one(write_snapshot)
    assert client.get(f"/api/v1/archives/{ts}.json").status_code == 404


def test_archive_page_served():
    res = client.get("/archive")
    assert res.status_code == 200
    assert "Pesquisa Archive" in res.text
