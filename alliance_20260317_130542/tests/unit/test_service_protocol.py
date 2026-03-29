"""Tests for the transport-agnostic JARVIS service protocol."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from jarvis.service.application import (
    JarvisApplicationService,
    _menu_bridge_timeout_seconds,
    _reset_runtime_context_cache_for_tests,
)
from jarvis.service.protocol import RpcRequest, error_response, ok_response


@pytest.fixture(autouse=True)
def reset_runtime_context_cache() -> None:
    _reset_runtime_context_cache_for_tests()
    yield
    _reset_runtime_context_cache_for_tests()


def test_rpc_request_roundtrip() -> None:
    request = RpcRequest(
        request_id="req-1",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "안녕하세요"},
    )

    restored = RpcRequest.from_json(request.to_json())

    assert restored == request


def test_ok_response_marks_success() -> None:
    request = RpcRequest(
        request_id="req-1",
        session_id="sess-1",
        request_type="health",
    )

    response = ok_response(request=request, payload={"healthy": True})

    assert response.ok is True
    assert response.error is None
    assert response.payload["healthy"] is True


def test_error_response_marks_failure() -> None:
    request = RpcRequest(
        request_id="req-1",
        session_id="sess-1",
        request_type="unknown",
    )

    response = error_response(
        request=request,
        code="UNKNOWN_REQUEST_TYPE",
        message="unsupported",
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "UNKNOWN_REQUEST_TYPE"


def test_application_service_rejects_unknown_request_type() -> None:
    service = JarvisApplicationService()
    request = RpcRequest(
        request_id="req-1",
        session_id="sess-1",
        request_type="does_not_exist",
    )

    response = service.handle(request)

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "UNKNOWN_REQUEST_TYPE"


def test_application_service_handles_runtime_state(monkeypatch) -> None:
    service = JarvisApplicationService()
    monkeypatch.setattr(
        "jarvis.service.application._health_light",
        lambda: {
            "healthy": True,
            "message": "ok",
            "checks": {"knowledge_base": True},
            "details": {"mode": "local"},
            "failed_checks": [],
            "status_level": "ok",
            "chunk_count": 12,
            "knowledge_base_path": "/tmp/kb",
            "bridge_mode": "service",
        },
    )

    request = RpcRequest(
        request_id="req-runtime",
        session_id="sess-1",
        request_type="runtime_state",
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["health"]["healthy"] is True
    assert response.payload["service"]["runtime_owner"] == "backend-service"


def test_application_service_repairs_transcript(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application.build_transcript_repair",
        lambda text: type(
            "RepairResult",
            (),
            {
                "raw_text": text,
                "repaired_text": "다이어트 식단표 에서 9일차 점심 메뉴 알려줘",
                "display_text": "다이어트 식단표 에서 9일차 점심 메뉴 알려줘",
                "final_query": "다이어트 식단표 에서 9일차 점심 메뉴 알려줘",
            },
        )(),
    )

    request = RpcRequest(
        request_id="req-repair",
        session_id="sess-1",
        request_type="repair_transcript",
        payload={"text": "다이어트 식단표 에서 구 1차 점심 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["transcript_repair"]["raw_text"] == "다이어트 식단표 에서 구 1차 점심 메뉴 알려줘"
    assert response.payload["transcript_repair"]["repaired_text"] == "다이어트 식단표 에서 9일차 점심 메뉴 알려줘"


def test_application_service_prefetches_query_tts(monkeypatch) -> None:
    service = JarvisApplicationService()
    prefetched: list[str] = []

    class ImmediateThread:
        def __init__(self, *, target, args=(), kwargs=None, daemon=None, name=None):  # type: ignore[no-untyped-def]
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self) -> None:
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(
        "jarvis.service.application.predict_prefetchable_spoken_response",
        lambda query: "9일차 아침은 구운계란 두 개와 요거트와 베리입니다.",
    )
    monkeypatch.setattr("jarvis.service.application._tts_backend", lambda: "qwen3")
    monkeypatch.setattr("jarvis.service.application._prefetch_tts_cache", prefetched.append)
    monkeypatch.setattr("jarvis.service.application.threading.Thread", ImmediateThread)

    request = RpcRequest(
        request_id="req-prefetch",
        session_id="sess-1",
        request_type="prefetch_query_tts",
        payload={"text": "다이어트 식단표 에서 9일 회차 아침 메뉴 알려 주세요"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["tts_prefetch"]["started"] is True
    assert prefetched == ["9일차 아침은 구운계란 두 개와 요거트와 베리입니다."]


def test_application_service_skips_query_tts_prefetch_without_prediction(monkeypatch) -> None:
    service = JarvisApplicationService()
    monkeypatch.setattr("jarvis.service.application._tts_backend", lambda: "qwen3")
    monkeypatch.setattr(
        "jarvis.service.application.predict_prefetchable_spoken_response",
        lambda query: "",
    )

    request = RpcRequest(
        request_id="req-prefetch-empty",
        session_id="sess-1",
        request_type="prefetch_query_tts",
        payload={"text": "pipeline.py 구조 설명해줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["tts_prefetch"]["started"] is False


def test_application_service_prefetches_query_tts_by_segment(monkeypatch) -> None:
    service = JarvisApplicationService()
    prefetched: list[str] = []

    class ImmediateThread:
        def __init__(self, *, target, args=(), kwargs=None, daemon=None, name=None):  # type: ignore[no-untyped-def]
            self._target = target
            self._args = args
            self._kwargs = kwargs or {}

        def start(self) -> None:
            self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(
        "jarvis.service.application.predict_prefetchable_spoken_response",
        lambda query: "1일차 점심은 닭가슴살입니다. / 2일차 저녁은 두부입니다.",
    )
    monkeypatch.setattr("jarvis.service.application._tts_backend", lambda: "qwen3")
    monkeypatch.setattr("jarvis.service.application._prefetch_tts_cache", prefetched.append)
    monkeypatch.setattr("jarvis.service.application.threading.Thread", ImmediateThread)

    request = RpcRequest(
        request_id="req-prefetch-segments",
        session_id="sess-1",
        request_type="prefetch_query_tts",
        payload={"text": "다이어트 식단표 에서 1일차 점심 2일차 저녁 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["tts_prefetch"]["started"] is True
    assert prefetched == [
        "1일차 점심은 닭가슴살입니다.",
        "2일차 저녁은 두부입니다.",
    ]


def test_application_service_skips_query_tts_prefetch_when_backend_is_say(monkeypatch) -> None:
    service = JarvisApplicationService()
    monkeypatch.setattr("jarvis.service.application._tts_backend", lambda: "say")
    monkeypatch.setattr(
        "jarvis.service.application.predict_prefetchable_spoken_response",
        lambda query: "1일차 아침은 구운계란 두 개와 방울토마토입니다.",
    )

    request = RpcRequest(
        request_id="req-prefetch-say",
        session_id="sess-1",
        request_type="prefetch_query_tts",
        payload={"text": "다이어트 식단표 에서 1일차 아침 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["tts_prefetch"]["started"] is False
    assert response.payload["tts_prefetch"]["predicted_text"] == ""


def test_application_service_ask_text_returns_guide_contract(monkeypatch) -> None:
    service = JarvisApplicationService()
    observed_args: list[str] = []

    @dataclass(frozen=True)
    class FakeResponse:
        query: str
        response: str
        has_evidence: bool
        citations: list[dict[str, object]]
        status: dict[str, object] | None
        render_hints: dict[str, object] | None
        exploration: dict[str, object] | None
        guide_directive: dict[str, object] | None
        full_response_path: str | None

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda query: observed_args.extend(["--query", query, "--model", "qwen3.5:9b"]) or {
            "kind": "query_result",
            "query_result": {
                "query": query,
                "response": "출발 위치를 알려주세요.",
                "spoken_response": "출발 위치를 알려주세요.",
                "has_evidence": True,
                "citations": [{"label": "1"}],
                "status": None,
                "render_hints": {"interaction_mode": "route"},
                "exploration": {
                    "mode": "document",
                    "target_file": "guide.md",
                    "target_document": "guide",
                },
                "guide_directive": {
                    "loop_stage": "waiting_user_reply",
                    "clarification_prompt": "출발 위치를 알려주세요.",
                    "suggested_replies": ["현재 위치", "집"],
                    "missing_slots": ["origin"],
                    "intent": "route_guidance",
                    "skill": "route",
                    "should_hold": True,
                },
                "full_response_path": "/tmp/response.md",
            },
        },
    )

    request = RpcRequest(
        request_id="req-ask",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "길 안내해줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["answer"]["text"] == "출발 위치를 알려주세요."
    assert response.payload["answer"]["spoken_text"] == "출발 위치를 알려주세요."
    assert response.payload["guide"]["loop_stage"] == "waiting_user_reply"
    assert response.payload["guide"]["missing_slots"] == ["origin"]
    assert response.payload["guide"]["clarification_reasons"] == ["origin"]
    assert response.payload["guide"]["clarification_options"] == ["현재 위치", "집"]
    assert response.payload["guide"]["target_file"] == "guide.md"
    assert observed_args[-1] == "qwen3.5:9b"


def test_application_service_infers_guide_prompt_from_answer(monkeypatch) -> None:
    service = JarvisApplicationService()

    @dataclass(frozen=True)
    class FakeResponse:
        query: str
        response: str
        has_evidence: bool
        citations: list[dict[str, object]]
        status: dict[str, object] | None
        render_hints: dict[str, object] | None
        exploration: dict[str, object] | None
        guide_directive: dict[str, object] | None
        full_response_path: str | None

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda query: {
            "kind": "query_result",
            "query_result": {
                "query": query,
                "response": "어느 파일을 기준으로 설명할까요?",
                "spoken_response": "어느 파일을 기준으로 설명할까요?",
                "has_evidence": False,
                "citations": [],
                "status": None,
                "render_hints": {"interaction_mode": "source"},
                "exploration": {
                    "mode": "source",
                    "target_file": "",
                    "target_document": "",
                    "file_candidates": [{"label": "app.py"}],
                    "document_candidates": [],
                    "class_candidates": [],
                    "function_candidates": [],
                },
                "guide_directive": None,
                "full_response_path": None,
            },
        },
    )

    request = RpcRequest(
        request_id="req-ask-infer",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "설명해줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["guide"]["loop_stage"] == "waiting_user_reply"
    assert response.payload["guide"]["clarification_prompt"] == "어느 파일을 기준으로 설명할까요?"
    assert response.payload["guide"]["clarification_options"] == ["app.py"]


def test_application_service_ask_text_falls_back_to_stub_model(monkeypatch) -> None:
    service = JarvisApplicationService()
    observed_models: list[str] = []
    monkeypatch.setenv("JARVIS_MENU_BAR_MODEL_CHAIN", "qwen3.5:9b,stub")
    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda response_payload: None)

    def fake_run(*, query: str, model_id: str) -> dict[str, object]:
        model = model_id
        observed_models.append(model)
        if model == "qwen3.5:9b":
            raise RuntimeError("primary model failed")
        return {
            "kind": "query_result",
            "query_result": {
                "query": query,
                "response": "9일차 저녁은 순두부와 방울토마토입니다.",
                "spoken_response": "9일차 저녁은 순두부와 방울토마토입니다.",
                "has_evidence": True,
                "citations": [],
                "status": None,
                "render_hints": {"interaction_mode": "document_exploration"},
                "exploration": None,
                "guide_directive": None,
                "full_response_path": None,
            },
        }

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_query_in_process",
        fake_run,
    )

    request = RpcRequest(
        request_id="req-ask-fallback",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "다이어트 식단표에서 9일차 저녁 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert observed_models == ["qwen3.5:9b", "stub"]
    assert response.payload["answer"]["text"] == "9일차 저녁은 순두부와 방울토마토입니다."


def test_application_service_ask_text_retries_when_primary_returns_degraded(monkeypatch) -> None:
    service = JarvisApplicationService()
    observed_models: list[str] = []
    monkeypatch.setenv("JARVIS_MENU_BAR_MODEL_CHAIN", "qwen3.5:9b,stub")
    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda response_payload: None)

    def fake_run(*, query: str, model_id: str) -> dict[str, object]:
        model = model_id
        observed_models.append(model)
        if model == "qwen3.5:9b":
            return {
                "kind": "query_result",
                "query_result": {
                    "query": query,
                    "response": "현재 시스템이 degraded 상태입니다. 생성 기능을 일시 제한하고 검색 결과만 제공합니다.",
                    "spoken_response": "현재 시스템이 degraded 상태입니다.",
                    "has_evidence": True,
                    "citations": [],
                    "status": {
                        "mode": "normal",
                        "safe_mode": False,
                        "degraded_mode": True,
                        "generation_blocked": False,
                        "write_blocked": False,
                        "rebuild_index_required": False,
                    },
                    "render_hints": {"interaction_mode": "document_exploration"},
                    "exploration": None,
                    "guide_directive": None,
                    "full_response_path": None,
                },
            }
        return {
            "kind": "query_result",
            "query_result": {
                "query": query,
                "response": "9일차 저녁은 순두부와 김과 피망입니다. [1]",
                "spoken_response": "9일차 저녁은 순두부와 김과 피망입니다.",
                "has_evidence": True,
                "citations": [],
                "status": {
                    "mode": "normal",
                    "safe_mode": False,
                    "degraded_mode": False,
                    "generation_blocked": False,
                    "write_blocked": False,
                    "rebuild_index_required": False,
                },
                "render_hints": {"interaction_mode": "document_exploration"},
                "exploration": None,
                "guide_directive": None,
                "full_response_path": None,
            },
        }

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_query_in_process",
        fake_run,
    )

    request = RpcRequest(
        request_id="req-ask-degraded-fallback",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "다이어트 식단표에서 9일차 저녁 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert observed_models == ["qwen3.5:9b", "stub"]
    assert response.payload["answer"]["text"] == "9일차 저녁은 순두부와 김과 피망입니다."
    assert response.payload["response"]["status"]["degraded_mode"] is False


def test_application_service_primes_tts_cache_from_spoken_response(monkeypatch) -> None:
    service = JarvisApplicationService()
    observed: list[str] = []

    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda query: {
            "kind": "query_result",
            "query_result": {
                "query": query,
                "response": "3일차 저녁은 순두부와 방울토마토입니다. [1]",
                "spoken_response": "3일차 저녁은 순두부와 방울토마토입니다.",
                "has_evidence": True,
                "citations": [],
                "status": {
                    "mode": "normal",
                    "safe_mode": False,
                    "degraded_mode": False,
                    "generation_blocked": False,
                    "write_blocked": False,
                    "rebuild_index_required": False,
                },
                "render_hints": {"interaction_mode": "document_exploration"},
                "exploration": None,
                "guide_directive": None,
                "full_response_path": None,
            },
        },
    )
    monkeypatch.setattr(
        "jarvis.service.application._prime_tts_cache_async",
        lambda response_payload: observed.append(str(response_payload.get("spoken_response", ""))),
    )

    request = RpcRequest(
        request_id="req-ask-prefetch",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "다이어트 식단표에서 3일차 저녁 메뉴 알려줘"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert observed == ["3일차 저녁은 순두부와 방울토마토입니다."]


def test_application_service_ask_text_reuses_cached_runtime_context(monkeypatch) -> None:
    service = JarvisApplicationService()
    observed_contexts: list[object] = []
    build_calls: list[str] = []

    @dataclass(frozen=True)
    class FakeResponse:
        query: str
        response: str
        spoken_response: str
        has_evidence: bool
        citations: list[dict[str, object]]
        status: dict[str, object] | None
        render_hints: dict[str, object] | None
        exploration: dict[str, object] | None
        guide_directive: dict[str, object] | None
        full_response_path: str | None

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda response_payload: None)

    def fake_build_context(*, model_id: str) -> object:
        build_calls.append(model_id)
        return object()

    def fake_run_query_in_context(*, query: str, model_id: str, context: object) -> FakeResponse:
        observed_contexts.append(context)
        return FakeResponse(
            query=query,
            response="4일차 저녁은 두부조림과 브로콜리입니다.",
            spoken_response="4일차 저녁은 두부조림과 브로콜리입니다.",
            has_evidence=True,
            citations=[],
            status=None,
            render_hints={"interaction_mode": "document_exploration"},
            exploration=None,
            guide_directive=None,
            full_response_path=None,
        )

    monkeypatch.setattr("jarvis.service.application._build_context", fake_build_context)
    monkeypatch.setattr("jarvis.service.application._run_query_in_context", fake_run_query_in_context)

    request = RpcRequest(
        request_id="req-ask-cache-1",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "다이어트 식단표에서 4일차 저녁 메뉴 알려줘"},
    )
    response = service.handle(request)
    assert response.ok is True

    request = RpcRequest(
        request_id="req-ask-cache-2",
        session_id="sess-1",
        request_type="ask_text",
        payload={"text": "다이어트 식단표에서 4일차 저녁 메뉴 다시 알려줘"},
    )
    response = service.handle(request)
    assert response.ok is True

    assert build_calls == ["stub"]
    assert len(observed_contexts) == 2
    assert observed_contexts[0] is observed_contexts[1]


def test_menu_bridge_timeout_prefers_longer_budget_for_model_backed_ask(monkeypatch) -> None:
    monkeypatch.delenv("JARVIS_MENU_BRIDGE_TIMEOUT_SECONDS", raising=False)

    assert _menu_bridge_timeout_seconds("ask", model_id="qwen3.5:9b") == 50
    assert _menu_bridge_timeout_seconds("ask", model_id="stub") == 18


def test_application_service_handles_synthesize_speech(monkeypatch, tmp_path: Path) -> None:
    service = JarvisApplicationService()

    @dataclass(frozen=True)
    class FakeSpeech:
        audio_path: str
    monkeypatch.setattr(
        "jarvis.service.application._synthesize_speech",
        lambda text: FakeSpeech(audio_path=str(tmp_path / "speech.aiff")),
    )

    request = RpcRequest(
        request_id="req-tts",
        session_id="sess-1",
        request_type="synthesize_speech",
        payload={"text": "안녕하세요"},
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["speech"]["audio_path"].endswith("speech.aiff")


def test_application_service_handles_tts_warmup(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr(
        "jarvis.service.application._start_background_tts_warmup",
        lambda: {"started": True, "running": True, "warmed": False},
    )

    request = RpcRequest(
        request_id="req-warmup-tts",
        session_id="sess-1",
        request_type="warmup_tts",
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["tts"]["started"] is True
    assert response.payload["tts"]["running"] is True
    assert response.payload["tts"]["warmed"] is False


def test_application_service_handles_export_draft(monkeypatch, tmp_path: Path) -> None:
    service = JarvisApplicationService()

    @dataclass(frozen=True)
    class FakeExport:
        destination: str
        approved: bool
        success: bool
        error_message: str

    monkeypatch.setattr(
        "jarvis.service.application._export_draft",
        lambda content, destination, approved: FakeExport(
            destination=str(tmp_path / "draft.txt"),
            approved=True,
            success=True,
            error_message="",
        ),
    )

    request = RpcRequest(
        request_id="req-export",
        session_id="sess-1",
        request_type="export_draft",
        payload={
            "content": "body",
            "destination": str(tmp_path / "draft.txt"),
            "approved": True,
        },
    )

    response = service.handle(request)

    assert response.ok is True
    assert response.payload["export"]["success"] is True
