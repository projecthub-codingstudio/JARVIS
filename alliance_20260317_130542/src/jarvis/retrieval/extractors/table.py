"""TableExtractor — deterministic fact extraction from table-row evidence.

Parses key=value pipe-delimited format produced by TableChunkStrategy.
Produces facts with composite keys for full disambiguation:
  "[표 미리보기 이미지 정보] 오프셋=0 > 자료형" — table name + row ID + column

The table name comes from:
  1. The [SheetName] prefix in the text (e.g., "[표 글자 모양]")
  2. This ensures facts from different tables are never confused
"""
from __future__ import annotations

import re

from jarvis.contracts import EvidenceItem, ExtractedFact

_TABLE_ROW_RE = re.compile(r"^\[([^\]]+)\]\s*(.+)$")


class TableExtractor:
    """Extracts structured facts from table-row evidence items."""

    def extract(self, item: EvidenceItem) -> list[ExtractedFact]:
        if not (item.heading_path and "table-row" in item.heading_path):
            return []

        m = _TABLE_ROW_RE.match(item.text)
        if not m:
            return []

        table_name = m.group(1).strip()
        pairs_str = m.group(2)
        if "=" not in pairs_str:
            return []

        raw_pairs: list[tuple[str, str]] = []
        for part in pairs_str.split("|"):
            part = part.strip()
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key, value = key.strip(), value.strip()
            if key and value:
                raw_pairs.append((key, value))

        if not raw_pairs:
            return []

        # First column is the row identifier (e.g., Day=5, 오프셋=0)
        first_key, first_val = raw_pairs[0]
        row_id = f"{first_key}={first_val}"

        facts: list[ExtractedFact] = []
        for key, value in raw_pairs:
            # Full composite key: [table] row_id > column
            composite_key = f"[{table_name}] {row_id} > {key}"
            facts.append(ExtractedFact(
                key=composite_key,
                value=value,
                source_chunk_id=item.chunk_id,
                source_document_id=item.document_id,
                confidence=1.0,
            ))

        return facts
