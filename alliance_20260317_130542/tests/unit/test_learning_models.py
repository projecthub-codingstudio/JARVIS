from __future__ import annotations

import time

from jarvis.learning.session_event import SessionEvent, ReformulationPair
from jarvis.learning.learned_pattern import LearnedPattern, ReformulationType


def test_session_event_roundtrip_json() -> None:
    event = SessionEvent(
        event_id="evt-1",
        session_id="sess-A",
        turn_id="turn-1",
        query_text="다이어트 식단표 알려줘",
        retrieval_task="table_lookup",
        entities={"row_ids": []},
        outcome="abstain",
        reason_code="weak_evidence",
        citation_paths=[],
        confidence=0.86,
        created_at=1_700_000_000,
    )
    payload = event.to_row()
    restored = SessionEvent.from_row(payload)
    assert restored == event


def test_reformulation_pair_holds_failure_and_success() -> None:
    failure = SessionEvent(
        event_id="e1", session_id="s1", turn_id="t1", query_text="식단",
        retrieval_task="table_lookup", entities={}, outcome="abstain",
        reason_code="weak_evidence", citation_paths=[], confidence=0.9,
        created_at=1_000,
    )
    success = SessionEvent(
        event_id="e2", session_id="s1", turn_id="t2", query_text="식단 3일차 저녁",
        retrieval_task="table_lookup", entities={"row_ids": ["3"], "fields": ["dinner"]},
        outcome="answer", reason_code="supported", citation_paths=["/kb/diet.xlsx"],
        confidence=0.88, created_at=1_060,
    )
    pair = ReformulationPair(failure=failure, success=success, similarity=0.72)
    assert pair.delta_seconds == 60
    assert pair.similarity == 0.72


def test_learned_pattern_created_from_pair() -> None:
    pattern = LearnedPattern(
        pattern_id="pat-1",
        canonical_query="식단 3일차 저녁",
        failed_variants=["식단"],
        retrieval_task="table_lookup",
        entity_hints={"row_ids": ["3"], "fields": ["dinner"]},
        reformulation_type=ReformulationType.SPECIALIZATION,
        success_count=1,
        citation_paths=["/kb/diet.xlsx"],
        created_at=1_000,
        last_used_at=1_000,
    )
    assert pattern.reformulation_type is ReformulationType.SPECIALIZATION
    assert pattern.success_count == 1
