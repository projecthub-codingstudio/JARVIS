"""FreshnessChecker — validates citation freshness states and computes score boosts.

Per Spec Task 1.3:
  - Time-based freshness filtering via max_age_seconds
  - STALE auto-detection: file modified since last indexing → STALE
  - Freshness score boost: recently modified files get higher relevance

Per Spec Section 11.2:
  - 최근 수정 파일은 검색 점수에 freshness 보정 적용
  - 삭제 파일은 tombstone 처리 후 색인 정리
"""
from __future__ import annotations

import hashlib
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

# Freshness boost: files modified within these windows get score multipliers.
# More recent = higher boost. Beyond 7 days = no boost.
_FRESHNESS_TIERS: list[tuple[int, float]] = [
    (3600,      0.15),   # modified within 1 hour  → +15%
    (86400,     0.10),   # modified within 1 day   → +10%
    (259200,    0.05),   # modified within 3 days  → +5%
    (604800,    0.02),   # modified within 7 days  → +2%
]


class FreshnessChecker:
    """Validates and updates citation freshness for evidence items.

    Per Spec Task 1.3: also provides time-based filtering,
    STALE auto-detection via content hash comparison,
    and freshness score boosting.
    """

    def check(self, citation: CitationRecord, document: DocumentRecord) -> CitationState:
        """Determine citation state from document status and file state.

        Checks (in priority order):
          1. Access denied/not found → ACCESS_LOST
          2. Tombstoned → MISSING
          3. Currently re-indexing → REINDEXING
          4. Index failed → STALE
          5. File content changed since indexing → STALE
          6. Otherwise → VALID
        """
        if document.access_status in (AccessStatus.DENIED, AccessStatus.NOT_FOUND):
            return CitationState.ACCESS_LOST
        if document.indexing_status == IndexingStatus.TOMBSTONED:
            return CitationState.MISSING
        if document.indexing_status == IndexingStatus.INDEXING:
            return CitationState.REINDEXING
        if document.indexing_status == IndexingStatus.FAILED:
            return CitationState.STALE

        # STALE auto-detection: compare current file hash with indexed hash
        if document.indexing_status == IndexingStatus.INDEXED and document.path:
            try:
                file_path = Path(document.path)
                if not file_path.exists():
                    return CitationState.MISSING
                current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if current_hash != document.content_hash:
                    return CitationState.STALE
            except OSError:
                pass  # Can't check — assume VALID

        return CitationState.VALID

    def refresh_citation(
        self, citation: CitationRecord, document: DocumentRecord
    ) -> CitationRecord:
        new_state = self.check(citation, document)
        return replace(citation, state=new_state)

    def compute_freshness_boost(self, document: DocumentRecord) -> float:
        """Compute a score boost based on how recently the source file was modified.

        Per Spec Section 11.2: 최근 수정 파일은 검색 점수에 freshness 보정 적용.

        Returns a boost value (0.0 to 0.15) to add to the relevance score.
        """
        if not document.path:
            return 0.0

        try:
            file_path = Path(document.path)
            if not file_path.exists():
                return 0.0
            age_seconds = time.time() - file_path.stat().st_mtime
        except OSError:
            return 0.0

        for max_age, boost in _FRESHNESS_TIERS:
            if age_seconds <= max_age:
                return boost

        return 0.0

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
