"""Tests for sentence-level citation verification."""

from __future__ import annotations

from jarvis.contracts import CitationRecord, EvidenceItem, VerifiedEvidenceSet
from jarvis.retrieval.citation_verifier import CitationVerifier


def _evidence_set() -> VerifiedEvidenceSet:
    item = EvidenceItem(
        chunk_id="c1",
        document_id="d1",
        text="JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval for grounded answers.",
        citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
        source_path="/tmp/architecture.md",
        relevance_score=1.0,
    )
    return VerifiedEvidenceSet(items=(item,), query_fragments=())


class TestCitationVerifier:
    def test_accepts_sentence_with_explicit_citation_label(self) -> None:
        warnings = CitationVerifier().verify(
            "JARVIS uses SQLite FTS5 and LanceDB hybrid retrieval [1].",
            _evidence_set(),
        )

        assert warnings == ()

    def test_flags_sentence_without_support(self) -> None:
        warnings = CitationVerifier().verify(
            "JARVIS automatically controls every macOS application on the screen.",
            _evidence_set(),
        )

        assert len(warnings) == 1
        assert "근거 정렬 미확인 문장" in warnings[0]
