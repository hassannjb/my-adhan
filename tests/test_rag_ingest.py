"""Tests for the RAG ingestion pipeline (no API keys needed)."""
from rag.ingest import chunk_text, CHUNK_SIZE, OVERLAP


def test_short_text_is_single_chunk():
    text = "This is a short document."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunks_cover_all_content():
    # Generate a multi-paragraph text that forces >1 chunk
    paragraphs = [f"Paragraph {i}: " + "word " * 60 for i in range(10)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    # Every paragraph must appear somewhere in the chunks
    for para in paragraphs:
        first_sentence = para[:30]
        assert any(first_sentence in c for c in chunks), f"Lost content: {first_sentence}"


def test_chunk_size_respected():
    paragraphs = ["x " * 300 for _ in range(5)]  # each para is 600 chars
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    for chunk in chunks:
        # Allow a little over for hard splits, but nothing extreme
        assert len(chunk) <= CHUNK_SIZE * 2, f"Chunk too large: {len(chunk)}"


def test_overlap_carries_context():
    # Two paragraphs each just under CHUNK_SIZE — they should be in separate chunks
    # and the second chunk should start with the tail of the first
    para_a = "A " * (CHUNK_SIZE // 2 + 10)
    para_b = "B " * (CHUNK_SIZE // 2 + 10)
    text = para_a.strip() + "\n\n" + para_b.strip()
    chunks = chunk_text(text, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    assert len(chunks) >= 2
    # The overlap means the second chunk starts with the tail of the first
    tail_of_first = chunks[0][-OVERLAP:].strip()
    assert tail_of_first in chunks[1], "Overlap not carried into second chunk"


def test_empty_text_returns_empty():
    assert chunk_text("") == []


def test_whitespace_only_returns_empty():
    assert chunk_text("   \n\n   ") == []
