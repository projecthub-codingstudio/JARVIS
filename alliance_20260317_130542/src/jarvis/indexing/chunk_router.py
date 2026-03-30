"""ChunkRouter — dispatches document elements to type-specific chunk strategies.

Routes each DocumentElement in a ParsedDocument to the appropriate
ChunkStrategy based on element_type. Central entry point for chunking.
"""
from __future__ import annotations

from jarvis.contracts import ChunkRecord, DocumentElement, ParsedDocument
from jarvis.indexing.strategies.code import CodeChunkStrategy
from jarvis.indexing.strategies.paragraph import ParagraphChunkStrategy
from jarvis.indexing.strategies.table import TableChunkStrategy


class ChunkRouter:
    """Routes each DocumentElement to the appropriate ChunkStrategy."""

    def __init__(self) -> None:
        self._paragraph = ParagraphChunkStrategy()
        self._table = TableChunkStrategy()
        self._code = CodeChunkStrategy()

    def chunk(self, doc: ParsedDocument, *, document_id: str) -> list[ChunkRecord]:
        """Chunk all elements in a ParsedDocument using type-specific strategies."""
        chunks: list[ChunkRecord] = []
        for element in doc.elements:
            strategy = self._select_strategy(element)
            chunks.extend(strategy.chunk(element, document_id=document_id))
        return chunks

    def _select_strategy(self, element: DocumentElement):
        """Select the appropriate strategy for an element type."""
        if element.element_type == "table":
            return self._table
        if element.element_type == "code":
            return self._code
        return self._paragraph
