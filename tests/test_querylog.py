"""Chat question log: what gets recorded, and that it never breaks a reply."""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from assistant import places, querylog


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:   # runs the lifespan, which loads the assistant
        yield c


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "logs" / "queries.sqlite"
    monkeypatch.setenv("QUERY_LOG_PATH", str(path))
    monkeypatch.setattr(places, "geocode", lambda n: {"name": "Lahore, Pakistan", "lat": 31.5, "lng": 74.3, "tz": "Asia/Karachi"})
    return path


def rows(path):
    querylog.flush()
    if not path.exists():
        return []
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute("SELECT * FROM queries ORDER BY id")]


CF = {"X-Session": "tab-1", "cf-ray": "abc-YYZ", "cf-ipcountry": "PK"}


def test_faq_question_is_recorded(db, client):
    assert client.get("/api/chat", params={"q": "is witr wajib"}, headers=CF).json()["kind"] == "faq"
    [row] = rows(db)
    assert row["query"] == "is witr wajib" and row["kind"] == "faq" and row["faq_id"] == "witr"
    assert row["score"] > 0.5 and row["session"] == "tab-1" and row["country"] == "PK" and row["local"] == 0
    assert row["followup"] == 0 and row["latency_ms"] is not None


def test_times_question_records_prayer_date_and_place(db, client):
    client.get("/api/chat", params={"q": "isha in Lahore on 3 March 2031"}, headers=CF)
    [row] = rows(db)
    assert row["kind"] == "times" and json.loads(row["targets"]) == ["isha"]
    assert row["date"] == "2031-03-03" and row["place"] == "Lahore, Pakistan"


def test_fallback_keeps_suggestions_and_followups_are_flagged(db, client):
    client.get("/api/chat", params={"q": "how to make wudu"})
    prev = json.dumps({"targets": ["asr"], "date": "2026-10-09", "date_label": "tomorrow", "place": None})
    client.get("/api/chat", params={"q": "and on friday?", "prev": prev})
    fb, fu = rows(db)
    assert fb["kind"] == "fallback" and json.loads(fb["suggestions"]) and fb["answer_text"]
    assert fb["local"] == 1 and fb["country"] is None
    assert fu["followup"] == 1 and fu["kind"] == "times"


def test_no_ip_or_user_agent_columns(db, client):
    client.get("/api/chat", params={"q": "fajr time"}, headers={"user-agent": "x"})
    [row] = rows(db)
    assert not {"ip", "user_agent", "ua"} & set(row)


def test_disabled_without_path(monkeypatch, tmp_path, client):
    monkeypatch.delenv("QUERY_LOG_PATH", raising=False)
    assert client.get("/api/chat", params={"q": "fajr time"}).status_code == 200
    assert not list(tmp_path.rglob("*.sqlite"))


def test_unwritable_log_never_breaks_chat(monkeypatch, client):
    monkeypatch.setenv("QUERY_LOG_PATH", "/dev/null/nope/queries.sqlite")
    r = client.get("/api/chat", params={"q": "is witr wajib"})
    assert r.status_code == 200 and r.json()["kind"] == "faq"
