"""Type-specific evidence extractors for ContextAssembler.

Each extractor follows the ChunkRouter strategy pattern:
- Receives an EvidenceItem
- Returns extracted data (facts or passages)
- ContextAssembler dispatches via heading_path metadata
"""
from __future__ import annotations

from typing import Protocol

from jarvis.contracts import EvidenceItem, ExtractedFact


class FactExtractorProtocol(Protocol):
    """Extracts structured facts from an evidence item."""

    def extract(self, item: EvidenceItem) -> list[ExtractedFact]: ...


class PassageExtractorProtocol(Protocol):
    """Extracts text passages from an evidence item."""

    def extract(self, item: EvidenceItem) -> str: ...
