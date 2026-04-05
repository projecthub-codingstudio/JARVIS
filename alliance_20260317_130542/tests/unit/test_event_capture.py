from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.learning import schema_sql_path
from jarvis.learning.pattern_store import PatternStore
from jarvis.learning.event_capture import SessionEventCapture


@pytest.fixture
def store(tmp_path: Path) -> PatternStore:
    conn = sqlite3.connect(str(tmp_path / "learning.db"))
    conn.executescript(Path(schema_sql_path()).read_text(encoding="utf-8"))
    return PatternStore(db=conn)


def test_capture_abstain_event(store: PatternStore) -> None:
    capture = SessionEventCapture(store=store, now=lambda: 1000)
    capture.record(
        session_id="s1", turn_id="t1",
        query_text="다이어트 식단",
        retrieval_task="table_lookup",
        entities={},
        outcome="abstain", reason_code="weak_evidence",
        citation_paths=[], confidence=0.86,
    )
    events = store.get_session_events("s1")
    assert len(events) == 1
    assert events[0].outcome == "abstain"
    assert events[0].query_text == "다이어트 식단"
    assert events[0].created_at == 1000


def test_capture_generates_unique_event_id(store: PatternStore) -> None:
    capture = SessionEventCapture(store=store, now=lambda: 1000)
    capture.record(session_id="s1", turn_id="t1", query_text="q1",
                   retrieval_task="document_qa", entities={}, outcome="answer",
                   reason_code="supported", citation_paths=[], confidence=0.8)
    capture.record(session_id="s1", turn_id="t2", query_text="q2",
                   retrieval_task="document_qa", entities={}, outcome="answer",
                   reason_code="supported", citation_paths=[], confidence=0.8)
    events = store.get_session_events("s1")
    ids = {e.event_id for e in events}
    assert len(ids) == 2
