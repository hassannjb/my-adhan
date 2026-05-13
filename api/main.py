"""
FastAPI backend for the Adhan Clock web app.

  GET  /api/chat              — streams RAG answers as SSE (session-aware)
  GET  /api/status            — RAG index health
  DELETE /api/session/{id}    — clear a conversation session early

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

# ── RAG state ────────────────────────────────────────────────────────────────

_rag: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from rag.query import INDEX_PATH, load_clients, load_index
        if not INDEX_PATH.exists():
            raise FileNotFoundError("Index not found — run: python rag/ingest.py")
        _rag["records"], _rag["matrix"] = load_index(INDEX_PATH)
        _rag["embedder"], _rag["model"] = load_clients()
        _rag["ready"] = True
        _rag["chunks"] = len(_rag["records"])
        logger.info("RAG index loaded: %d chunks", _rag["chunks"])
    except (Exception, SystemExit) as e:
        _rag["ready"] = False
        _rag["error"] = str(e)
        logger.warning("RAG unavailable: %s", e)
    yield
    _rag.clear()


# ── Session store (in-memory, 30-min TTL) ────────────────────────────────────

_SESSION_TTL = timedelta(minutes=30)
_sessions: dict[str, dict] = {}


def _get_history(session_id: str) -> list[dict]:
    s = _sessions.get(session_id)
    if not s:
        return []
    if datetime.now() - s["last_active"] > _SESSION_TTL:
        _sessions.pop(session_id, None)
        return []
    return list(s["messages"])


def _save_turn(session_id: str, user_msg: str, assistant_msg: str) -> None:
    s = _sessions.setdefault(session_id, {"messages": [], "last_active": datetime.now()})
    s["messages"].append({"role": "user",      "content": user_msg})
    s["messages"].append({"role": "assistant", "content": assistant_msg})
    s["last_active"] = datetime.now()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Adhan Clock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    return {
        "ready":  _rag.get("ready", False),
        "chunks": _rag.get("chunks", 0),
        "error":  _rag.get("error"),
    }


@app.get("/api/chat")
async def chat(
    q:          str = Query(...,       description="User question"),
    language:   str = Query("English", description="Reply language"),
    session_id: str = Query("",        description="Session ID for conversation memory"),
):
    if not _rag.get("ready"):
        err = _rag.get("error", "RAG index not loaded.")
        return JSONResponse({"error": err}, status_code=503)

    history = _get_history(session_id) if session_id else []

    def generate():
        from rag.chat import answer_stream_with_tools
        full: list[str] = []
        try:
            stream, _ = answer_stream_with_tools(
                q,
                _rag["records"],
                _rag["matrix"],
                _rag["embedder"],
                _rag["model"],
                language=language,
                history=history,
            )
            for token in stream:
                full.append(token)
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps(f'Error: {e}')}\n\n"
        finally:
            if session_id and full:
                _save_turn(session_id, q, "".join(full))
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.delete("/api/session/{session_id}")
async def reset_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"ok": True}


# ── Static assets ─────────────────────────────────────────────────────────────

app.mount("/audio", StaticFiles(directory=str(_ROOT / "lib")), name="audio")
app.mount("/", StaticFiles(directory=str(_ROOT / "web"), html=True), name="web")
