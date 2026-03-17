"""FreshnessChecker — validates citation freshness states."""
from __future__ import annotations

from dataclasses import replace

from jarvis.contracts import (
    AccessStatus,
    CitationRecord,
    CitationState,
    DocumentRecord,
    IndexingStatus,
)


class FreshnessChecker:
    """Validates and updates citation freshness for evidence items."""

    def check(self, citation: CitationRecord, document: DocumentRecord) -> CitationState:
        if document.access_status in (AccessStatus.DENIED, AccessStatus.NOT_FOUND):
            return CitationState.ACCESS_LOST
        if document.indexing_status == IndexingStatus.TOMBSTONED:
            return CitationState.MISSING
        if document.indexing_status == IndexingStatus.INDEXING:
            return CitationState.REINDEXING
        if document.indexing_status == IndexingStatus.FAILED:
            return CitationState.STALE
        return CitationState.VALID

    def refresh_citation(
        self, citation: CitationRecord, document: DocumentRecord
    ) -> CitationRecord:
        new_state = self.check(citation, document)
        return replace(citation, state=new_state)
