"""
RAG Ingestion Pipeline
======================
Reads markdown docs, splits them into overlapping chunks, embeds each chunk
with Voyage AI, and saves the index to a JSON file.

WHY CHUNKS?
  A language model has a limited context window.  You can't paste 20 pages of
  docs into every prompt.  Chunks are small enough to fit, but targeted: only
  the 3-4 most relevant chunks end up in the prompt, not the whole corpus.

WHY OVERLAP?
  A sentence at the boundary of a chunk loses context.  Overlapping by ~50
  tokens means important sentences always have their surrounding context, even
  if they land near a chunk edge.

WHY VOYAGE AI?
  Embedding models convert text to dense float vectors.  Similar text ends up
  geometrically close in that high-dimensional space.  Voyage AI's models are
  among the best at this, and are the recommended embeddings provider alongside
  Claude.
"""

import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import voyageai

# ── Config ────────────────────────────────────────────────────────────────────
DOCS_DIR = Path(__file__).parent.parent / "docs"
INDEX_PATH = Path(__file__).parent / "index.json"
EMBED_MODEL = "voyage-3-lite"   # cheapest Voyage model; voyage-3 for higher quality
CHUNK_SIZE = 400                # target characters per chunk (not tokens — rough approx)
OVERLAP = 80                    # characters of overlap between consecutive chunks


def load_docs(docs_dir: Path) -> list[dict]:
    """Return list of {source, text} dicts, one per .md file."""
    docs = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        docs.append({"source": path.name, "text": text})
    print(f"Loaded {len(docs)} document(s) from {docs_dir}")
    return docs


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
    """
    Split text into overlapping windows.

    Strategy: split on double-newlines (paragraph boundaries) first, then
    merge small paragraphs until we hit CHUNK_SIZE, then slide by (chunk_size -
    overlap).  This keeps paragraph semantics intact while bounding chunk length.
    """
    # Normalise whitespace
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
                # overlap: carry the tail of the current chunk forward
                current = current[-overlap:].strip() + "\n\n" + para
            else:
                # single paragraph > chunk_size: hard split
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i : i + chunk_size])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def embed(texts: list[str], client: voyageai.Client) -> list[list[float]]:
    """Call Voyage AI and return a list of embedding vectors."""
    result = client.embed(texts, model=EMBED_MODEL, input_type="document")
    return result.embeddings   # list of list[float]


def build_index(docs: list[dict], voyage: voyageai.Client) -> list[dict]:
    """
    Chunk every doc, embed all chunks in one batch, return index records.

    Each record: {source, chunk_id, text, embedding (list[float])}
    """
    records = []
    all_chunks = []  # flat list to embed in one API call (cheaper than many small calls)
    chunk_meta = []  # parallel metadata

    for doc in docs:
        chunks = chunk_text(doc["text"])
        print(f"  {doc['source']}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_meta.append({"source": doc["source"], "chunk_id": i, "text": chunk})

    print(f"\nEmbedding {len(all_chunks)} chunks with {EMBED_MODEL}...")
    embeddings = embed(all_chunks, voyage)

    for meta, vec in zip(chunk_meta, embeddings):
        records.append({**meta, "embedding": vec})

    return records


def save_index(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f)
    print(f"Saved {len(records)} records to {path}")


def main():
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        sys.exit("Set VOYAGE_API_KEY environment variable.\n"
                 "Get a free key at https://www.voyageai.com/")

    voyage = voyageai.Client(api_key=api_key)
    docs = load_docs(DOCS_DIR)
    if not docs:
        sys.exit(f"No .md files found in {DOCS_DIR}")

    records = build_index(docs, voyage)
    save_index(records, INDEX_PATH)
    print("Done. Run `python rag/chat.py` to start asking questions.")


if __name__ == "__main__":
    main()
