"""CodeExtractor — passage extraction from code evidence."""
from __future__ import annotations

from jarvis.contracts import EvidenceItem


class CodeExtractor:
    """Extracts code passages for LLM interpretation."""

    def extract(self, item: EvidenceItem) -> str:
        text = item.text.strip()
        if item.heading_path:
            scope = item.heading_path.replace("-", " > ")
            return f"[{scope}]\n{text}"
        return text
