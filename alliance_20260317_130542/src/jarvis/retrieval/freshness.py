"""FreshnessChecker — validates citation freshness states.

Per Spec Task 1.3: includes time-based freshness filtering
via max_age_seconds on search results.
"""
from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from jarvis.contracts import (
    AccessStatus,
    CitationRecord,
    CitationState,
    DocumentRecord,
    HybridSearchResult,
    IndexingStatus,
)


class FreshnessChecker:
    """Validates and updates citation freshness for evidence items.

    Per Spec Task 1.3: also provides time-based filtering
    via filter_by_age().
    """

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

    def filter_by_age(
        self,
        results: Sequence[HybridSearchResult],
        *,
        max_age_seconds: int,
        db: object,
    ) -> list[HybridSearchResult]:
        """Filter search results by document modification time.

        Per Spec Task 1.3: drop results from documents older than
        max_age_seconds.
        """
        if max_age_seconds <= 0:
            return list(results)

        now = time.time()
        filtered: list[HybridSearchResult] = []

        for result in results:
            try:
                row = db.execute(  # type: ignore[union-attr]
                    "SELECT path FROM documents WHERE document_id = ?",
                    (result.document_id,),
                ).fetchone()
                if row is None:
                    continue
                file_path = Path(row[0])
                if file_path.exists():
                    mtime = file_path.stat().st_mtime
                    if (now - mtime) <= max_age_seconds:
                        filtered.append(result)
                else:
                    # File missing — include anyway, freshness check will catch it
                    filtered.append(result)
            except Exception:
                filtered.append(result)

        return filtered
