"""
Append-only log of chat questions, kept for later analysis.

Off unless QUERY_LOG_PATH is set (run-hf.sh on the MBP sets it), so tests
and local runs write nothing. Rows are written by one background thread; a
failure to log is reported and swallowed, never raised into a request.

No IP addresses or user agents are stored: only an anonymous per-tab session
id sent by the page and Cloudflare's country code.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id          INTEGER PRIMARY KEY,
    ts          TEXT NOT NULL,     -- UTC, ISO 8601, when the question arrived
    local       INTEGER NOT NULL,  -- 1 = did not come through Cloudflare (tests, local runs)
    session     TEXT,              -- random id per browser tab
    country     TEXT,              -- Cloudflare CF-IPCountry, e.g. CA
    query       TEXT NOT NULL,
    followup    INTEGER NOT NULL,  -- 1 = sent with the previous times answer ("and tomorrow?")
    kind        TEXT,              -- faq | times | convert | fallback | error
    faq_id      TEXT,              -- matched answer id (faq)
    score       REAL,              -- match score (faq)
    suggestions TEXT,              -- JSON list offered on a fallback
    targets     TEXT,              -- JSON prayers asked for (times)
    date        TEXT,              -- date asked for (times), YYYY-MM-DD
    place       TEXT,              -- city asked for (times), as resolved
    answer_text TEXT,              -- reply text for convert / fallback / error
    latency_ms  INTEGER,
    error       TEXT               -- server exception, if any
);
CREATE INDEX IF NOT EXISTS queries_ts ON queries(ts);
"""

_COLUMNS = ("ts", "local", "session", "country", "query", "followup", "kind", "faq_id", "score",
            "suggestions", "targets", "date", "place", "answer_text", "latency_ms", "error")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def connect(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


class _Writer:
    def __init__(self, path: str) -> None:
        self.path = path
        self.q: queue.Queue = queue.Queue(maxsize=10_000)
        threading.Thread(target=self._run, name="querylog", daemon=True).start()

    def _run(self) -> None:
        try:
            conn = connect(self.path)
        except Exception as e:
            logger.warning("query log disabled, cannot open %s: %s", self.path, e)
            return
        sql = (f"INSERT INTO queries ({', '.join(_COLUMNS)}) "
               f"VALUES ({', '.join('?' for _ in _COLUMNS)})")
        while True:
            row = self.q.get()
            try:
                conn.execute(sql, [row.get(c) for c in _COLUMNS])
                conn.commit()
            except Exception as e:
                logger.warning("query log write failed: %s", e)
            finally:
                self.q.task_done()


_writer: _Writer | None = None
_lock = threading.Lock()


def _get_writer() -> _Writer | None:
    global _writer
    path = os.environ.get("QUERY_LOG_PATH", "").strip()
    if not path:
        return None
    with _lock:
        if _writer is None or _writer.path != path:
            _writer = _Writer(path)
        return _writer


def flush() -> None:
    """Block until queued rows are written (tests use this)."""
    if _writer is not None:
        _writer.q.join()


def record(*, started: str, query: str, reply: dict[str, Any] | None, headers, followup: bool,
           latency_ms: float, error: str | None = None) -> None:
    """Queue one row. Never raises."""
    try:
        writer = _get_writer()
        if writer is None:
            return

        def clean(v, n=64):
            return v.strip()[:n] if v and v.strip() else None

        reply = reply or {}
        kind = reply.get("kind")
        place = reply.get("place") or {}
        row = {
            "ts": started,
            "local": 0 if headers.get("cf-ray") else 1,
            "session": clean(headers.get("x-session")),
            "country": clean(headers.get("cf-ipcountry"), 8),
            "query": query,
            "followup": int(followup),
            "kind": kind,
            "faq_id": reply.get("id") if kind == "faq" else None,
            "score": reply.get("score") if kind == "faq" else None,
            "suggestions": json.dumps(reply["suggestions"]) if reply.get("suggestions") else None,
            "targets": json.dumps(reply["targets"]) if kind == "times" else None,
            "date": reply.get("date") if kind == "times" else None,
            "place": place.get("name") if kind == "times" else None,
            "answer_text": reply.get("text") if kind in ("convert", "fallback", "error") else None,
            "latency_ms": int(latency_ms),
            "error": error,
        }
        writer.q.put_nowait(row)
    except Exception as e:
        logger.warning("query log record failed: %s", e)
