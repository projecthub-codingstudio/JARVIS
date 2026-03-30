"""Tests for action intent classification in the planner."""

from __future__ import annotations

from jarvis.core.planner import _classify_intent


def test_classify_youtube_open_as_action():
    result = _classify_intent(
        "YouTube 열어줘",
        tokens=["youtube", "열어줘"],
        target_file="",
    )
    assert result == "action"


def test_classify_kakaotalk_as_action():
    result = _classify_intent(
        "카톡 켜줘",
        tokens=["카톡", "켜줘"],
        target_file="",
    )
    assert result == "action"


def test_classify_english_open_as_action():
    result = _classify_intent(
        "open safari",
        tokens=["open", "safari"],
        target_file="",
    )
    assert result == "action"


def test_classify_qa_unchanged():
    result = _classify_intent(
        "서울 인구 알려줘",
        tokens=["서울", "인구", "알려줘"],
        target_file="",
    )
    assert result == "qa"


def test_classify_smalltalk_unchanged():
    result = _classify_intent(
        "안녕하세요",
        tokens=["안녕하세요"],
        target_file="",
    )
    assert result == "smalltalk"


def test_classify_weather_unchanged():
    result = _classify_intent(
        "서울 날씨 어때",
        tokens=["서울", "날씨", "어때"],
        target_file="",
    )
    assert result == "weather"
