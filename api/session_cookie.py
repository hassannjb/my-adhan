"""Reads the sign-in cookie set by searchthehadith.fyi.

Copy of sunnah-toolkit's sunnah_toolkit/core/session_cookie.py: keep the two
in step. Format: `v1.<base64url JSON payload>.<base64url HMAC-SHA256>`, signed
with AUTH_SECRET (the same value on both sites). The payload is
{sid, uid, email, name, exp}; `exp` is unix seconds. This app has no user
database, so it trusts a genuine, unexpired cookie; ending the session on
the search site does not reach a copy of the cookie held elsewhere until it
expires. Fine for showing who is signed in; anything that acts on an
account should ask searchthehadith.fyi/auth/me instead.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _key(secret: str, purpose: str) -> bytes:
    return hmac.new(secret.encode(), f"sth-cookie:{purpose}".encode(), hashlib.sha256).digest()


def sign(payload: dict[str, Any], secret: str, purpose: str = "session") -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    mac = hmac.new(_key(secret, purpose), f"v1.{body}".encode(), hashlib.sha256).digest()
    return f"v1.{body}.{_b64(mac)}"


def verify(value: str, secret: str, purpose: str = "session", now: float | None = None) -> dict[str, Any] | None:
    """The payload if `value` is genuine and unexpired, else None."""
    try:
        version, body, mac = value.split(".")
        if version != "v1":
            return None
        want = hmac.new(_key(secret, purpose), f"v1.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(want, _unb64(mac)):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("exp"), (int, float)):
        return None
    if payload["exp"] <= (time.time() if now is None else now):
        return None
    return payload
