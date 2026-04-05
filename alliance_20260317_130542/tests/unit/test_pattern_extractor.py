from __future__ import annotations

from jarvis.learning.session_event import SessionEvent, ReformulationPair
from jarvis.learning.learned_pattern import ReformulationType
from jarvis.learning.pattern_extractor import PatternExtractor


def _pair(failure_entities: dict, success_entities: dict, *, similarity: float = 0.7) -> ReformulationPair:
    failure = SessionEvent(
        event_id="f", session_id="s", turn_id="tf", query_text="식단",
        retrieval_task="table_lookup", entities=failure_entities,
        outcome="abstain", reason_code="weak", citation_paths=[],
        confidence=0.9, created_at=1000,
    )
    success = SessionEvent(
        event_id="s", session_id="s", turn_id="ts", query_text="식단 3일차 저녁",
        retrieval_task="table_lookup", entities=success_entities,
        outcome="answer", reason_code="supported",
        citation_paths=["/kb/diet.xlsx"], confidence=0.85, created_at=1060,
    )
    return ReformulationPair(failure=failure, success=success, similarity=similarity)


def test_detects_specialization_when_success_has_more_entities() -> None:
    ext = PatternExtractor()
    pair = _pair({}, {"row_ids": ["3"], "fields": ["dinner"]})
    assert ext.classify(pair) is ReformulationType.SPECIALIZATION


def test_detects_generalization_when_success_has_fewer_entities() -> None:
    ext = PatternExtractor()
    pair = _pair({"row_ids": ["3"], "fields": ["dinner"]}, {"row_ids": ["3"]})
    assert ext.classify(pair) is ReformulationType.GENERALIZATION


def test_detects_error_correction_when_entities_identical_and_similarity_high() -> None:
    ext = PatternExtractor()
    pair = _pair({"row_ids": ["3"]}, {"row_ids": ["3"]}, similarity=0.9)
    assert ext.classify(pair) is ReformulationType.ERROR_CORRECTION


def test_detects_parallel_move_when_entities_differ_but_count_equal() -> None:
    ext = PatternExtractor()
    pair = _pair({"row_ids": ["3"]}, {"row_ids": ["4"]}, similarity=0.6)
    assert ext.classify(pair) is ReformulationType.PARALLEL_MOVE


def test_extract_returns_none_for_generalization() -> None:
    ext = PatternExtractor()
    pair = _pair({"row_ids": ["3"], "fields": ["dinner"]}, {})
    pattern = ext.extract(pair, pattern_id="p1", now=1060)
    assert pattern is None


def test_extract_builds_pattern_for_specialization() -> None:
    ext = PatternExtractor()
    pair = _pair({}, {"row_ids": ["3"], "fields": ["dinner"]})
    pattern = ext.extract(pair, pattern_id="p1", now=1060)
    assert pattern is not None
    assert pattern.reformulation_type is ReformulationType.SPECIALIZATION
    assert pattern.entity_hints == {"row_ids": ["3"], "fields": ["dinner"]}
    assert pattern.canonical_query == "식단 3일차 저녁"
    assert pattern.failed_variants == ["식단"]
    assert pattern.citation_paths == ["/kb/diet.xlsx"]
