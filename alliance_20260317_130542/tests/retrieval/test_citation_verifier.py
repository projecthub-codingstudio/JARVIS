"""Tests for claim-level citation verification."""

from __future__ import annotations

from jarvis.contracts import CitationRecord, EvidenceItem, VerifiedEvidenceSet
from jarvis.retrieval.citation_verifier import CitationVerifier, _split_claims


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


def _multi_evidence_set() -> VerifiedEvidenceSet:
    item1 = EvidenceItem(
        chunk_id="c1", document_id="d1",
        text="EXAONE-3.5-7.8B delivers 1.5 second latency with 3/3 accuracy.",
        citation=CitationRecord(document_id="d1", chunk_id="c1", label="[1]"),
        relevance_score=1.0,
    )
    item2 = EvidenceItem(
        chunk_id="c2", document_id="d2",
        text="Day=5 | Breakfast=요거트 | Lunch=닭가슴살 | Calories=350",
        citation=CitationRecord(document_id="d2", chunk_id="c2", label="[2]"),
        relevance_score=0.9,
    )
    return VerifiedEvidenceSet(items=(item1, item2), query_fragments=())


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
        assert "근거 미확인" in warnings[0]

    def test_accepts_sentence_with_token_overlap(self) -> None:
        warnings = CitationVerifier().verify(
            "The system uses SQLite FTS5 for hybrid retrieval of indexed documents.",
            _evidence_set(),
        )
        assert warnings == ()

    def test_empty_answer_returns_no_warnings(self) -> None:
        assert CitationVerifier().verify("", _evidence_set()) == ()

    def test_empty_evidence_returns_no_warnings(self) -> None:
        evidence = VerifiedEvidenceSet(items=(), query_fragments=())
        assert CitationVerifier().verify("Some answer text.", evidence) == ()

    def test_short_sentences_skipped(self) -> None:
        warnings = CitationVerifier().verify("OK.", _evidence_set())
        assert warnings == ()


class TestClaimSplitting:
    def test_splits_korean_conjunctions(self) -> None:
        claims = _split_claims("EXAONE-3.5는 1.5초이고 EXAONE-4.0은 8.8초입니다")
        assert len(claims) >= 2

    def test_splits_english_conjunctions(self) -> None:
        claims = _split_claims("The model has low latency, and it achieves high accuracy")
        assert len(claims) >= 2

    def test_single_claim_stays_intact(self) -> None:
        claims = _split_claims("JARVIS uses SQLite for retrieval")
        assert len(claims) == 1

    def test_filters_short_fragments(self) -> None:
        claims = _split_claims("A, B, and some meaningful claim here")
        assert all(len(c) >= 6 for c in claims)


class TestClaimLevelVerification:
    def test_compound_sentence_partial_support(self) -> None:
        """A sentence with supported + unsupported claims should flag the unsupported part."""
        answer = "EXAONE-3.5-7.8B는 1.5초 레이턴시이고 GPT-4보다 10배 빠릅니다."
        warnings = CitationVerifier().verify(answer, _multi_evidence_set())
        # "GPT-4보다 10배 빠릅니다" has no evidence support
        assert len(warnings) >= 1
        assert any("GPT-4" in w or "10배" in w for w in warnings)

    def test_numeric_value_matching(self) -> None:
        """Numeric values in claims should be checked against evidence."""
        answer = "5일차 점심은 닭가슴살이며 칼로리는 350입니다."
        warnings = CitationVerifier().verify(answer, _multi_evidence_set())
        # Both claims are supported by evidence (Day=5, Lunch=닭가슴살, Calories=350)
        assert len(warnings) == 0

    def test_fully_supported_compound(self) -> None:
        """All claims supported → no warnings."""
        answer = "EXAONE-3.5-7.8B는 1.5 second latency이고 3/3 accuracy를 달성합니다."
        warnings = CitationVerifier().verify(answer, _multi_evidence_set())
        assert len(warnings) == 0
