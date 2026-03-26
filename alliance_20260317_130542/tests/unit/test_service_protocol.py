"""Tests for the transport-agnostic JARVIS service protocol."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis.service.application import JarvisApplicationService
from jarvis.service.protocol import RpcRequest, error_response, ok_response


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

    def fake_run(*, command: str, args: list[str]) -> dict[str, object]:
        model = args[-1]
        observed_models.append(model)
        if model == "qwen3.5:9b":
            raise RuntimeError("primary model failed")
        return {
            "kind": "query_result",
            "query_result": {
                "query": args[1],
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
        "jarvis.service.application._run_menu_bridge_subprocess",
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
    assert observed_models == ["stub"]
    assert response.payload["answer"]["text"] == "9일차 저녁은 순두부와 방울토마토입니다."


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
