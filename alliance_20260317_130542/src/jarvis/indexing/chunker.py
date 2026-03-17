"""Chunker — splits parsed document text into indexable chunks.

Per Spec Task 1.1:
  - documents: heading-aware paragraph windows
  - target 250 to 500 tokens, overlap 40 to 80 tokens
  - chunks carry heading_path for retrieval quality

Token estimation: ~2 chars per token for mixed Korean/English.
"""
from __future__ import annotations

import hashlib
import re

from jarvis.contracts import ChunkRecord

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$|^(\d+(?:\.\d+)*\.?)\s+(.+)$", re.MULTILINE)

# Korean: ~1.5 chars/token, English: ~4 chars/token. Blend ≈ 3 for mixed.
_CHARS_PER_TOKEN = 3
_DEFAULT_MAX_TOKENS = 500
_DEFAULT_OVERLAP_TOKENS = 80


def _snap_to_utf8_boundary(data: bytes, pos: int) -> int:
    """Snap a byte position forward to a valid UTF-8 character boundary."""
    if pos >= len(data):
        return len(data)
    while pos < len(data) and (data[pos] & 0xC0) == 0x80:
        pos += 1
    return pos


class Chunker:
    """Splits document text into overlapping, heading-aware chunks.

    Per Spec Task 1.1: target 250-500 tokens with 40-80 token overlap.
    """

    def __init__(
        self,
        *,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS,
        max_chunk_bytes: int | None = None,
        overlap_bytes: int | None = None,
    ) -> None:
        if max_chunk_bytes is not None:
            self._max_chars = max_chunk_bytes
            self._overlap_chars = overlap_bytes or 128
        else:
            self._max_chars = max_tokens * _CHARS_PER_TOKEN
            self._overlap_chars = overlap_tokens * _CHARS_PER_TOKEN

    def chunk(self, text: str, *, document_id: str = "") -> list[ChunkRecord]:
        if not text:
            return []

        paragraphs = re.split(r"\n{2,}", text)
        chunks: list[ChunkRecord] = []
        current_parts: list[str] = []
        current_len = 0
        current_headings: list[str] = []
        char_offset = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Track headings
            heading_match = _HEADING_RE.match(para)
            if heading_match:
                if heading_match.group(1):
                    level = len(heading_match.group(1))
                    heading_text = heading_match.group(2).strip()
                else:
                    level = min(para.count("."), 5) + 1
                    heading_text = para.strip()
                current_headings = current_headings[:max(0, level - 1)]
                current_headings.append(heading_text)

            para_len = len(para)

            # Long single paragraph: split by character limit
            if para_len > self._max_chars:
                if current_parts:
                    self._emit_chunk(chunks, current_parts, current_headings, document_id)
                    current_parts = []
                    current_len = 0

                para_bytes = para.encode("utf-8")
                pos = 0
                while pos < len(para_bytes):
                    end = min(pos + self._max_chars, len(para_bytes))
                    end = _snap_to_utf8_boundary(para_bytes, end)
                    sub_text = para_bytes[pos:end].decode("utf-8")
                    self._emit_chunk(chunks, [sub_text], current_headings, document_id)
                    next_pos = end - self._overlap_chars
                    pos = _snap_to_utf8_boundary(para_bytes, max(next_pos, pos + 1))
                continue

            # Normal case: accumulate paragraphs
            if current_len + para_len > self._max_chars and current_parts:
                self._emit_chunk(chunks, current_parts, current_headings, document_id)
                # Overlap: keep last parts
                overlap_parts: list[str] = []
                overlap_len = 0
                for p in reversed(current_parts):
                    if overlap_len + len(p) > self._overlap_chars:
                        break
                    overlap_parts.insert(0, p)
                    overlap_len += len(p)
                current_parts = overlap_parts
                current_len = overlap_len

            current_parts.append(para)
            current_len += para_len

        if current_parts:
            self._emit_chunk(chunks, current_parts, current_headings, document_id)

        return chunks

    def _emit_chunk(
        self,
        chunks: list[ChunkRecord],
        parts: list[str],
        headings: list[str],
        document_id: str,
    ) -> None:
        """Create a ChunkRecord and append to chunks list."""
        chunk_text = "\n\n".join(parts)
        chunk_bytes = chunk_text.encode("utf-8")
        chunk_index = len(chunks)

        chunks.append(ChunkRecord(
            document_id=document_id,
            byte_start=0,
            byte_end=len(chunk_bytes),
            line_start=chunk_index,
            line_end=chunk_index,
            text=chunk_text,
            chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            heading_path=" > ".join(headings[-3:]) if headings else "",
        ))
