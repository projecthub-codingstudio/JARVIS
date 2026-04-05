"""E2E scenario: failure then success within session, pattern extracted, hints applied on new query."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import pytest

from jarvis.learning import schema_sql_path
from jarvis.learning.coordinator import LearningCoordinator
from jarvis.learning.pattern_store import PatternStore


def _embed(text: str) -> list[float]:
    # Deterministic bag-of-chars embedding (8-dim)
    vec = [0.0] * 8
    for i, c in enumerate(text):
        vec[i % 8] += (ord(c) % 31) / 31.0
    return vec


def _similarity(a: str, b: str) -> float:
    ea = _embed(a)
    eb = _embed(b)
    dot = sum(x * y for x, y in zip(ea, eb))
    na = math.sqrt(sum(x * x for x in ea))
    nb = math.sqrt(sum(y * y for y in eb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@pytest.fixture
def coordinator(tmp_path: Path) -> LearningCoordinator:
    conn = sqlite3.connect(str(tmp_path / "e2e.db"))
    conn.executescript(Path(schema_sql_path()).read_text(encoding="utf-8"))
    store = PatternStore(db=conn)
    return LearningCoordinator(
        store=store,
        embed_fn=_embed,
        similarity_fn=_similarity,
        now=lambda: 10_000,
        min_pair_similarity=0.3,   # Relaxed for this stub embedder
        min_match_similarity=0.5,  # Relaxed for this stub embedder
    )


def test_scenario_specialization_learned_and_applied(coordinator: LearningCoordinator) -> None:
    # Session 1: user asks too-broad then refines
    coordinator.record_outcome(
        session_id="s1", turn_id="t1",
        query_text="다이어트 식단표 알려줘",
        retrieval_task="table_lookup", entities={},
        outcome="abstain", reason_code="weak_evidence",
        citation_paths=[], confidence=0.86, now_override=1000,
    )
    coordinator.record_outcome(
        session_id="s1", turn_id="t2",
        query_text="다이어트 식단표에서 3일차 저녁 메뉴",
        retrieval_task="table_lookup",
        entities={"row_ids": ["3"], "fields": ["dinner"]},
        outcome="answer", reason_code="supported",
        citation_paths=["/kb/diet.xlsx"], confidence=0.88, now_override=1080,
    )

    created = coordinator.analyze_unanalyzed(before=5000)
    assert created == 1, "should create one specialization pattern"

    coordinator.refresh_index()

    hints = coordinator.find_hints(
        query="다이어트 식단표에서 5일차 저녁 메뉴",
        retrieval_task="table_lookup",
    )
    assert hints is not None, "learned pattern should match new similar query"
    assert set(hints.keys()) <= {"row_ids", "fields"}


def test_scenario_parallel_move_stored(coordinator: LearningCoordinator) -> None:
    coordinator.record_outcome(
        session_id="s2", turn_id="t1", query_text="식단 메뉴",
        retrieval_task="table_lookup", entities={},
        outcome="clarify", reason_code="underspecified_query",
        citation_paths=[], confidence=0.84, now_override=2000,
    )
    coordinator.record_outcome(
        session_id="s2", turn_id="t2", query_text="식단 7일차 아침",
        retrieval_task="table_lookup",
        entities={"row_ids": ["7"], "fields": ["breakfast"]},
        outcome="answer", reason_code="supported",
        citation_paths=[], confidence=0.9, now_override=2060,
    )

    created = coordinator.analyze_unanalyzed(before=5000)
    assert created == 1

    coordinator.refresh_index()
    hints = coordinator.find_hints(query="식단 9일차 저녁", retrieval_task="table_lookup")
    assert hints is not None


def test_scenario_explicit_entities_win_over_learned() -> None:
    from jarvis.learning.hint_injector import merge_entities
    explicit = {"row_ids": ["10"]}
    learned = {"row_ids": ["3"], "fields": ["dinner"]}
    merged = merge_entities(explicit=explicit, learned=learned)
    assert merged["row_ids"] == ["10"]
    assert merged["fields"] == ["dinner"]
