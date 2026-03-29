from __future__ import annotations

from pathlib import Path

from jarvis.identifier_restoration import (
    build_identifier_lexicon,
    load_voice_query_samples,
    rewrite_query_with_identifiers,
    score_identifier_candidates,
)


def _build_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    (kb / "pipeline.py").write_text(
        """
class Pipeline:
    def describe(self) -> str:
        provider_result = "ok"
        return provider_result
""".strip(),
        encoding="utf-8",
    )
    return kb


def _build_symbol_heavy_kb(tmp_path: Path) -> Path:
    kb = tmp_path / "knowledge_base"
    kb.mkdir()
    (kb / "pipeline.py").write_text(
        """
class DebateRound:
    def __init__(self, opinion_id: str, min_debate_rounds: int) -> None:
        self.opinion_id = opinion_id
        self.min_debate_rounds = min_debate_rounds
""".strip(),
        encoding="utf-8",
    )
    return kb


def test_build_identifier_lexicon_extracts_code_symbols(tmp_path: Path) -> None:
    kb = _build_kb(tmp_path)

    lexicon = build_identifier_lexicon(kb)
    canonicals = {entry.canonical for entry in lexicon}

    assert "pipeline.py" in canonicals
    assert "Pipeline" in canonicals
    assert "provider_result" in canonicals


def test_score_identifier_candidates_ranks_spoken_code_terms(tmp_path: Path) -> None:
    kb = _build_kb(tmp_path)
    lexicon = build_identifier_lexicon(kb)

    candidates = score_identifier_candidates(
        "파이프라인점 파이에 있는 프로바이더 리절트 설명해줘",
        lexicon,
        limit=3,
    )

    canonicals = [candidate.canonical for candidate in candidates]
    assert "pipeline.py" in canonicals
    assert "provider_result" in canonicals


def test_rewrite_query_with_identifiers_appends_high_confidence_anchors(tmp_path: Path) -> None:
    kb = _build_kb(tmp_path)

    rewrite = rewrite_query_with_identifiers(
        "다시 파이선 소스인 파이프라인에서 클래스 파이프라인에 대해 설명해 줘",
        knowledge_base_path=kb,
    )

    assert rewrite.original_query in rewrite.rewritten_query
    assert "pipeline.py" in rewrite.appended_terms
    assert "Pipeline" in rewrite.appended_terms


def test_rewrite_query_with_identifiers_handles_korean_suffixes(tmp_path: Path) -> None:
    kb = _build_kb(tmp_path)

    rewrite = rewrite_query_with_identifiers(
        "파이프라인.py라는 파일에서 파이프라인이라는 클래스를 설명해줘",
        knowledge_base_path=kb,
    )

    assert "pipeline.py" in rewrite.rewritten_query
    assert "Pipeline" in rewrite.rewritten_query


def test_score_identifier_candidates_skips_symbols_for_non_code_queries(tmp_path: Path) -> None:
    kb = _build_symbol_heavy_kb(tmp_path)
    lexicon = build_identifier_lexicon(kb)

    candidates = score_identifier_candidates(
        "다이어트 식단표에서 3일차 저녁 메뉴 알려줘요",
        lexicon,
        limit=5,
    )

    assert candidates == ()


def test_load_voice_query_samples_and_rewrite_against_eval_set(tmp_path: Path) -> None:
    kb = _build_kb(tmp_path)
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "voice_query_eval.json"

    samples = load_voice_query_samples(fixture_path)

    assert len(samples) >= 2
    for sample in samples:
        rewrite = rewrite_query_with_identifiers(
            sample.query,
            knowledge_base_path=kb,
        )
        for expected in sample.expected_identifiers:
            assert expected in rewrite.rewritten_query
