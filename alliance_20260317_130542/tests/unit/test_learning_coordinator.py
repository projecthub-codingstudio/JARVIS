from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jarvis.learning import schema_sql_path
from jarvis.learning.coordinator import LearningCoordinator
from jarvis.learning.pattern_store import PatternStore


def _embed(text: str) -> list[float]:
    base = [0.0] * 8
    for i, c in enumerate(text):
        base[i % 8] += ord(c) / 1000.0
    return base


def _similarity(a: str, b: str) -> float:
    emb_a = _embed(a)
    emb_b = _embed(b)
    import math
    dot = sum(x * y for x, y in zip(emb_a, emb_b))
    na = math.sqrt(sum(x * x for x in emb_a))
    nb = math.sqrt(sum(y * y for y in emb_b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@pytest.fixture
def coord(tmp_path: Path) -> LearningCoordinator:
    conn = sqlite3.connect(str(tmp_path / "l.db"))
    conn.executescript(Path(schema_sql_path()).read_text(encoding="utf-8"))
    store = PatternStore(db=conn)
    return LearningCoordinator(
        store=store,
        embed_fn=_embed,
        similarity_fn=_similarity,
        now=lambda: 2000,
    )


def test_record_then_analyze_creates_pattern(coord: LearningCoordinator) -> None:
    coord.record_outcome(
        session_id="s1", turn_id="t1", query_text="식단 알려줘",
        retrieval_task="table_lookup", entities={},
        outcome="abstain", reason_code="weak", citation_paths=[],
        confidence=0.86, now_override=1000,
    )
    coord.record_outcome(
        session_id="s1", turn_id="t2", query_text="식단 3일차 저녁",
        retrieval_task="table_lookup",
        entities={"row_ids": ["3"], "fields": ["dinner"]},
        outcome="answer", reason_code="supported",
        citation_paths=["/kb/diet.xlsx"], confidence=0.88, now_override=1100,
    )

    created = coord.analyze_unanalyzed(before=1500)
    assert created == 1

    coord.refresh_index()
    hints = coord.find_hints(query="식단 5일차 저녁", retrieval_task="table_lookup")
    assert hints is not None
    assert "row_ids" in hints or "fields" in hints


def test_analyze_is_idempotent(coord: LearningCoordinator) -> None:
    coord.record_outcome(
        session_id="s1", turn_id="t1", query_text="식단",
        retrieval_task="table_lookup", entities={},
        outcome="abstain", reason_code="weak", citation_paths=[],
        confidence=0.86, now_override=1000,
    )
    coord.record_outcome(
        session_id="s1", turn_id="t2", query_text="식단 3일차 저녁",
        retrieval_task="table_lookup",
        entities={"row_ids": ["3"], "fields": ["dinner"]},
        outcome="answer", reason_code="supported",
        citation_paths=[], confidence=0.88, now_override=1060,
    )
    first = coord.analyze_unanalyzed(before=1500)
    second = coord.analyze_unanalyzed(before=1500)
    assert first == 1
    assert second == 0


def test_find_hints_returns_none_when_no_match(coord: LearningCoordinator) -> None:
    coord.refresh_index()
    hints = coord.find_hints(query="unrelated", retrieval_task="document_qa")
    assert hints is None
