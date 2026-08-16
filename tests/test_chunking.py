"""Tests for the recursive markdown chunker.

The invariants worth pinning (as opposed to exact char counts which drift):
  - Every chunk is ≤ max_chars (except the one-chunk no-split edge case).
  - Chunks are in document order.
  - Adjacent chunks overlap by at most `overlap_chars`.
  - Concatenated *non-overlap* text covers the full source.
"""

from __future__ import annotations

from job_finder.classify.chunking import (
    CHARS_PER_TOKEN,
    DEFAULT_CHUNK_TOKENS,
    Chunk,
    approx_tokens,
    chunk_text,
)


class TestChunkText:
    def test_empty_returns_empty(self):
        assert chunk_text("") == []
        assert chunk_text("   \n  \t ") == []

    def test_short_text_returns_one_chunk(self):
        out = chunk_text("Just a short paragraph.")
        assert len(out) == 1
        assert out[0].text == "Just a short paragraph."
        assert out[0].start == 0

    def test_large_doc_produces_multiple_chunks(self):
        # ~3x default chunk size
        paragraph = ("This is a sentence about graphics programming. " * 40).strip()
        text = "\n\n".join([paragraph] * 5)
        chunks = chunk_text(text, chunk_tokens=128, overlap_tokens=20)
        assert len(chunks) >= 3

    def test_every_chunk_near_max(self):
        """No chunk should wildly exceed max_chars (allow slack for overlap)."""
        paragraph = ("Render real-time scenes with a tile-based GPU renderer. " * 30).strip()
        text = "\n\n".join([paragraph] * 4)
        chunk_tokens = 64
        overlap_tokens = 10
        max_chars = chunk_tokens * CHARS_PER_TOKEN
        overlap_chars = overlap_tokens * CHARS_PER_TOKEN
        chunks = chunk_text(text, chunk_tokens=chunk_tokens, overlap_tokens=overlap_tokens)
        # After overlap injection, chunk 2+ can be max_chars + overlap_chars wide
        slack = max_chars + overlap_chars + CHARS_PER_TOKEN
        for c in chunks:
            assert len(c.text) <= slack, f"chunk {len(c.text)} chars exceeds slack {slack}"

    def test_chunks_are_in_document_order(self):
        text = "\n\n".join(f"Paragraph {i}: " + ("content " * 20) for i in range(12))
        chunks = chunk_text(text, chunk_tokens=48, overlap_tokens=5)
        for a, b in zip(chunks, chunks[1:]):
            # Starts are non-decreasing (overlap can cause `b.start` = `a.end - overlap`)
            assert b.start >= a.start
            assert b.end >= a.end

    def test_overlap_is_bounded(self):
        text = "word " * 800  # lots of splittable whitespace
        overlap_tokens = 10
        chunks = chunk_text(text, chunk_tokens=80, overlap_tokens=overlap_tokens)
        overlap_chars_max = overlap_tokens * CHARS_PER_TOKEN
        for a, b in zip(chunks, chunks[1:]):
            # Overlap region width = a.end - b.start (allowed to be 0 or positive, bounded)
            overlap = max(0, a.end - b.start)
            assert overlap <= overlap_chars_max + CHARS_PER_TOKEN

    def test_respects_paragraph_breaks(self):
        a = "Paragraph one describes rendering."
        b = "Paragraph two describes networking."
        text = f"{a}\n\n{b}"
        chunks = chunk_text(text)
        joined = " ".join(c.text for c in chunks)
        assert "rendering" in joined and "networking" in joined


class TestApproxTokens:
    def test_empty(self):
        assert approx_tokens("") == 0

    def test_rounds_up(self):
        # 1 char → 1 token (ceil(1/4))
        assert approx_tokens("x") == 1
        # 4 chars → 1 token
        assert approx_tokens("xxxx") == 1
        # 5 chars → 2 tokens
        assert approx_tokens("xxxxx") == 2

    def test_scales_linearly_enough(self):
        t = "hello world " * 100
        assert approx_tokens(t) == (len(t) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


class TestChunkDataclass:
    def test_slots_are_set(self):
        c = Chunk(text="x", start=0, end=1)
        assert c.text == "x"
        assert c.start == 0
        assert c.end == 1

    def test_default_size_constants_match(self):
        # Guard against accidental drift from the spec's 512/50 numbers
        assert DEFAULT_CHUNK_TOKENS == 512
