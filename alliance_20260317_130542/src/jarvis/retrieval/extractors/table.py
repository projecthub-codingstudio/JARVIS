"""TableExtractor — deterministic fact extraction from table-row evidence.

Parses key=value pipe-delimited format produced by TableChunkStrategy.
Produces facts with composite keys for row disambiguation:
  "Day=5 > Breakfast" instead of just "Breakfast"
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

        # First column is the row identifier (e.g., Day=5)
        first_key, first_val = raw_pairs[0]
        row_id = f"{first_key}={first_val}"

        facts: list[ExtractedFact] = []
        for key, value in raw_pairs:
            composite_key = f"{row_id} > {key}"
            facts.append(ExtractedFact(
                key=composite_key,
                value=value,
                source_chunk_id=item.chunk_id,
                source_document_id=item.document_id,
                confidence=1.0,
            ))

        return facts
