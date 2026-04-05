from __future__ import annotations

from jarvis.learning.session_event import SessionEvent
from jarvis.learning.reformulation_detector import ReformulationDetector


def _evt(event_id: str, outcome: str, created_at: int, text: str = "q") -> SessionEvent:
    return SessionEvent(
        event_id=event_id, session_id="s", turn_id=event_id,
        query_text=text, retrieval_task="table_lookup", entities={},
        outcome=outcome, reason_code="", citation_paths=[],
        confidence=0.8, created_at=created_at,
    )


def test_detects_pair_within_5_min_window() -> None:
    detector = ReformulationDetector(
        similarity_fn=lambda a, b: 0.7,
        min_similarity=0.5,
        window_seconds=300,
    )
    events = [
        _evt("e1", "abstain", 1000, "diet"),
        _evt("e2", "answer", 1100, "diet day 3 dinner"),
    ]
    pairs = detector.find_pairs(events)
    assert len(pairs) == 1
    assert pairs[0].failure.event_id == "e1"
    assert pairs[0].success.event_id == "e2"


def test_skips_pair_beyond_window() -> None:
    detector = ReformulationDetector(
        similarity_fn=lambda a, b: 0.9,
        min_similarity=0.5,
        window_seconds=300,
    )
    events = [
        _evt("e1", "abstain", 1000),
        _evt("e2", "answer", 2000),
    ]
    assert detector.find_pairs(events) == []


def test_skips_pair_below_similarity_threshold() -> None:
    detector = ReformulationDetector(
        similarity_fn=lambda a, b: 0.3,
        min_similarity=0.5,
        window_seconds=300,
    )
    events = [
        _evt("e1", "abstain", 1000),
        _evt("e2", "answer", 1060),
    ]
    assert detector.find_pairs(events) == []


def test_matches_only_first_success_after_failure() -> None:
    detector = ReformulationDetector(
        similarity_fn=lambda a, b: 0.9,
        min_similarity=0.5,
        window_seconds=300,
    )
    events = [
        _evt("e1", "abstain", 1000),
        _evt("e2", "answer", 1050),
        _evt("e3", "answer", 1100),
    ]
    pairs = detector.find_pairs(events)
    assert len(pairs) == 1
    assert pairs[0].success.event_id == "e2"


def test_also_matches_clarify_as_failure() -> None:
    detector = ReformulationDetector(
        similarity_fn=lambda a, b: 0.9,
        min_similarity=0.5,
        window_seconds=300,
    )
    events = [
        _evt("e1", "clarify", 1000),
        _evt("e2", "answer", 1060),
    ]
    pairs = detector.find_pairs(events)
    assert len(pairs) == 1
