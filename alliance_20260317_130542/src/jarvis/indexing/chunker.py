"""Chunker — splits parsed document text into indexable chunks.

Produces ChunkRecord objects with byte/line ranges for citation
back-references.
"""
from __future__ import annotations

import hashlib

from jarvis.contracts import ChunkRecord


def _snap_to_utf8_boundary(data: bytes, pos: int) -> int:
    """Snap a byte position forward to a valid UTF-8 character boundary."""
    if pos >= len(data):
        return len(data)
    # UTF-8 continuation bytes start with 0b10xxxxxx (0x80-0xBF).
    # Advance past any continuation bytes to reach the start of the next char.
    while pos < len(data) and (data[pos] & 0xC0) == 0x80:
        pos += 1
    return pos


class Chunker:
    """Splits document text into overlapping chunks for indexing.

    Chunk boundaries respect newline boundaries where possible.
    Byte positions are snapped to UTF-8 character boundaries to avoid
    splitting multi-byte characters (critical for Korean text).
    """

    def __init__(
        self,
        *,
        max_chunk_bytes: int = 1024,
        overlap_bytes: int = 128,
    ) -> None:
        self._max_chunk_bytes = max_chunk_bytes
        self._overlap_bytes = overlap_bytes

    def chunk(self, text: str, *, document_id: str = "") -> list[ChunkRecord]:
        if not text:
            return []

        text_bytes = text.encode("utf-8")
        total = len(text_bytes)
        chunks: list[ChunkRecord] = []
        byte_pos = 0

        while byte_pos < total:
            end = min(byte_pos + self._max_chunk_bytes, total)

            # Try to break at a newline within the last 25% of the chunk
            if end < total:
                search_start = max(byte_pos + (self._max_chunk_bytes * 3 // 4), byte_pos)
                best_break = -1
                # Look for double newline first (paragraph boundary)
                idx = text_bytes.rfind(b"\n\n", search_start, end)
                if idx != -1:
                    best_break = idx + 2
                else:
                    # Fall back to single newline
                    idx = text_bytes.rfind(b"\n", search_start, end)
                    if idx != -1:
                        best_break = idx + 1
                if best_break > byte_pos:
                    end = best_break

            # Snap end to UTF-8 character boundary
            end = _snap_to_utf8_boundary(text_bytes, end)

            chunk_bytes = text_bytes[byte_pos:end]
            chunk_text = chunk_bytes.decode("utf-8")

            # Compute line range
            preceding = text_bytes[:byte_pos]
            line_start = preceding.count(b"\n")
            line_end = line_start + chunk_bytes.count(b"\n")

            chunks.append(ChunkRecord(
                document_id=document_id,
                byte_start=byte_pos,
                byte_end=end,
                line_start=line_start,
                line_end=line_end,
                text=chunk_text,
                chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            ))

            # Advance with overlap, snapping to UTF-8 boundary
            if end < total:
                next_pos = end - self._overlap_bytes
                byte_pos = _snap_to_utf8_boundary(text_bytes, max(next_pos, byte_pos + 1))
            else:
                byte_pos = total

        return chunks
