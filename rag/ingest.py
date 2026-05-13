"""
RAG Ingestion Pipeline
======================
Reads markdown docs, splits them into overlapping chunks, embeds each chunk
with sentence-transformers (all-MiniLM-L6-v2), and saves the index to a JSON
file.  No API keys required — model runs entirely locally.

WHY CHUNKS?
  A language model has a limited context window.  You can't paste 20 pages of
  docs into every prompt.  Chunks are small enough to fit, but targeted: only
  the 3-4 most relevant chunks end up in the prompt, not the whole corpus.

WHY OVERLAP?
  A sentence at the boundary of a chunk loses context.  Overlapping by ~50
  tokens means important sentences always have their surrounding context, even
  if they land near a chunk edge.
"""

import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────
DOCS_DIR   = Path(__file__).parent.parent / "docs"
INDEX_PATH = Path(__file__).parent / "index.json"
EMBED_MODEL = "all-MiniLM-L6-v2"   # 384-dim, ~90 MB, fast on CPU
CHUNK_SIZE  = 400                   # target characters per chunk
OVERLAP     = 80                    # characters of overlap between chunks


def load_docs(docs_dir: Path) -> list[dict]:
    docs = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        docs.append({"source": path.name, "text": text})
    print(f"Loaded {len(docs)} document(s) from {docs_dir}")
    return docs


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = OVERLAP) -> list[str]:
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
                current = current[-overlap:].strip() + "\n\n" + para
            else:
                for i in range(0, len(para), chunk_size - overlap):
                    chunks.append(para[i : i + chunk_size])
                current = ""
    if current:
        chunks.append(current)
    return chunks


def build_index(docs: list[dict], model: SentenceTransformer) -> list[dict]:
    records = []
    all_chunks = []
    chunk_meta = []

    for doc in docs:
        chunks = chunk_text(doc["text"])
        print(f"  {doc['source']}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_meta.append({"source": doc["source"], "chunk_id": i, "text": chunk})

    print(f"\nEmbedding {len(all_chunks)} chunks with {EMBED_MODEL}...")
    embeddings = model.encode(all_chunks, normalize_embeddings=True, show_progress_bar=True)

    for meta, vec in zip(chunk_meta, embeddings):
        records.append({**meta, "embedding": vec.tolist()})

    return records


def save_index(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(records, f)
    print(f"Saved {len(records)} records to {path}")


def main():
    import sys
    docs = load_docs(DOCS_DIR)
    if not docs:
        sys.exit(f"No .md files found in {DOCS_DIR}")

    print(f"Loading embedding model {EMBED_MODEL}...")
    model = SentenceTransformer(EMBED_MODEL)
    records = build_index(docs, model)
    save_index(records, INDEX_PATH)
    print("Done.")


if __name__ == "__main__":
    main()
