"""Tests for built-in capability routing in the application service."""

from __future__ import annotations

from datetime import datetime, timezone

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest


def _request(text: str) -> RpcRequest:
    return RpcRequest(
        request_id="req-1",
        session_id="session-1",
        request_type="ask_text",
        payload={"text": text},
    )


def test_ask_text_uses_builtin_time_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 3, 30, 10, 45, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)

    response = service.handle(_request("서울 시간 알려줘"))

    assert response.ok is True
    assert response.payload["response"]["response"].startswith("서울 기준 현재 시간은")
    assert response.payload["guide"]["presentation"]["title"] == "Time Workspace"
    assert response.payload["guide"]["artifacts"][0]["title"] == "서울"


def test_ask_text_uses_builtin_weather_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._fetch_weather",
        lambda location: (
            {
                "current_condition": [
                    {
                        "temp_C": "18",
                        "FeelsLikeC": "16",
                        "humidity": "55",
                        "windspeedKmph": "10",
                        "weatherDesc": [{"value": "맑음"}],
                    }
                ],
                "nearest_area": [{"areaName": [{"value": "서울"}]}],
                "weather": [
                    {
                        "date": "2026-03-30",
                        "maxtempC": "20",
                        "mintempC": "12",
                        "avgtempC": "17",
                        "daily_chance_of_rain": "5",
                        "hourly": [{}, {}, {}, {}, {"weatherDesc": [{"value": "맑음"}]}],
                    }
                ],
            },
            "https://wttr.in/Seoul?format=j1&lang=ko",
        ),
    )

    response = service.handle(_request("서울 날씨 알려줘"))

    assert response.ok is True
    assert "서울 현재 날씨는 맑음" in response.payload["response"]["response"]
    assert response.payload["guide"]["presentation"]["title"] == "Weather Workspace"
    assert response.payload["guide"]["artifacts"][0]["title"] == "서울 현재 날씨"


def test_ask_text_uses_builtin_web_search_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._search_web",
        lambda query: [
            {
                "title": "OpenAI",
                "url": "https://openai.com/",
                "domain": "openai.com",
                "snippet": "OpenAI official website",
            },
            {
                "title": "OpenAI API",
                "url": "https://platform.openai.com/",
                "domain": "platform.openai.com",
                "snippet": "API platform",
            },
        ],
    )

    response = service.handle(_request("OpenAI 사이트 찾아줘"))

    assert response.ok is True
    assert "웹 결과 2개" in response.payload["response"]["response"]
    assert response.payload["guide"]["presentation"]["layout"] == "master_detail"
    assert response.payload["guide"]["artifacts"][0]["type"] == "web"


def test_ask_text_uses_builtin_calculation_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    response = service.handle(_request("12 / 4 계산"))

    assert response.ok is True
    assert response.payload["response"]["response"] == "12/4의 결과는 3입니다."
    assert response.payload["guide"]["presentation"]["title"] == "Calculation Workspace"
    assert response.payload["guide"]["artifacts"][0]["preview"] == "식: 12/4\n결과: 3"


def test_ask_text_uses_builtin_direct_url_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    response = service.handle(_request("https://example.com"))

    assert response.ok is True
    assert "example.com" in response.payload["response"]["response"]
    assert response.payload["guide"]["artifacts"][0]["type"] == "web"
    assert response.payload["guide"]["artifacts"][0]["path"] == "https://example.com"


def test_builtin_calculator_rejects_unsafe_expressions(monkeypatch) -> None:
    """Ensure expressions with import/call attempts fall through to LLM."""
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)

    llm_called = []

    def fake_bridge(**kwargs):
        llm_called.append(True)
        return {
            "kind": "query_result",
            "query_result": {
                "response": "안전하지 않은 입력입니다.",
                "citations": [],
                "render_hints": {},
            },
        }

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        fake_bridge,
    )

    response = service.handle(_request("import os 계산"))

    assert response.ok is True
    assert len(llm_called) == 1  # fell through to LLM
