"""ContextAssembler — Pipeline Step 5: type-aware fact extraction + context assembly.

Sits between EvidenceBuilder (Step 4) and LLMGenerator (Step 7).
Follows the ChunkRouter pattern — dispatches evidence items to
type-specific extractors based on heading_path metadata.

For structured evidence (table rows): extracts facts deterministically.
For unstructured evidence (text, code): includes as reference passages.
The LLM receives pre-extracted facts, not raw evidence.

Research basis:
  - TableRAG (NeurIPS 2024): Schema+Cell retrieval separation
  - Microsoft "Table Meets LLM": LLMs unreliable at cell extraction
  - TabRAG: Structured intermediate representation before generation
"""
from __future__ import annotations

from jarvis.contracts import (
    AssembledContext,
    EvidenceItem,
    VerifiedEvidenceSet,
)
from jarvis.retrieval.extractors.code import CodeExtractor
from jarvis.retrieval.extractors.table import TableExtractor
from jarvis.retrieval.extractors.text import TextExtractor

_DEFAULT_MAX_CONTEXT_CHARS = 16_384


class ContextAssembler:
    """Type-aware evidence extraction and context assembly.

    Implements ContextAssemblerProtocol.
    Dispatches to extractors following ChunkRouter pattern.
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
        """Extract facts and assemble context from verified evidence."""
        facts: list = []
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
                    facts.append(fact)
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

        return AssembledContext(
            facts=tuple(facts),
            text_passages=tuple(passages),
        )

    def _select_extractor(self, item: EvidenceItem):
        """Select extraction strategy based on evidence type metadata.

        Returns the extractor object directly (ChunkRouter pattern).
        """
        hp = item.heading_path or ""
        if "table-row" in hp or "table-full" in hp:
            return self._table
        if "code" in hp:
            return self._code
        return self._text
