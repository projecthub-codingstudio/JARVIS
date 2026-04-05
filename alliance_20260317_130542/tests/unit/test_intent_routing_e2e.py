"""End-to-end tests for intent-based response routing."""

from __future__ import annotations

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest


def _request(text: str) -> RpcRequest:
    return RpcRequest(
        request_id="req-1",
        session_id="session-1",
        request_type="ask_text",
        payload={"text": text},
    )


def test_youtube_open_returns_action_response(monkeypatch) -> None:
    """'YouTube 열어줘' should execute open command, not return HWP content."""
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    open_calls = []

    def mock_subprocess_run(*args, **kwargs):
        open_calls.append(args[0] if args else kwargs.get("args"))

    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        mock_subprocess_run,
    )

    response = service.handle(_request("YouTube 열어줘"))

    assert response.ok is True
    assert "열었습니다" in response.payload["response"]["response"]
    action_calls = [c for c in open_calls if c and c[0] == "open"]
    assert len(action_calls) == 1
    assert "youtube.com" in action_calls[0][1]


def test_kakaotalk_open_returns_action_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    open_calls = []

    def mock_subprocess_run(*args, **kwargs):
        open_calls.append(args[0] if args else kwargs.get("args"))

    monkeypatch.setattr(
        "jarvis.core.action_resolver.subprocess.run",
        mock_subprocess_run,
    )

    response = service.handle(_request("카톡 켜줘"))

    assert response.ok is True
    assert "실행했습니다" in response.payload["response"]["response"]
    action_calls = [c for c in open_calls if c and c[0] == "open"]
    assert len(action_calls) == 1
    assert action_calls[0] == ["open", "-a", "KakaoTalk"]


def test_qa_query_still_uses_rag(monkeypatch) -> None:
    """Non-action queries should still go through RAG pipeline."""
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )

    bridge_called = []

    def fake_bridge(**kwargs):
        bridge_called.append(True)
        return {
            "kind": "query_result",
            "query_result": {
                "response": "서울 인구는 약 950만명입니다.",
                "citations": [],
                "render_hints": {},
            },
        }

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        fake_bridge,
    )

    response = service.handle(_request("서울 인구 알려줘"))

    assert response.ok is True
    assert len(bridge_called) == 1


def test_builtin_time_still_works(monkeypatch) -> None:
    """Builtin capabilities should still take priority over action routing."""
    from datetime import datetime, timezone

    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda payload: None,
    )
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("should not reach menu bridge")
        ),
    )

    def fake_now(zone_name: str) -> datetime:
        return datetime(2026, 3, 30, 10, 45, tzinfo=timezone.utc)

    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        fake_now,
    )

    response = service.handle(_request("지금 몇시야"))

    assert response.ok is True
    assert "시간" in response.payload["response"]["response"]
