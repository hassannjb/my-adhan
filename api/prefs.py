"""
Settings saved per signed-in user, so they follow the user to other devices.

Off unless PREFS_DB_PATH is set (run-hf.sh on the MBP sets it); then
/api/prefs answers {"enabled": false} and the page keeps settings in the
browser only, as it does for everyone who is not signed in.

One row per account: the uid from the searchthehadith.fyi cookie, the
settings as JSON and when they were last saved. Only the keys in ALLOWED are
kept; nothing about the device (location, IP, user agent) is stored.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

SCHEMA = """
CREATE TABLE IF NOT EXISTS prefs (
    uid        TEXT PRIMARY KEY,  -- account id from the session cookie
    prefs      TEXT NOT NULL,     -- JSON object, keys from ALLOWED
    updated_at TEXT NOT NULL      -- UTC, ISO 8601
);
"""

MAX_BYTES = 2048

METHODS = {"NorthAmerica", "MuslimWorldLeague", "Egyptian", "Karachi", "UmmAlQura", "Dubai",
           "Qatar", "Kuwait", "MoonsightingCommittee", "Singapore", "Tehran", "Turkey"}


def _angle(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 <= v <= 30


# key: check for its value. Keep in step with SYNCED_KEYS in web/app.js.
ALLOWED = {
    "method":    lambda v: v in METHODS,
    "fajrAngle": _angle,
    "ishaAngle": _angle,
    "audioFile": lambda v: v in ("makkah", "fajr"),
}


def db_path() -> str | None:
    return os.environ.get("PREFS_DB_PATH", "").strip() or None


def allowed_origins() -> set[str]:
    raw = os.environ.get("PREFS_ALLOWED_ORIGINS", "").strip() or "https://adhan.searchthehadith.fyi"
    return {o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip()}


def same_origin(headers) -> bool:
    """Origin header, falling back to Referer, as sunnah-toolkit's accounts.py does."""
    origin = headers.get("origin")
    if not origin or origin == "null":
        ref = headers.get("referer")
        if not ref:
            return False
        p = urlsplit(ref)
        origin = f"{p.scheme}://{p.netloc}"
    return origin.lower() in allowed_origins()


def validate(obj: Any) -> str | None:
    """None if `obj` may be saved, else what is wrong with it."""
    if not isinstance(obj, dict):
        return "Expected a JSON object."
    for k, v in obj.items():
        check = ALLOWED.get(k)
        if check is None:
            return f"Unknown setting: {k[:40]}"
        if not check(v):
            return f"Bad value for {k}."
    return None


_conn: sqlite3.Connection | None = None
_conn_path: str | None = None
_lock = threading.Lock()


def _connect(path: str) -> sqlite3.Connection:
    global _conn, _conn_path
    if _conn is None or _conn_path != path:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        _conn, _conn_path = conn, path
    return _conn


def load(path: str, uid: str) -> tuple[dict | None, str | None]:
    """(prefs, updated_at) for `uid`, or (None, None) if nothing is saved."""
    with _lock:
        row = _connect(path).execute("SELECT prefs, updated_at FROM prefs WHERE uid = ?", (uid,)).fetchone()
    return (json.loads(row[0]), row[1]) if row else (None, None)


def save(path: str, uid: str, prefs: dict) -> str:
    """Replace `uid`'s settings. Returns the new updated_at."""
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    with _lock:
        conn = _connect(path)
        conn.execute("INSERT INTO prefs (uid, prefs, updated_at) VALUES (?, ?, ?) "
                     "ON CONFLICT(uid) DO UPDATE SET prefs = excluded.prefs, updated_at = excluded.updated_at",
                     (uid, json.dumps(prefs, separators=(",", ":"), sort_keys=True), ts))
        conn.commit()
    return ts
