"""TextExtractor — passage extraction from unstructured text evidence."""
from __future__ import annotations

from jarvis.contracts import EvidenceItem


class TextExtractor:
    """Extracts text passages for LLM interpretation (no deterministic facts)."""

    def extract(self, item: EvidenceItem) -> str:
        return item.text.strip()
