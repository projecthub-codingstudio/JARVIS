"""ContextAssembler — Pipeline Step 5: type-aware fact extraction + context assembly.

Sits between EvidenceBuilder (Step 4) and LLMGenerator (Step 7).
Follows the ChunkRouter pattern — dispatches evidence items to
type-specific extractors based on heading_path metadata.

For structured evidence (table rows): extracts facts deterministically.
For unstructured evidence (text, code): includes as reference passages.
The LLM receives pre-extracted facts, not raw evidence.

Query-aware filtering (TableRAG "Cell Retrieval"):
  When a query contains identifiable row/column references,
  facts are filtered to only include relevant cells.
  This prevents LLM confusion from irrelevant similar-looking data.

Research basis:
  - TableRAG (NeurIPS 2024): Schema+Cell retrieval separation
  - Microsoft "Table Meets LLM": LLMs unreliable at cell extraction
  - TabRAG: Structured intermediate representation before generation
"""
from __future__ import annotations

import re
from pathlib import Path

from jarvis.contracts import (
    AssembledContext,
    ExtractedFact,
    EvidenceItem,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.extractors.code import CodeExtractor
from jarvis.retrieval.extractors.table import TableExtractor
from jarvis.retrieval.extractors.text import TextExtractor

_DEFAULT_MAX_CONTEXT_CHARS = 16_384
_STRUCTURED_TABLE_SUFFIXES = {".xlsx", ".csv", ".tsv"}

# Generic identifier extraction: numbers followed by ordinal/unit markers
_ROW_ID_RE = re.compile(r"(\d+)\s*(?:일\s*차|일차|일|번째|번|day|row|항)", re.IGNORECASE)


class ContextAssembler:
    """Type-aware evidence extraction and context assembly.

    Implements ContextAssemblerProtocol.
    Dispatches to extractors following ChunkRouter pattern.
    Applies query-aware filtering to reduce fact noise.
    """

    def __init__(self, *, max_context_chars: int = _DEFAULT_MAX_CONTEXT_CHARS) -> None:
        self._max_context_chars = max_context_chars
        self._table = TableExtractor()
        self._text = TextExtractor()
        self._code = CodeExtractor()

    def assemble(
        self,
        evidence: VerifiedEvidenceSet,
        query: str,
    ) -> AssembledContext:
        """Extract facts and assemble context from verified evidence.

        When the query references specific row identifiers (e.g., "2일차", "Day 5"),
        table facts are filtered to only include rows matching those identifiers.
        This implements TableRAG's Cell Retrieval concept — the LLM receives
        only the cells it needs, not the entire table.
        """
        all_facts: list[ExtractedFact] = []
        passages: list[str] = []
        budget = self._max_context_chars

        for item in evidence.items:
            if budget <= 0:
                break

            extractor = self._select_extractor(item)

            if extractor is self._table:
                extracted = extractor.extract(item)
                for fact in extracted:
                    cost = len(fact.key) + len(fact.value) + 4
                    if budget - cost < 0:
                        break
                    all_facts.append(fact)
                    budget -= cost
            else:
                passage = extractor.extract(item)
                cost = len(passage)
                if budget - cost < 0:
                    remaining = budget
                    if remaining > 100:
                        passages.append(passage[:remaining] + "...")
                        budget = 0
                    break
                passages.append(passage)
                budget -= cost

        # Query-aware Cell Retrieval: filter facts to query-relevant rows
        filtered_facts = self._filter_facts_by_query(all_facts, query)

        return AssembledContext(
            facts=tuple(filtered_facts),
            text_passages=tuple(passages),
        )

    def _filter_facts_by_query(
        self, facts: list[ExtractedFact], query: str
    ) -> list[ExtractedFact]:
        """Filter facts to only include rows referenced in the query.

        Extracts numeric identifiers from the query (e.g., "2일차" → "2")
        and keeps only facts whose composite key contains a matching row ID.
        If no identifiers found in query, returns all facts unfiltered.

        This is the generic Cell Retrieval step from TableRAG —
        applicable to any table data, not specific to any domain.
        """
        query_ids = set(_ROW_ID_RE.findall(query))
        if not query_ids:
            return facts  # No filtering when query has no specific row references

        filtered: list[ExtractedFact] = []
        for fact in facts:
            # Check if fact's composite key contains a queried row ID
            # e.g., "Day=5 > Breakfast" matches query_id "5" via "=5 "
            key = fact.key
            matched = False
            for qid in query_ids:
                if f"={qid} " in key or f"={qid}>" in key or key.endswith(f"={qid}"):
                    matched = True
                    break
            if matched:
                filtered.append(fact)

        return filtered if filtered else facts  # Fallback to all if nothing matched

    def _select_extractor(self, item: EvidenceItem):
        """Select extraction strategy based on evidence type metadata.

        Returns the extractor object directly (ChunkRouter pattern).
        """
        hp = item.heading_path or ""
        if ("table-row" in hp or "table-full" in hp) and _is_structured_table_source(item):
            return self._table
        if "code" in hp:
            return self._code
        return self._text


def _is_structured_table_source(item: EvidenceItem) -> bool:
    if not item.source_path:
        return True
    return Path(item.source_path).suffix.lower() in _STRUCTURED_TABLE_SUFFIXES
