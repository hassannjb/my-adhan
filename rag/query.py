"""
RAG Query Pipeline
==================
Given a user question:
  1. Embed the question with the SAME model used at index time.
  2. Compute cosine similarity between the question vector and every stored chunk.
  3. Return the top-k most similar chunks.
  4. Build a prompt: system instructions + retrieved context + question.
  5. Call Claude and return the answer.

WHY COSINE SIMILARITY?
  Vectors can vary in magnitude, but we care about direction (semantic meaning).
  Cosine similarity normalises for length: cosine(A, B) = dot(A,B) / (|A||B|).
  Result is always in [-1, 1]; higher = more similar.

WHY THE SAME EMBEDDING MODEL?
  The vectors MUST live in the same space to be comparable.  If you index with
  voyage-3 and query with text-embedding-3-small, the geometry is meaningless.
"""

import json
import os
import sys
from pathlib import Path

import anthropic
import numpy as np
import voyageai

INDEX_PATH = Path(__file__).parent / "index.json"
EMBED_MODEL = "voyage-3-lite"
TOP_K = 4          # how many chunks to retrieve
CLAUDE_MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a helpful assistant for the Adhan Clock app — an Islamic prayer times application.
Answer questions using ONLY the context provided below.
If the context doesn't contain enough information to answer, say so clearly.
Be concise and accurate. Do not invent details not present in the context."""


def load_index(path: Path) -> tuple[list[dict], np.ndarray]:
    """Return (records, matrix) where matrix[i] is the normalised embedding of records[i]."""
    with open(path) as f:
        records = json.load(f)
    matrix = np.array([r["embedding"] for r in records], dtype=np.float32)
    # Pre-normalise for fast cosine similarity (dot product of unit vectors = cosine)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.where(norms == 0, 1, norms)
    return records, matrix


def retrieve(question: str, records: list[dict], matrix: np.ndarray,
             voyage: voyageai.Client, top_k: int = TOP_K) -> list[dict]:
    """Embed the question and return the top-k most similar records."""
    result = voyage.embed([question], model=EMBED_MODEL, input_type="query")
    q_vec = np.array(result.embeddings[0], dtype=np.float32)
    q_vec = q_vec / (np.linalg.norm(q_vec) or 1.0)

    scores = matrix @ q_vec          # (N,) — cosine similarity for each chunk
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [
        {**records[i], "score": float(scores[i])}
        for i in top_indices
    ]


def build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into a readable context block."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source: {chunk['source']} | Relevance: {chunk['score']:.3f}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def _build_messages(question: str, chunks: list[dict]) -> list[dict]:
    context = build_context(chunks)
    return [{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}]


def answer(question: str, records: list[dict], matrix: np.ndarray,
           voyage: voyageai.Client, claude: anthropic.Anthropic,
           top_k: int = TOP_K) -> tuple[str, list[dict]]:
    """Full RAG pipeline, blocking. Returns (answer_text, retrieved_chunks)."""
    chunks = retrieve(question, records, matrix, voyage, top_k)
    response = claude.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=_build_messages(question, chunks),
    )
    return response.content[0].text, chunks


def answer_stream(question: str, records: list[dict], matrix: np.ndarray,
                  voyage: voyageai.Client, claude: anthropic.Anthropic,
                  top_k: int = TOP_K):
    """
    Full RAG pipeline, streaming.

    Returns (token_generator, retrieved_chunks).  Iterate the generator to
    receive text tokens as Claude produces them — no waiting for the full
    response before the first word appears.

    WHY STREAMING MATTERS:
      Without streaming, the user sees nothing for 2–5 seconds, then the full
      answer dumps at once.  With streaming, the first token arrives in ~300ms.
      The total time is the same, but perceived latency drops dramatically.
      This is why every chat UI (Claude, ChatGPT, Copilot) streams by default.
    """
    chunks = retrieve(question, records, matrix, voyage, top_k)

    def _tokens():
        with claude.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=_build_messages(question, chunks),
        ) as stream:
            yield from stream.text_stream

    return _tokens(), chunks


def load_clients() -> tuple[voyageai.Client, anthropic.Anthropic]:
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not voyage_key:
        sys.exit("Set VOYAGE_API_KEY environment variable.")
    if not anthropic_key:
        sys.exit("Set ANTHROPIC_API_KEY environment variable.")
    return voyageai.Client(api_key=voyage_key), anthropic.Anthropic(api_key=anthropic_key)
