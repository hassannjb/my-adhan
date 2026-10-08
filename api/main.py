"""
FastAPI backend for the Adhan Clock web app.

  GET  /api/chat              : answers a question as JSON (see assistant/router.py)
  GET  /api/status            : assistant health
  DELETE /api/session/{id}    : kept for older pages; there is no server-side session now

The chat no longer uses an LLM: answers come from the curated assistant/faq.md,
and prayer times are calculated in the browser from the user's own settings.

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
    prev:     str = Query("",        description="JSON of the previous times reply, for follow-ups"),
    language: str = Query("English", description="Ignored for now: answers are English only"),
):
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


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str):
    return {"ok": True}


# ── Static assets ─────────────────────────────────────────────────────────────

app.mount("/audio", StaticFiles(directory=str(_ROOT / "lib")), name="audio")
app.mount("/", StaticFiles(directory=str(_ROOT / "web"), html=True), name="web")
