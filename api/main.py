"""
FastAPI backend for the Adhan Clock web app.

  GET  /api/chat              : answers a question as JSON (see assistant/router.py)
  GET  /api/status            : assistant health
  GET  /api/me                : who is signed in (optional; accounts live on searchthehadith.fyi)
  GET  /api/prefs             : the signed-in user's saved settings (api/prefs.py)
  PUT  /api/prefs             : replace them
  DELETE /api/session/{id}    : kept for older pages; there is no server-side session now

The chat no longer uses an LLM: answers come from the curated assistant/faq.md,
and prayer times are calculated in the browser from the user's own settings.

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

# ── Assistant state ──────────────────────────────────────────────────────────

_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from assistant.router import Assistant
        _state["assistant"] = Assistant()
        _state["ready"] = True
        logger.info("assistant ready: %d answers, %s matching",
                    len(_state["assistant"].faq.entries), _state["assistant"].faq.mode)
    except Exception as e:
        _state["ready"] = False
        _state["error"] = str(e)
        logger.warning("assistant unavailable: %s", e)
    yield
    _state.clear()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Adhan Clock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# Cloudflare sits in front and caches .js for hours by default, which kept
# serving a stale app.js after a deploy. Make browsers and the edge recheck
# page assets every time (a 304 when unchanged); audio stays cacheable.
@app.middleware("http")
async def _revalidate_page_assets(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.endswith((".html", ".js", ".css", ".json")):
        response.headers["Cache-Control"] = "no-cache"
    return response


from assistant import ratelimit  # noqa: E402

_chat_limit = ratelimit.from_env()
_prefs_limit = ratelimit.from_env("RATE_LIMIT_PREFS_PER_MIN")


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    a = _state.get("assistant")
    return {
        "ready":   _state.get("ready", False),
        "answers": len(a.faq.entries) if a else 0,
        "mode":    a.faq.mode if a else None,
        "error":   _state.get("error"),
    }


# Plain `def` so FastAPI runs it in a thread: city lookups block on HTTP.
@app.get("/api/chat")
def chat(
    request:  Request,
    q:        str = Query(...,       description="User question", max_length=500),
    prev:     str = Query("",        description="JSON of the previous times reply, for follow-ups",
                          max_length=4000),
    language: str = Query("English", description="Ignored for now: answers are English only"),
):
    if _chat_limit is not None:
        wait = _chat_limit.hit(ratelimit.client_key(request.headers,
                                                    request.client.host if request.client else None))
        if wait:
            return JSONResponse(
                {"error": f"That's a lot of questions at once. Try again in {wait} seconds."},
                status_code=429, headers={"Retry-After": str(wait)})
    if not _state.get("ready"):
        return JSONResponse({"error": _state.get("error", "Assistant not loaded.")}, status_code=503)
    prev_obj = None
    if prev:
        try:
            prev_obj = json.loads(prev)
            if not isinstance(prev_obj, dict):
                prev_obj = None
        except ValueError:
            prev_obj = None
    from assistant import querylog
    started, t0 = querylog.now(), time.perf_counter()
    reply, error = None, None
    try:
        reply = _state["assistant"].answer(q, prev=prev_obj)
    except Exception as e:
        logger.exception("chat failed for %r", q)
        error = f"{type(e).__name__}: {e}"
        reply = {"kind": "error", "text": "Something went wrong answering that. Please try rephrasing."}
    querylog.record(started=started, query=q, reply=reply, headers=request.headers,
                    followup=prev_obj is not None, latency_ms=(time.perf_counter() - t0) * 1000,
                    error=error)
    return reply


# Optional sign-in, shared with the hadith search site. Accounts, sign-in pages
# and sign-out live there (sunnah-toolkit, /auth/*); its session cookie is
# scoped to .searchthehadith.fyi and signed with AUTH_SECRET, so this app can
# read it with the same secret. Off when AUTH_SECRET is unset.
def _signed_in(request: Request) -> dict | None:
    """The verified cookie payload, or None when signed out or sign-in is off."""
    secret = os.environ.get("AUTH_SECRET", "").strip()
    if not secret:
        return None
    from api import session_cookie
    raw = request.cookies.get(os.environ.get("AUTH_COOKIE_NAME", "").strip() or "sth_session")
    payload = session_cookie.verify(raw, secret) if raw else None
    return payload if payload and payload.get("email") else None


@app.get("/api/me")
def me(request: Request):
    secret = os.environ.get("AUTH_SECRET", "").strip()
    base = (os.environ.get("AUTH_BASE_URL", "").strip() or "https://searchthehadith.fyi").rstrip("/")
    payload = _signed_in(request)
    user = {"id": payload.get("uid"), "email": payload["email"], "name": payload.get("name")} if payload else None
    return JSONResponse({"enabled": bool(secret), "user": user, "auth_base": base},
                        headers={"Cache-Control": "no-store"})


# Settings that follow a signed-in user between devices. Off when
# PREFS_DB_PATH is unset; the page then keeps settings in the browser only.
def _prefs_gate(request: Request) -> tuple[str | None, JSONResponse | None]:
    """(uid, None) when the request may go ahead, else (None, the reply to send)."""
    def reply(body, code, **headers):
        return None, JSONResponse(body, status_code=code, headers={"Cache-Control": "no-store", **headers})

    from api import prefs
    if not prefs.db_path():
        return reply({"enabled": False, "error": "Settings sync is off on this server."},
                     200 if request.method == "GET" else 503)
    payload = _signed_in(request)
    if not payload or payload.get("uid") is None:
        return reply({"enabled": True, "error": "Sign in to save settings."}, 401)
    uid = str(payload["uid"])
    if _prefs_limit is not None:
        wait = _prefs_limit.hit("u:" + uid)
        if wait:
            return reply({"error": f"Too many saves. Try again in {wait} seconds."}, 429,
                         **{"Retry-After": str(wait)})
    return uid, None


@app.get("/api/prefs")
def get_prefs(request: Request):
    uid, refused = _prefs_gate(request)
    if refused:
        return refused
    from api import prefs
    saved, updated_at = prefs.load(prefs.db_path(), uid)
    return JSONResponse({"enabled": True, "prefs": saved, "updated_at": updated_at},
                        headers={"Cache-Control": "no-store"})


@app.put("/api/prefs")
async def put_prefs(request: Request):
    from api import prefs
    uid, refused = _prefs_gate(request)
    if refused:
        return refused
    if not prefs.same_origin(request.headers):
        return JSONResponse({"error": "Cross-site request refused."}, status_code=403)
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > prefs.MAX_BYTES:
            return JSONResponse({"error": "Settings too large."}, status_code=413)
    try:
        obj = json.loads(body or b"null")
    except ValueError:
        return JSONResponse({"error": "Body is not JSON."}, status_code=400)
    problem = prefs.validate(obj)
    if problem:
        return JSONResponse({"error": problem}, status_code=400)
    updated_at = await run_in_threadpool(prefs.save, prefs.db_path(), uid, obj)
    return JSONResponse({"enabled": True, "prefs": obj, "updated_at": updated_at},
                        headers={"Cache-Control": "no-store"})


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str):
    return {"ok": True}


# ── Static assets ─────────────────────────────────────────────────────────────

app.mount("/audio", StaticFiles(directory=str(_ROOT / "lib")), name="audio")
app.mount("/", StaticFiles(directory=str(_ROOT / "web"), html=True), name="web")
