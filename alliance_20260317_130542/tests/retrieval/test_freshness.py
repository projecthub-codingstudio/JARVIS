"""Tests for FreshnessChecker."""
from __future__ import annotations

from jarvis.contracts import (
    CitationRecord, CitationState, DocumentRecord, IndexingStatus, AccessStatus,
)
from jarvis.retrieval.freshness import FreshnessChecker


class TestFreshnessChecker:
    def test_indexed_accessible_is_valid(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.INDEXED, access_status=AccessStatus.ACCESSIBLE)
        assert checker.check(citation, doc) == CitationState.VALID

    def test_tombstoned_is_missing(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.TOMBSTONED)
        assert checker.check(citation, doc) == CitationState.MISSING

    def test_reindexing_is_reindexing(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.INDEXING)
        assert checker.check(citation, doc) == CitationState.REINDEXING

    def test_access_denied_is_access_lost(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.INDEXED, access_status=AccessStatus.DENIED)
        assert checker.check(citation, doc) == CitationState.ACCESS_LOST

    def test_not_found_is_access_lost(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            access_status=AccessStatus.NOT_FOUND)
        assert checker.check(citation, doc) == CitationState.ACCESS_LOST

    def test_failed_indexing_is_stale(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]")
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.FAILED)
        assert checker.check(citation, doc) == CitationState.STALE

    def test_refresh_citation(self) -> None:
        checker = FreshnessChecker()
        citation = CitationRecord(document_id="d1", chunk_id="c1", label="[1]",
            state=CitationState.VALID)
        doc = DocumentRecord(document_id="d1", path="/f.md",
            indexing_status=IndexingStatus.TOMBSTONED)
        refreshed = checker.refresh_citation(citation, doc)
        assert refreshed.state == CitationState.MISSING
        assert refreshed.citation_id == citation.citation_id
