from __future__ import annotations

from jarvis.learning.learned_pattern import LearnedPattern, ReformulationType
from jarvis.learning.pattern_matcher import PatternMatcher, PatternMatch


def _pattern(pid: str, task: str = "table_lookup") -> LearnedPattern:
    return LearnedPattern(
        pattern_id=pid, canonical_query=f"q-{pid}", failed_variants=[],
        retrieval_task=task, entity_hints={"row_ids": ["3"]},
        reformulation_type=ReformulationType.SPECIALIZATION,
        success_count=1, citation_paths=[],
        created_at=1000, last_used_at=1000,
    )


def _embed_stub(text: str) -> list[float]:
    base = ord(text[0]) if text else 0
    return [base / 128.0] * 8


def test_empty_matcher_returns_no_matches() -> None:
    matcher = PatternMatcher(embed_fn=_embed_stub, min_similarity=0.75)
    matches = matcher.find("some query", retrieval_task="table_lookup")
    assert matches == []


def test_matcher_returns_hit_above_threshold() -> None:
    matcher = PatternMatcher(embed_fn=_embed_stub, min_similarity=0.75)
    matcher.index([
        (_pattern("p1"), _embed_stub("query about diet")),
    ])
    matches = matcher.find("query asking diet", retrieval_task="table_lookup")
    assert len(matches) == 1
    assert matches[0].pattern.pattern_id == "p1"
    assert matches[0].score >= 0.75


def test_matcher_filters_by_retrieval_task() -> None:
    matcher = PatternMatcher(embed_fn=_embed_stub, min_similarity=0.5)
    matcher.index([
        (_pattern("p1", task="table_lookup"), _embed_stub("a")),
        (_pattern("p2", task="document_qa"), _embed_stub("a")),
    ])
    matches = matcher.find("a", retrieval_task="table_lookup")
    ids = {m.pattern.pattern_id for m in matches}
    assert ids == {"p1"}


def test_matcher_returns_top_k() -> None:
    matcher = PatternMatcher(embed_fn=_embed_stub, min_similarity=0.0, top_k=2)
    matcher.index([
        (_pattern(f"p{i}"), _embed_stub("a")) for i in range(5)
    ])
    matches = matcher.find("a", retrieval_task="table_lookup")
    assert len(matches) == 2
