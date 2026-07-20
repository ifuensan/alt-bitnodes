"""redirect_slashes is disabled so the API never emits a 307 whose Location
leaks the origin hostname. Exact-path routes work; a wrong slash is a clean
404, not a redirect."""

from fastapi.testclient import TestClient

import app as app_module

client = TestClient(app_module.app, follow_redirects=False)


def test_no_307_on_missing_trailing_slash():
    # The v1 route is defined with a trailing slash; without it, no redirect.
    res = client.get("/api/v1/snapshots")
    assert res.status_code == 404
    assert "location" not in {k.lower() for k in res.headers}


def test_exact_paths_still_work():
    assert client.get("/api/snapshots").status_code == 200          # legacy, no slash
    assert client.get("/api/v1/stats/window").status_code == 200    # no slash
    assert client.get("/api/v1/archives/").status_code == 200       # trailing slash
