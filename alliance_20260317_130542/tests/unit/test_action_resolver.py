"""Tests for ActionResolver — target parsing and macOS open execution."""

from __future__ import annotations

from jarvis.core.action_resolver import parse_action_target, execute_action, ActionTarget


def test_parse_youtube_open():
    target = parse_action_target("YouTube 열어줘")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://youtube.com"
    assert target.label == "YouTube"


def test_parse_kakaotalk_open():
    target = parse_action_target("카톡 켜줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "KakaoTalk"
    assert target.label == "카카오톡"


def test_parse_unknown_app():
    target = parse_action_target("모르는앱 열어줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "모르는앱"
    assert target.label == "모르는앱"
    assert target.confidence == "low"


def test_parse_no_action_verb():
    target = parse_action_target("서울 인구 알려줘")
    assert target is None


def test_parse_naver_open():
    target = parse_action_target("네이버 열어")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://naver.com"


def test_parse_english_open():
    target = parse_action_target("open github")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://github.com"


def test_parse_settings_open():
    target = parse_action_target("설정 열어줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "System Preferences"


def test_does_not_match_single_letter_x_inside_other_words():
    target = parse_action_target("text 다시 열어줘")
    assert target is not None
    assert target.action_type == "open_app"
    assert target.target == "text 다시"
    assert target.confidence == "low"


def test_parse_single_letter_x_exact_match():
    target = parse_action_target("x 열어줘")
    assert target is not None
    assert target.action_type == "open_url"
    assert target.target == "https://x.com"
    assert target.label == "X"


def test_execute_url_success(monkeypatch):
    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        lambda *args, **kwargs: None,
    )
    target = ActionTarget(
        action_type="open_url",
        target="https://youtube.com",
        label="YouTube",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is True
    assert "YouTube" in result.spoken_response
    assert "열었습니다" in result.spoken_response


def test_execute_app_success(monkeypatch):
    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        lambda *args, **kwargs: None,
    )
    target = ActionTarget(
        action_type="open_app",
        target="KakaoTalk",
        label="카카오톡",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is True
    assert "카카오톡" in result.spoken_response
    assert "실행했습니다" in result.spoken_response


def test_execute_app_not_found(monkeypatch):
    import subprocess as sp

    def fail_run(*args, **kwargs):
        raise sp.CalledProcessError(1, "open")

    monkeypatch.setattr("jarvis.core.action_resolver.subprocess.run", fail_run)
    target = ActionTarget(
        action_type="open_app",
        target="NonExistentApp",
        label="NonExistentApp",
        confidence="low",
    )
    result = execute_action(target)
    assert result.success is False
    assert "찾을 수 없습니다" in result.spoken_response


def test_execute_timeout(monkeypatch):
    import subprocess as sp

    def timeout_run(*args, **kwargs):
        raise sp.TimeoutExpired("open", 5)

    monkeypatch.setattr("jarvis.core.action_resolver.subprocess.run", timeout_run)
    target = ActionTarget(
        action_type="open_url",
        target="https://example.com",
        label="example",
        confidence="high",
    )
    result = execute_action(target)
    assert result.success is False
    assert "시간이 초과" in result.spoken_response
