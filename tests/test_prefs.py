"""Settings sync: /api/prefs keeps one JSON object per signed-in account (api/prefs.py)."""
from __future__ import annotations

import importlib
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from api import session_cookie

SECRET = "shared-test-secret"
SITE = "https://adhan.searchthehadith.fyi"
SAME = {"Origin": SITE}
GOOD = {"method": "Karachi", "fajrAngle": 18, "ishaAngle": 17.5, "audioFile": "fajr"}


def cookie(uid=7, **over):
    payload = {"sid": "s1", "uid": uid, "email": "amina@example.com", "name": "Amina", "exp": int(time.time()) + 3600}
    payload.update(over)
    return session_cookie.sign(payload, SECRET)


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "data" / "prefs.sqlite"
    monkeypatch.setenv("AUTH_SECRET", SECRET)
    monkeypatch.setenv("PREFS_DB_PATH", str(path))
    for name in ("AUTH_COOKIE_NAME", "PREFS_ALLOWED_ORIGINS", "RATE_LIMIT_PREFS_PER_MIN"):
        monkeypatch.delenv(name, raising=False)
    return path


def client(uid=7):
    from api.main import app
    c = TestClient(app, base_url=SITE)
    if uid is not None:
        c.cookies.set("sth_session", cookie(uid), domain=".searchthehadith.fyi")
    return c


def test_anonymous_gets_401(db):
    c = client(uid=None)
    assert c.get("/api/prefs").status_code == 401
    assert c.put("/api/prefs", json=GOOD, headers=SAME).status_code == 401
    c.cookies.set("sth_session", "v1.forged.cookie", domain=".searchthehadith.fyi")
    assert c.get("/api/prefs").status_code == 401


def test_round_trip(db):
    c = client()
    r = c.get("/api/prefs")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"enabled": True, "prefs": None, "updated_at": None}

    r = c.put("/api/prefs", json=GOOD, headers=SAME)
    assert r.status_code == 200 and r.json()["prefs"] == GOOD
    first = r.json()["updated_at"]

    got = c.get("/api/prefs").json()
    assert got["prefs"] == GOOD and got["updated_at"] == first

    # A PUT replaces the whole object, and moves updated_at on.
    c.put("/api/prefs", json={"method": "Turkey"}, headers=SAME)
    got = c.get("/api/prefs").json()
    assert got["prefs"] == {"method": "Turkey"} and got["updated_at"] >= first

    # Another account sees only its own.
    assert client(uid=8).get("/api/prefs").json()["prefs"] is None

    rows = sqlite3.connect(db).execute("SELECT uid, updated_at FROM prefs").fetchall()
    assert [r[0] for r in rows] == ["7"] and rows[0][1] == got["updated_at"]


@pytest.mark.parametrize("body", [
    {"theme": "dark"},                                 # unknown key
    {"method": "Made Up"},
    {"method": 3},
    {"fajrAngle": "18"},                              # string, not a number
    {"fajrAngle": True},
    {"ishaAngle": 95},                                # out of range
    {"ishaAngle": -1},
    {"audioFile": "makkah.mp3"},
    ["method", "Karachi"],                            # not an object
])
def test_rejects_bad_settings(db, body):
    c = client()
    r = c.put("/api/prefs", json=body, headers=SAME)
    assert r.status_code == 400 and r.json()["error"]
    assert c.get("/api/prefs").json()["prefs"] is None


def test_rejects_non_json_and_oversize(db):
    c = client()
    r = c.put("/api/prefs", content=b"{not json", headers={**SAME, "Content-Type": "application/json"})
    assert r.status_code == 400
    big = '{"method": "Karachi", "pad": "' + "x" * 5000 + '"}'
    r = c.put("/api/prefs", content=big.encode(), headers={**SAME, "Content-Type": "application/json"})
    assert r.status_code == 413
    assert c.get("/api/prefs").json()["prefs"] is None


def test_put_needs_our_origin(db, monkeypatch):
    c = client()
    assert c.put("/api/prefs", json=GOOD).status_code == 403
    assert c.put("/api/prefs", json=GOOD, headers={"Origin": "https://evil.example"}).status_code == 403
    assert c.put("/api/prefs", json=GOOD, headers={"Origin": "null"}).status_code == 403
    assert c.put("/api/prefs", json=GOOD, headers={"Referer": SITE + "/?x=1"}).status_code == 200
    assert c.put("/api/prefs", json=GOOD, headers={"Origin": "https://ADHAN.searchthehadith.fyi"}).status_code == 200

    monkeypatch.setenv("PREFS_ALLOWED_ORIGINS", "http://localhost:8000, https://adhan.searchthehadith.fyi")
    assert c.put("/api/prefs", json=GOOD, headers={"Origin": "http://localhost:8000"}).status_code == 200


def test_off_without_db_path(db, monkeypatch):
    monkeypatch.delenv("PREFS_DB_PATH")
    c = client()
    r = c.get("/api/prefs")
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = c.put("/api/prefs", json=GOOD, headers=SAME)
    assert r.status_code == 503 and r.json()["enabled"] is False
    assert client(uid=None).get("/api/prefs").json()["enabled"] is False
    assert not db.exists()


def test_rate_limited_per_account(db, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PREFS_PER_MIN", "2")
    import api.main
    main = importlib.reload(api.main)
    try:
        c = TestClient(main.app, base_url=SITE)
        c.cookies.set("sth_session", cookie(7), domain=".searchthehadith.fyi")
        codes = [c.put("/api/prefs", json=GOOD, headers=SAME).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert int(c.get("/api/prefs").headers["retry-after"]) > 0
    finally:
        monkeypatch.delenv("RATE_LIMIT_PREFS_PER_MIN")
        importlib.reload(api.main)


def test_page_syncs_the_same_keys_the_server_allows():
    import re
    from pathlib import Path
    from api import prefs
    js = (Path(__file__).parent.parent / "web" / "app.js").read_text()
    keys = re.search(r"const SYNCED_KEYS = \[([^\]]*)\]", js).group(1)
    assert sorted(re.findall(r"'(\w+)'", keys)) == sorted(prefs.ALLOWED)
