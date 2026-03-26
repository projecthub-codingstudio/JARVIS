from __future__ import annotations

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

    assert normalized == "다이어트 식단표에서 11일 차 아침 메뉴 알려주세요"


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
