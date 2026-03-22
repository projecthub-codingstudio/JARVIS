"""CodeChunkStrategy — splits code at function/class boundaries.

Uses regex-based heuristic for Python (def/class detection).
Tree-sitter integration deferred — can be added without API change.
"""
from __future__ import annotations
import hashlib
import re
from jarvis.contracts import ChunkRecord, DocumentElement

_PY_DEF_RE = re.compile(r"^(class |def |async def )", re.MULTILINE)
_CHARS_PER_TOKEN = 3


class CodeChunkStrategy:
    """Splits code at function/class definition boundaries."""

    def __init__(self, *, max_tokens: int = 500) -> None:
        self._max_chars = max_tokens * _CHARS_PER_TOKEN

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        text = element.text
        if not text.strip():
            return []

        language = element.metadata.get("language", "")
        blocks = self._split_by_definitions(text)

        if len(blocks) <= 1:
            return self._size_split(text, document_id, language)

        chunks: list[ChunkRecord] = []
        current_parts: list[str] = []
        current_len = 0

        for block in blocks:
            if current_len + len(block) > self._max_chars and current_parts:
                chunk_text = "\n".join(current_parts)
                chunks.append(self._make_chunk(chunk_text, document_id, language))
                current_parts = []
                current_len = 0
            current_parts.append(block)
            current_len += len(block)

        if current_parts:
            chunks.append(self._make_chunk("\n".join(current_parts), document_id, language))

        return chunks

    def _split_by_definitions(self, text: str) -> list[str]:
        lines = text.split("\n")
        blocks: list[str] = []
        current: list[str] = []

        for line in lines:
            if _PY_DEF_RE.match(line) and current:
                blocks.append("\n".join(current))
                current = []
            current.append(line)

        if current:
            blocks.append("\n".join(current))

        return blocks

    def _size_split(self, text: str, document_id: str, language: str) -> list[ChunkRecord]:
        if len(text) <= self._max_chars:
            return [self._make_chunk(text, document_id, language)]

        chunks: list[ChunkRecord] = []
        lines = text.split("\n")
        current: list[str] = []
        current_len = 0
        for line in lines:
            if current_len + len(line) > self._max_chars and current:
                chunks.append(self._make_chunk("\n".join(current), document_id, language))
                current = []
                current_len = 0
            current.append(line)
            current_len += len(line)
        if current:
            chunks.append(self._make_chunk("\n".join(current), document_id, language))
        return chunks

    def _make_chunk(self, text: str, document_id: str, language: str) -> ChunkRecord:
        chunk_bytes = text.encode("utf-8")
        return ChunkRecord(
            document_id=document_id,
            text=text,
            chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            heading_path=f"code:{language}" if language else "code",
        )
