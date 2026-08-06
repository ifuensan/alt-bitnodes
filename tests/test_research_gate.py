"""The research page is served only to a caller holding the gate token."""

import pytest
from fastapi.testclient import TestClient

import app as app_module
import research_gate


@pytest.fixture
def client(tmp_path, monkeypatch):
    token_file = tmp_path / "research-token"
    token_file.write_text("s3cr3t\n")
    monkeypatch.setenv("RESEARCH_TOKEN_PATH", str(token_file))
    # https base URL: the gate cookie is Secure, so it is only stored over TLS.
    return TestClient(app_module.app, base_url="https://testserver")


def test_no_token_is_not_found(client):
    """Absent credentials must not reveal that the page exists."""
    assert client.get("/research").status_code == 404


def test_wrong_token_is_not_found(client):
    assert client.get("/research", params={"token": "nope"}).status_code == 404


def test_valid_token_serves_page_and_sets_cookie(client):
    r = client.get("/research", params={"token": "s3cr3t"})
    assert r.status_code == 200
    assert research_gate.COOKIE_NAME in r.cookies


def test_cookie_alone_serves_page(client):
    client.get("/research", params={"token": "s3cr3t"})  # seeds the cookie
    assert client.get("/research").status_code == 200


def test_unconfigured_token_keeps_page_closed(tmp_path, monkeypatch):
    """Fail closed: a missing token file must not open the page."""
    monkeypatch.setenv("RESEARCH_TOKEN_PATH", str(tmp_path / "absent"))
    c = TestClient(app_module.app, base_url="https://testserver")
    assert c.get("/research").status_code == 404
    assert c.get("/research", params={"token": ""}).status_code == 404


def test_empty_token_file_keeps_page_closed(tmp_path, monkeypatch):
    empty = tmp_path / "empty-token"
    empty.write_text("   \n")
    monkeypatch.setenv("RESEARCH_TOKEN_PATH", str(empty))
    c = TestClient(app_module.app, base_url="https://testserver")
    assert c.get("/research", params={"token": ""}).status_code == 404
    assert c.get("/research", params={"token": "   "}).status_code == 404
