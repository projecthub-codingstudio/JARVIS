"""TableChunkStrategy — row-level chunking with header mapping for structured data."""
from __future__ import annotations
import hashlib
from jarvis.contracts import ChunkRecord, DocumentElement


class TableChunkStrategy:
    """Chunks table data with each row as an independent chunk.

    Each row chunk includes header-mapped key=value pairs so the LLM
    can identify which column each value belongs to without needing
    the full table context.
    """

    def __init__(self, *, min_rows_for_split: int = 4) -> None:
        self._min_rows_for_split = min_rows_for_split

    def chunk(self, element: DocumentElement, *, document_id: str) -> list[ChunkRecord]:
        headers = element.metadata.get("headers", ())
        rows = element.metadata.get("rows", ())
        sheet_name = element.metadata.get("sheet_name", "")

        if not rows:
            return []

        chunks: list[ChunkRecord] = []

        # Summary chunk
        summary = self._build_summary(sheet_name, headers, len(rows))
        chunks.append(self._make_chunk(summary, document_id, f"table-summary-{sheet_name}"))

        # Small tables: single chunk with all rows
        if len(rows) < self._min_rows_for_split:
            full_text = self._render_full_table(sheet_name, headers, rows)
            chunks.append(self._make_chunk(full_text, document_id, f"table-full-{sheet_name}"))
            return chunks

        # Each row as independent chunk with header mapping
        for row_idx, row in enumerate(rows):
            row_text = self._render_row(sheet_name, headers, row, row_idx)
            chunks.append(self._make_chunk(row_text, document_id, f"table-row-{sheet_name}-{row_idx}"))

        return chunks

    def _render_row(self, sheet_name: str, headers: tuple, row: tuple, row_idx: int) -> str:
        pairs = []
        for i, val in enumerate(row):
            header = headers[i] if i < len(headers) else f"col{i}"
            pairs.append(f"{header}={val}")
        prefix = f"[{sheet_name}] " if sheet_name else ""
        return f"{prefix}{' | '.join(pairs)}"

    def _render_full_table(self, sheet_name: str, headers: tuple, rows: tuple) -> str:
        prefix = f"[{sheet_name}] " if sheet_name else ""
        lines = [f"{prefix}{' | '.join(headers)}"]
        for row in rows:
            lines.append(f"{prefix}{' | '.join(str(v) for v in row)}")
        return "\n".join(lines)

    def _build_summary(self, sheet_name: str, headers: tuple, row_count: int) -> str:
        cols = ", ".join(headers) if headers else "unknown"
        return f"[{sheet_name}] Table with {row_count} rows. Columns: {cols}"

    def _make_chunk(self, text: str, document_id: str, label: str) -> ChunkRecord:
        chunk_bytes = text.encode("utf-8")
        return ChunkRecord(
            document_id=document_id,
            text=text,
            chunk_hash=hashlib.sha256(chunk_bytes).hexdigest(),
            heading_path=label,
        )
