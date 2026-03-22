"""ParagraphChunkStrategy — default text chunking by paragraph boundaries.

Extracted from the original Chunker logic. Splits on double-newline,
respects heading hierarchy, applies overlap.
"""
from __future__ import annotations
from dataclasses import replace
from jarvis.contracts import ChunkRecord, DocumentElement
from jarvis.indexing.chunker import Chunker


class ParagraphChunkStrategy:
    """Default chunk strategy using paragraph boundaries."""

    def __init__(self, *, max_tokens: int = 500, overlap_tokens: int = 80) -> None:
        self._chunker = Chunker(max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        if not element.text.strip():
            return []
        chunks = self._chunker.chunk(element.text, document_id=document_id)
        heading = element.metadata.get("heading_path", "")
        if heading:
            chunks = [replace(c, heading_path=heading) if not c.heading_path else c for c in chunks]
        return chunks
