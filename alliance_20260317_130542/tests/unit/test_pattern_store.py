from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.learning import schema_sql_path
from jarvis.learning.session_event import SessionEvent
from jarvis.learning.learned_pattern import LearnedPattern, ReformulationType
from jarvis.learning.pattern_store import PatternStore


@pytest.fixture
def store(tmp_path: Path) -> PatternStore:
    db_path = tmp_path / "learning.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(Path(schema_sql_path()).read_text(encoding="utf-8"))
    return PatternStore(db=conn)


def _event(**over: object) -> SessionEvent:
    defaults = dict(
        event_id="e-1", session_id="s-1", turn_id="t-1",
        query_text="hello", retrieval_task="document_qa", entities={},
        outcome="answer", reason_code="supported", citation_paths=[],
        confidence=0.8, created_at=1000,
    )
    defaults.update(over)
    return SessionEvent(**defaults)


def _pattern(**over: object) -> LearnedPattern:
    defaults = dict(
        pattern_id="p-1", canonical_query="q", failed_variants=[],
        retrieval_task="table_lookup",
        entity_hints={"row_ids": ["3"]},
        reformulation_type=ReformulationType.SPECIALIZATION,
        success_count=1, citation_paths=[],
        created_at=1000, last_used_at=1000,
    )
    defaults.update(over)
    return LearnedPattern(**defaults)


def test_save_and_fetch_event(store: PatternStore) -> None:
    store.save_event(_event())
    events = store.get_session_events("s-1")
    assert len(events) == 1
    assert events[0].query_text == "hello"


def test_get_unanalyzed_events_excludes_recent(store: PatternStore) -> None:
    store.save_event(_event(event_id="old", query_text="old query", created_at=100))
    store.save_event(_event(event_id="recent", query_text="recent query", created_at=10_000))
    unanalyzed = store.get_unanalyzed_events(before=5_000)
    ids = {e.event_id for e in unanalyzed}
    assert "old" in ids
    assert "recent" not in ids


def test_mark_analyzed(store: PatternStore) -> None:
    store.save_event(_event())
    store.mark_analyzed(["e-1"], analyzed_at=2000)
    unanalyzed = store.get_unanalyzed_events(before=5_000)
    assert unanalyzed == []


def test_save_pattern_and_fetch_by_task(store: PatternStore) -> None:
    store.save_pattern(_pattern())
    patterns = store.get_patterns_by_task("table_lookup")
    assert len(patterns) == 1
    assert patterns[0].pattern_id == "p-1"


def test_increment_pattern_usage(store: PatternStore) -> None:
    store.save_pattern(_pattern())
    store.increment_pattern_usage("p-1", now=5000)
    fetched = store.get_pattern("p-1")
    assert fetched is not None
    assert fetched.success_count == 2
    assert fetched.last_used_at == 5000


def test_get_pattern_returns_none_for_missing(store: PatternStore) -> None:
    assert store.get_pattern("missing") is None


def test_save_event_replaces_prior_event_for_same_session_query(store: PatternStore) -> None:
    """When fallback calls handle_turn twice for the same session+query,
    only the latest event should remain."""
    store.save_event(_event(
        event_id="first", session_id="s1", query_text="diet query",
        entities={"topic": ["diet"]}, created_at=1000,
    ))
    store.save_event(_event(
        event_id="second", session_id="s1", query_text="diet query",
        entities={}, created_at=1050,
    ))
    events = store.get_session_events("s1")
    assert len(events) == 1
    assert events[0].event_id == "second"
    assert events[0].entities == {}


def test_save_event_keeps_distinct_queries_separate(store: PatternStore) -> None:
    store.save_event(_event(event_id="a", session_id="s1", query_text="query A"))
    store.save_event(_event(event_id="b", session_id="s1", query_text="query B"))
    events = store.get_session_events("s1")
    assert len(events) == 2
