"""
FastAPI backend for the Adhan Clock web app.

Exposes two things the browser can't do on its own:
  GET /api/chat   — streams RAG/Claude answers as SSE
  GET /api/status — lets the UI know if the RAG index is loaded

Everything else (prayer times, clock, location, voice, TTS) runs
entirely in the browser using Adhan.js, the Web Speech API, and the
browser Geolocation API.  No business logic is duplicated.

Audio files are served as static assets from /audio so the browser
can play them directly with the HTML5 Audio API.

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)

# ── RAG state (loaded once at startup) ───────────────────────────────────────

_rag: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from rag.query import INDEX_PATH, load_clients, load_index
        if not INDEX_PATH.exists():
            raise FileNotFoundError(f"Index not found — run: python rag/ingest.py")
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


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Adhan Clock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def status():
    return {
        "ready": _rag.get("ready", False),
        "chunks": _rag.get("chunks", 0),
        "error": _rag.get("error"),
    }


@app.get("/api/chat")
async def chat(
    q: str = Query(..., description="User question"),
    language: str = Query("English", description="Reply language"),
):
    if not _rag.get("ready"):
        err = _rag.get("error", "RAG index not loaded.")
        return JSONResponse({"error": err}, status_code=503)

    def generate():
        from rag.chat import answer_stream_with_tools
        try:
            stream, _ = answer_stream_with_tools(
                q,
                _rag["records"],
                _rag["matrix"],
                _rag["embedder"],
                _rag["model"],
                language=language,
            )
            for token in stream:
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps(f'Error: {e}')}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Static assets ─────────────────────────────────────────────────────────────

# Adhan audio files
app.mount("/audio", StaticFiles(directory=str(_ROOT / "lib")), name="audio")

# Web frontend — must be last so /api/* routes take precedence
app.mount("/", StaticFiles(directory=str(_ROOT / "web"), html=True), name="web")
