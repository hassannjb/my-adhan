"""Chat rate limit (assistant/ratelimit.py) and the Nominatim throttle."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from assistant import places, ratelimit


def test_sliding_window():
    w = ratelimit.SlidingWindow(2, window=60)
    assert w.hit("a", now=0) == 0 and w.hit("a", now=1) == 0
    assert w.hit("a", now=2) == 58
    assert w.hit("b", now=2) == 0
    assert w.hit("a", now=60.5) == 0


def test_chat_limit_per_cloudflare_ip(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_CHAT_PER_MIN", "2")
    import api.main
    main = importlib.reload(api.main)
    with TestClient(main.app) as c:
        a, b = {"cf-connecting-ip": "203.0.113.1"}, {"cf-connecting-ip": "203.0.113.2"}
        codes = [c.get("/api/chat", params={"q": "is witr wajib"}, headers=a).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        r = c.get("/api/chat", params={"q": "is witr wajib"}, headers=a)
        assert "Try again" in r.json()["error"] and int(r.headers["retry-after"]) > 0
        assert c.get("/api/chat", params={"q": "is witr wajib"}, headers=b).status_code == 200
    monkeypatch.delenv("RATE_LIMIT_CHAT_PER_MIN")
    importlib.reload(api.main)


def test_geocode_waits_a_second_between_calls(monkeypatch):
    calls = []

    class R:
        def raise_for_status(self): pass
        def json(self): return []

    monkeypatch.setattr(places.requests, "get", lambda *a, **k: calls.append(places.time.monotonic()) or R())
    places.geocode.cache_clear()
    places.geocode("Nowhere One")
    places.geocode("Nowhere Two")
    assert calls[1] - calls[0] >= 0.99
