"""Tests for frontend intent policy dispatch."""

from __future__ import annotations

from jarvis.core.intent_policy import resolve_menu_intent_policy


def test_resolves_smalltalk_policy() -> None:
    resolution = resolve_menu_intent_policy("안녕하세요")

    assert resolution.analysis.intent == "smalltalk"
    assert resolution.policy is not None
    assert resolution.policy.intent == "smalltalk"
    assert "무엇을 도와드릴까요" in resolution.policy.response_text


def test_resolves_weather_policy() -> None:
    resolution = resolve_menu_intent_policy("오늘 날씨좀 알려주세요")

    assert resolution.analysis.intent == "weather"
    assert resolution.policy is not None
    assert resolution.policy.intent == "weather"
    assert "실시간 날씨 데이터" in resolution.policy.response_text


def test_returns_no_override_for_document_qa() -> None:
    resolution = resolve_menu_intent_policy("다이어트 식단표에서 3일차 점심을 알려줘")

    assert resolution.analysis.intent == "qa"
    assert resolution.policy is None
