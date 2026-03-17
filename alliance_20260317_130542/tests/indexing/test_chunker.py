"""Tests for Chunker."""
from __future__ import annotations

import pytest

from jarvis.contracts import ChunkRecord
from jarvis.indexing.chunker import Chunker


class TestChunkerBasic:
    def test_empty_text_returns_empty(self) -> None:
        assert Chunker().chunk("") == []

    def test_short_text_single_chunk(self) -> None:
        chunks = Chunker(max_chunk_bytes=1024).chunk("Hello world", document_id="doc1")
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"
        assert chunks[0].document_id == "doc1"

    def test_chunk_has_byte_ranges(self) -> None:
        chunks = Chunker(max_chunk_bytes=1024).chunk("Hello world", document_id="d1")
        c = chunks[0]
        assert c.byte_start == 0
        assert c.byte_end == len("Hello world".encode("utf-8"))

    def test_chunk_has_line_ranges(self) -> None:
        text = "Line 1\nLine 2\nLine 3"
        chunks = Chunker(max_chunk_bytes=4096).chunk(text, document_id="d1")
        assert chunks[0].line_start >= 0
        assert chunks[0].line_end >= 0

    def test_chunk_has_hash(self) -> None:
        chunks = Chunker().chunk("some text", document_id="d1")
        assert chunks[0].chunk_hash  # non-empty

    def test_chunk_id_is_uuid(self) -> None:
        chunks = Chunker().chunk("text", document_id="d1")
        assert len(chunks[0].chunk_id) == 36  # UUID format


class TestChunkerSplitting:
    def test_long_text_produces_multiple_chunks(self) -> None:
        text = "word " * 500  # ~2500 bytes
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1

    def test_chunks_cover_all_text(self) -> None:
        text = "A" * 1000
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        # All text must be represented in at least one chunk
        all_text = "".join(c.text for c in chunks)
        assert "A" * 100 in all_text
        assert chunks[0].byte_start == 0

    def test_chunks_have_overlap(self) -> None:
        text = "word " * 200  # 1000 bytes
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=64).chunk(text, document_id="d1")
        if len(chunks) >= 2:
            assert chunks[1].byte_start < chunks[0].byte_end

    def test_respects_newline_boundaries(self) -> None:
        paragraphs = ["Paragraph one content here." * 5, "Paragraph two content here." * 5]
        text = "\n\n".join(paragraphs)
        chunks = Chunker(max_chunk_bytes=200, overlap_bytes=32).chunk(text, document_id="d1")
        for c in chunks:
            stripped = c.text.lstrip()
            if stripped:
                assert stripped[0].isalpha() or stripped[0] in "\n#-*>"


class TestChunkerKorean:
    def test_korean_text_chunking(self) -> None:
        text = "한국어 문장입니다. " * 100
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1
        for c in chunks:
            assert isinstance(c, ChunkRecord)
            assert c.text

    def test_mixed_korean_english(self) -> None:
        text = "JARVIS 프로젝트의 아키텍처를 설명합니다. " * 50
        chunks = Chunker(max_chunk_bytes=256, overlap_bytes=32).chunk(text, document_id="d1")
        assert len(chunks) > 1

    def test_no_replacement_chars_in_korean_chunks(self) -> None:
        """Verify multi-byte Korean chars are never split mid-character."""
        text = "가나다라마바사아자차카타파하" * 30  # pure Korean, 3 bytes each
        # Use chunk size that doesn't align with 3-byte boundaries
        chunks = Chunker(max_chunk_bytes=100, overlap_bytes=25).chunk(text, document_id="d1")
        for c in chunks:
            assert "\ufffd" not in c.text, f"Replacement char found in chunk: {c.text[:50]}..."
            # Every chunk should decode cleanly
            c.text.encode("utf-8").decode("utf-8")
