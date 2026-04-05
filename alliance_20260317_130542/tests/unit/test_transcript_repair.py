from __future__ import annotations

from jarvis.transcript_repair import build_transcript_repair, prepare_transcript_for_query


def test_transcript_repair_handles_stt_day_word_with_onecha() -> None:
    result = build_transcript_repair("다이어트 식단표 에서 구 1차 점심 메뉴 알려줘")

    assert result.raw_text == "다이어트 식단표 에서 구 1차 점심 메뉴 알려줘"
    assert result.repaired_text == "다이어트 식단표 에서 9일차 점심 메뉴 알려줘"
    assert result.display_text == "다이어트 식단표 에서 9일차 점심 메뉴 알려줘"
    assert result.final_query == "다이어트 식단표 에서 9일차 점심 메뉴 알려줘"


def test_transcript_repair_handles_spaced_digit_day_expression() -> None:
    result = build_transcript_repair("다이어트 식단 메뉴에서 11일 차 아침 메뉴 알려 주세요")

    assert result.repaired_text == "다이어트 식단표에서 11일차 아침 메뉴 알려 주세요"
    assert result.display_text == "다이어트 식단표에서 11일차 아침 메뉴 알려 주세요"


def test_transcript_repair_strips_greeting_only_in_display_stage() -> None:
    result = build_transcript_repair("안녕하세요 다이어트 식단표 중에 삼 일차 저녁 메뉴 알려 주세요")

    assert result.repaired_text == "안녕하세요 다이어트 식단표 중에 3일차 저녁 메뉴 알려 주세요"
    assert result.display_text == "다이어트 식단표 중에 3일차 저녁 메뉴 알려 주세요"


def test_prepare_transcript_for_query_strips_identifier_tail_noise() -> None:
    result = prepare_transcript_for_query(
        "다이어트 식단표에서 3일차 저녁 메뉴 알려줘요 min_debate_rounds opinion_id DebateRound"
    )

    assert result == "다이어트 식단표에서 3일차 저녁 메뉴 알려줘요"


def test_transcript_repair_canonicalizes_diet_table_alias_and_spoken_day_slot() -> None:
    result = build_transcript_repair("다이어트 메뉴 표 에서 육 일자 점심 메뉴 알려 주세요")

    assert result.repaired_text == "다이어트 식단표 에서 6일차 점심 메뉴 알려 주세요"
    assert result.display_text == "다이어트 식단표 에서 6일차 점심 메뉴 알려 주세요"


def test_transcript_repair_canonicalizes_diet_round_slot_expression() -> None:
    result = build_transcript_repair("안녕하세요 다이어트 식단표 에서 9일 회차 아침 메뉴 알려 주세요")

    assert result.repaired_text == "안녕하세요 다이어트 식단표 에서 9일차 아침 메뉴 알려 주세요"
    assert result.display_text == "다이어트 식단표 에서 9일차 아침 메뉴 알려 주세요"


def test_transcript_repair_handles_prefixed_il_noise_before_day_slot() -> None:
    result = build_transcript_repair("다이어트 식단표 에서 일 1일 아침 메뉴 알려줘")

    assert result.repaired_text == "다이어트 식단표 에서 1일차 아침 메뉴 알려줘"
    assert result.display_text == "다이어트 식단표 에서 1일차 아침 메뉴 알려줘"


def test_transcript_repair_canonicalizes_wake_phrase_variants() -> None:
    result = build_transcript_repair("이 자비스")

    assert result.repaired_text == "헤이 자비스"
    assert result.display_text == "헤이 자비스"
    assert result.final_query == "헤이 자비스"


def test_prepare_transcript_for_query_strips_explicit_wake_phrase_prefix() -> None:
    result = prepare_transcript_for_query("헤이 자비스 오늘 일정 알려줘")

    assert result == "오늘 일정 알려줘"


def test_prepare_transcript_for_query_preserves_plain_jarvis_subject_query() -> None:
    result = prepare_transcript_for_query("자비스 구조 설명해줘")

    assert result == "자비스 구조 설명해줘"
