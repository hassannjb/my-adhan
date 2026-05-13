"""
RAG Query Pipeline
==================
Given a user question:
  1. Embed the question with the SAME model used at index time.
  2. Compute cosine similarity between the question vector and every stored chunk.
  3. Return the top-k most similar chunks.
  4. Build a prompt: system instructions + retrieved context + question.
  5. Call Ollama (local LLM) and return the answer.

No API keys required — all inference runs locally via Ollama.
"""

import json
from pathlib import Path

import numpy as np
import ollama
from sentence_transformers import SentenceTransformer

INDEX_PATH  = Path(__file__).parent / "index.json"
EMBED_MODEL = "all-MiniLM-L6-v2"
OLLAMA_MODEL = "llama3.2:3b"
TOP_K = 4

SYSTEM_PROMPT = """You are a helpful assistant for the Adhan Clock app — an Islamic prayer times application.
Answer questions using ONLY the context provided below.
If the context doesn't contain enough information to answer, say so clearly.
Be concise and accurate. Do not invent details not present in the context."""


def load_index(path: Path) -> tuple[list[dict], np.ndarray]:
    """Return (records, matrix) where matrix[i] is the normalised embedding of records[i]."""
    with open(path) as f:
        records = json.load(f)
    matrix = np.array([r["embedding"] for r in records], dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    matrix = matrix / np.where(norms == 0, 1, norms)
    return records, matrix


def retrieve(question: str, records: list[dict], matrix: np.ndarray,
             embedder: SentenceTransformer, top_k: int = TOP_K) -> list[dict]:
    """Embed the question and return the top-k most similar records."""
    q_vec = embedder.encode(question, normalize_embeddings=True)
    scores = matrix @ q_vec
    top_indices = np.argsort(scores)[::-1][:top_k]
    return [{**records[i], "score": float(scores[i])} for i in top_indices]


def build_context(chunks: list[dict]) -> str:
    parts = []
    for chunk in chunks:
        parts.append(f"[Source: {chunk['source']} | Relevance: {chunk['score']:.3f}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def _build_messages(question: str, chunks: list[dict]) -> list[dict]:
    context = build_context(chunks)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]


def answer(question: str, records: list[dict], matrix: np.ndarray,
           embedder: SentenceTransformer, model: str = OLLAMA_MODEL,
           top_k: int = TOP_K) -> tuple[str, list[dict]]:
    """Full RAG pipeline, blocking."""
    chunks = retrieve(question, records, matrix, embedder, top_k)
    resp = ollama.chat(model=model, messages=_build_messages(question, chunks))
    return resp["message"]["content"], chunks


def answer_stream(question: str, records: list[dict], matrix: np.ndarray,
                  embedder: SentenceTransformer, model: str = OLLAMA_MODEL,
                  top_k: int = TOP_K):
    """
    Full RAG pipeline, streaming.
    Returns (token_generator, retrieved_chunks).
    """
    chunks = retrieve(question, records, matrix, embedder, top_k)
    messages = _build_messages(question, chunks)

    def _tokens():
        stream = ollama.chat(model=model, messages=messages, stream=True)
        for chunk in stream:
            text = chunk["message"]["content"]
            if text:
                yield text

    return _tokens(), chunks


def load_clients() -> tuple[SentenceTransformer, str]:
    """Load the embedding model and return (embedder, ollama_model_name)."""
    print(f"Loading embedding model {EMBED_MODEL}...")
    embedder = SentenceTransformer(EMBED_MODEL)
    return embedder, OLLAMA_MODEL
