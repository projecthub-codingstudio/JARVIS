from __future__ import annotations

from pathlib import Path

from jarvis import query_normalization
from jarvis.query_normalization import normalize_spoken_code_query


def test_normalize_spoken_query_prefers_substantive_clause() -> None:
    normalized = normalize_spoken_code_query(
        "안녕하세요. 한국 문서 8형식 중에 그리기 개체 자료 구조 중에 기본 구조에 대해 설명해 주세요. 왠 조화 두롱이드가?"
    )

    assert "한국 문서 8형식" in normalized
    assert "기본 구조에 대해 설명" in normalized
    assert "안녕하세요" not in normalized
    assert "두롱이드가" not in normalized


def test_normalize_spoken_query_keeps_single_substantive_clause() -> None:
    normalized = normalize_spoken_code_query("다이어트 식단표에서 11일 차 아침 메뉴 알려주세요")

    assert normalized == "다이어트 식단표에서 11일차 아침 메뉴 알려주세요"


def test_normalize_spoken_query_strips_leading_greeting_and_normalizes_korean_day_words() -> None:
    normalized = normalize_spoken_code_query("안녕하세요 다이어트 식단표 중에 삼 일차 저녁 메뉴 알려 주세요")

    assert normalized == "다이어트 식단표 중에 3일차 저녁 메뉴 알려 주세요"


def test_normalize_spoken_query_handles_stt_onecha_for_day_word() -> None:
    normalized = normalize_spoken_code_query("다이어트 식단표 에서 구 1차 점심 메뉴 알려줘")

    assert normalized == "다이어트 식단표 에서 9일차 점심 메뉴 알려줘"


def test_normalize_spoken_query_canonicalizes_diet_table_alias_and_spoken_day_slot() -> None:
    normalized = normalize_spoken_code_query("다이어트 메뉴 표 에서 육 일자 점심 메뉴 알려 주세요")

    assert normalized == "다이어트 식단표 에서 6일차 점심 메뉴 알려 주세요"


def test_normalize_spoken_query_repairs_round_suffix_for_diet_lookup() -> None:
    normalized = normalize_spoken_code_query("안녕하세요 다이어트 식단표 에서 9일 회차 아침 메뉴 알려 주세요")

    assert normalized == "다이어트 식단표 에서 9일차 아침 메뉴 알려 주세요"


def test_normalize_spoken_query_repairs_prefixed_il_noise_for_diet_lookup() -> None:
    normalized = normalize_spoken_code_query("다이어트 식단표 에서 일 1일 아침 메뉴 알려줘")

    assert normalized == "다이어트 식단표 에서 1일차 아침 메뉴 알려줘"


def test_normalize_spoken_query_restores_korean_vocabulary_terms(monkeypatch) -> None:
    query_normalization._indexed_korean_vocabulary.cache_clear()
    monkeypatch.setattr(
        query_normalization,
        "load_indexed_vocabulary_terms",
        lambda: ["한글", "형식", "개체", "그리기"],
    )

    normalized = normalize_spoken_code_query(
        "흥글 문서 8형씨에서 그리기 개최 자료 구조 중에 기본 구조에 대해 설명해 주세요"
    )

    assert "한글" in normalized
    assert "형식" in normalized
    assert "개체" in normalized


def test_normalize_spoken_query_does_not_append_code_symbols_for_document_lookup(tmp_path: Path) -> None:
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

    normalized = normalize_spoken_code_query(
        "다이어트 식단표에서 3일차 저녁 메뉴 알려줘요",
        knowledge_base_path=Path(kb),
    )

    assert normalized == "다이어트 식단표에서 3일차 저녁 메뉴 알려줘요"
