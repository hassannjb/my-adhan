"""Optional sign-in: /api/me reads the searchthehadith.fyi cookie (api/session_cookie.py)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api import session_cookie

SECRET = "shared-test-secret"

# Signed by sunnah-toolkit's core/session_cookie.py (its tests/test_accounts.py
# checks it produces this exact value), so the two copies agree on the format.
FROM_SEARCH_SITE = ("v1.eyJlbWFpbCI6ImFtaW5hQGV4YW1wbGUuY29tIiwiZXhwIjo0MTAyNDQ0ODAwLCJuYW1lIjoiQW1pbmEiLCJzaWQiOiJz"
                    "MSIsInVpZCI6N30.kNCaLIkia46iFR05Q15a4vrDffaps61vbStXoGwCl8I")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    monkeypatch.delenv("AUTH_COOKIE_NAME", raising=False)
    monkeypatch.delenv("AUTH_BASE_URL", raising=False)
    from api.main import app
    return TestClient(app, base_url="https://adhan.searchthehadith.fyi")


def me(client, cookie=None):
    if cookie is not None:
        client.cookies.set("sth_session", cookie, domain=".searchthehadith.fyi")
    r = client.get("/api/me")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    return r.json()


def cookie(**over):
    payload = {"sid": "s1", "uid": 7, "email": "amina@example.com", "name": "Amina", "exp": int(time.time()) + 3600}
    payload.update(over)
    return session_cookie.sign(payload, SECRET)


def test_reads_cookie_from_search_site(client):
    assert me(client, FROM_SEARCH_SITE) == {
        "enabled": True, "auth_base": "https://searchthehadith.fyi",
        "user": {"id": 7, "email": "amina@example.com", "name": "Amina"}}


def test_signed_out(client):
    assert me(client) == {"enabled": True, "user": None, "auth_base": "https://searchthehadith.fyi"}


def test_tampered_cookie_is_ignored(client):
    body, mac = cookie().rsplit(".", 1)
    forged = session_cookie.sign({"sid": "s1", "uid": 1, "email": "admin@example.com", "exp": 4102444800},
                                 "guessed secret")
    assert me(client, body + "." + mac[::-1])["user"] is None
    assert me(client, forged)["user"] is None
    assert me(client, "garbage")["user"] is None


def test_expired_cookie_is_ignored(client):
    assert me(client, cookie(exp=int(time.time()) - 1))["user"] is None


def test_other_purposes_do_not_pass_as_a_session(client):
    oauth_state = session_cookie.sign({"email": "a@example.com", "exp": 4102444800}, SECRET, purpose="oauth")
    assert me(client, oauth_state)["user"] is None


def test_off_without_secret(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    from api.main import app
    c = TestClient(app)
    c.cookies.set("sth_session", FROM_SEARCH_SITE)
    assert c.get("/api/me").json()["enabled"] is False
    assert c.get("/api/me").json()["user"] is None


def test_page_has_sign_in_and_fresh_app_js():
    from pathlib import Path
    html = (Path(__file__).parent.parent / "web" / "index.html").read_text()
    assert "signInUrl()" in html and "/auth/logout" in html
    assert 'src="app.js?v=6"' in html
