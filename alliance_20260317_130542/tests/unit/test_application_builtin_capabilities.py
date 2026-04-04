"""Tests for built-in capability routing in the application service."""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import count

from jarvis.cli.menu_bridge import MenuBarExplorationItem, MenuBarExplorationState
from jarvis.core.action_resolver import ActionResult
from jarvis.contracts import DocumentElement
from jarvis.service.application import (
    JarvisApplicationService,
    _contains_japanese_kana,
    _create_local_calendar_event,
    _extract_topic_document_highlight,
    _normalize_topic_summary_language,
    _primary_topic_summary_query,
    _topic_summary_model_candidates,
)
from jarvis.service.intent_skill_store import create_action_map, create_skill_profile, list_skill_backlog
from jarvis.service.protocol import RpcRequest

_SESSION_COUNTER = count(1)


def _request(text: str, *, session_id: str | None = None) -> RpcRequest:
    resolved_session_id = session_id or f"session-{next(_SESSION_COUNTER)}"
    return RpcRequest(
        request_id="req-1",
        session_id=resolved_session_id,
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
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "timezone_now"
    assert len(response.payload["answer"]["structured_payload"]["clocks"]) == 1
    assert response.payload["guide"]["artifacts"] == []
    assert response.payload["guide"]["presentation"] is None
    assert response.payload["guide"]["ui_hints"]["show_documents"] is False


def test_extract_topic_document_highlight_prefers_code_comments() -> None:
    document = {
        "format": "swift",
        "text": (
            "//\n"
            "//  ProjectHubApp.swift\n"
            "//  ProjectHub\n"
            "//\n"
            "//  Project management and version control Mac app\n"
            "//\n"
            "import SwiftUI\n"
        ),
        "elements": [],
    }

    highlight = _extract_topic_document_highlight(document)

    assert "Project management and version control Mac app" in highlight


def test_primary_topic_summary_query_strips_generic_descriptor() -> None:
    assert _primary_topic_summary_query("JARVIS의 기술 사양") == "JARVIS"
    assert _primary_topic_summary_query("ProjectHub architecture") == "ProjectHub"


def test_topic_summary_model_candidates_include_fallback_models(monkeypatch) -> None:
    monkeypatch.setattr(
        "jarvis.service.application._menu_bar_model_chain",
        lambda: ("qwen3.5:9b", "stub"),
    )

    candidates = _topic_summary_model_candidates()

    assert candidates[0] == "qwen3.5:9b"
    assert "qwen3:14b" in candidates


def test_normalize_topic_summary_language_rewrites_japanese_terms() -> None:
    text = "사용자에게 더욱 스ムーズ하고 안정적인 개발 환경을 제공합니다."

    normalized = _normalize_topic_summary_language(text)

    assert "원활한" in normalized
    assert _contains_japanese_kana(normalized) is False


def test_ask_text_uses_builtin_relative_date_offset_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)

    response = service.handle(_request("오늘부터 20일 후면 며칠이야?"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "relative_date"
    assert response.payload["answer"]["structured_payload"]["offset_days"] == 20
    assert response.payload["answer"]["structured_payload"]["target_date"] == "2026-04-24"
    assert "20일 후는 2026년 4월 24일" in response.payload["response"]["response"]


def test_ask_text_uses_builtin_relative_date_anchor_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)

    response = service.handle(_request("엊그제가 며칠이었지?"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "relative_date"
    assert response.payload["answer"]["structured_payload"]["anchor_label"] == "엊그제"
    assert response.payload["answer"]["structured_payload"]["target_date"] == "2026-04-02"
    assert "엊그제는 2026년 4월 2일" in response.payload["response"]["response"]


def test_ask_text_uses_builtin_relative_date_anchor_only_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)

    response = service.handle(_request("글피는 ?"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "relative_date"
    assert response.payload["answer"]["structured_payload"]["anchor_label"] == "글피"
    assert response.payload["answer"]["structured_payload"]["target_date"] == "2026-04-07"
    assert "글피는 2026년 4월 7일" in response.payload["response"]["response"]


def test_ask_text_uses_relative_date_context_for_calendar_followup(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)

    first_response = service.handle(_request("오늘부터 20일 후면 며칠이야?", session_id="session-relative-calendar"))
    second_response = service.handle(_request("그날 일정을 잡아줘", session_id="session-relative-calendar"))

    assert first_response.ok is True
    assert second_response.ok is True
    assert second_response.payload["answer"]["task_id"] == "calendar_followup"
    assert second_response.payload["answer"]["kind"] == "utility_result"
    assert second_response.payload["answer"]["structured_payload"]["target_date"] == "2026-04-24"
    assert second_response.payload["guide"]["has_clarification"] is True
    assert second_response.payload["guide"]["missing_slots"] == ["title"]
    assert "일정 제목이나 내용을 알려주세요" in second_response.payload["response"]["response"]


def test_ask_text_creates_calendar_event_from_relative_date_query(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    def fake_now(zone_name: str) -> datetime:
        reference = datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc if zone_name == "UTC" else timezone.utc)

    monkeypatch.setattr("jarvis.service.builtin_capabilities._now_in_zone", fake_now)
    monkeypatch.setattr(
        "jarvis.service.application._create_local_calendar_event",
        lambda **kwargs: {
            "calendar_name": "Home",
            "event_title": kwargs.get("title", ""),
        },
    )

    response = service.handle(
        _request("오늘 부터 3일 후에 여의도 국회 의사당에 방문 해야 돼. 일정에 등록해줘.")
    )

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "calendar_create"
    assert response.payload["answer"]["kind"] == "action_result"
    assert response.payload["guide"]["artifacts"] == []
    structured = response.payload["answer"]["structured_payload"]
    assert structured["status"] == "created"
    assert structured["target_date"] == "2026-04-07"
    assert structured["title"] == "여의도 국회 의사당 방문"
    assert structured["location"] == "여의도 국회 의사당"
    assert structured["all_day"] is True
    assert "macOS Calendar에 등록했습니다" in response.payload["response"]["response"]


def test_ask_text_updates_calendar_event_to_absolute_datetime(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    monkeypatch.setattr(
        "jarvis.service.application._update_local_calendar_event",
        lambda **kwargs: {
            "calendar_name": "Home",
            "event_title": "여의도 국회 의사당 방문",
        },
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        lambda zone_name: datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc),
    )

    response = service.handle(
        _request("4월7일 국회의사당 방문을 4월 8일 오후 1:00 로 수정해줘.")
    )

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "calendar_update"
    assert response.payload["answer"]["kind"] == "action_result"
    structured = response.payload["answer"]["structured_payload"]
    assert structured["status"] == "updated"
    assert structured["source_date"] == "2026-04-07"
    assert structured["target_date"] == "2026-04-08"
    assert structured["all_day"] is False
    assert structured["start_label"] == "오후 1:00"
    assert "수정했습니다" in response.payload["response"]["response"]


def test_ask_text_updates_calendar_event_by_relative_day_shift(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    monkeypatch.setattr(
        "jarvis.service.application._update_local_calendar_event",
        lambda **kwargs: {
            "calendar_name": "Home",
            "event_title": "여의도 국회 의사당 방문",
        },
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        lambda zone_name: datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc),
    )

    response = service.handle(
        _request("일정에서 4월7일 국회 의사당 방문을 하루 후로 수정해줘.")
    )

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "calendar_update"
    structured = response.payload["answer"]["structured_payload"]
    assert structured["status"] == "updated"
    assert structured["source_date"] == "2026-04-07"
    assert structured["target_date"] == "2026-04-08"
    assert structured["all_day"] is True


def test_create_local_calendar_event_builds_valid_osascript(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = "Home\t여의도 국회 의사당 방문\n"
        stderr = ""

    def fake_run(args, capture_output, text, timeout, check):  # type: ignore[no-untyped-def]
        captured["args"] = args
        return Completed()

    monkeypatch.setattr("jarvis.service.application.subprocess.run", fake_run)

    result = _create_local_calendar_event(
        title="여의도 국회 의사당 방문",
        start_at=datetime(2026, 4, 7, 0, 0),
        end_at=datetime(2026, 4, 8, 0, 0),
        all_day=True,
        location="여의도 국회 의사당",
        notes="오늘 부터 3일 후에 여의도 국회 의사당에 방문 해야 돼. 일정에 등록해줘.",
    )

    assert result["calendar_name"] == "Home"
    script = str((captured.get("args") or [None, None, ""])[2])
    assert "make new event at end of events with properties" in script
    assert 'set location of newEvent to "여의도 국회 의사당"' in script
    assert 'set allday event of newEvent to true' in script


def test_ask_text_clarifies_calendar_followup_without_date_context(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    response = service.handle(_request("그날 일정을 잡아줘", session_id="session-calendar-clarify"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "calendar_followup"
    assert response.payload["guide"]["has_clarification"] is True
    assert response.payload["guide"]["missing_slots"] == ["target_date"]


def test_ask_text_uses_builtin_runtime_status_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._health_light",
        lambda: {
            "status_level": "healthy",
            "chunk_count": 42,
            "failed_checks": ["vector_search"],
            "details": {"index_failures": 3},
            "bridge_mode": "service",
            "knowledge_base_path": "/tmp/kb",
        },
    )

    response = service.handle(_request("백엔드 상태 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "runtime_status"
    assert response.payload["answer"]["structured_payload"]["chunk_count"] == 42
    assert response.payload["guide"]["ui_hints"]["show_repository"] is False


def test_ask_text_uses_builtin_help_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    response = service.handle(_request("무엇을 할 수 있어?"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "capability_help"
    groups = response.payload["answer"]["structured_payload"]["groups"]
    assert isinstance(groups, list)
    assert response.payload["answer"]["structured_payload"]["registry_version"] == "2026-04-04"
    flat_items = [
        str(item)
        for group in groups
        for item in (group.get("items", []) if isinstance(group, dict) else [])
    ]
    assert any("오늘부터 20일 후면 며칠이야" in item for item in flat_items)
    assert any("오늘 일정 보여줘" in item for item in flat_items)


def test_ask_text_returns_today_calendar_agenda(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._list_local_calendar_events",
        lambda **kwargs: [
            {
                "calendar_name": "Home",
                "title": "여의도 국회 의사당 방문",
                "location": "여의도 국회의사당",
                "start_at": datetime(2026, 4, 4, 13, 0, tzinfo=timezone.utc),
                "end_at": datetime(2026, 4, 4, 14, 0, tzinfo=timezone.utc),
                "all_day": False,
                "start_label": "오후 1:00",
                "end_label": "오후 2:00",
                "date_label": "2026년 4월 4일 토요일",
            }
        ],
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        lambda zone_name: datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc),
    )

    response = service.handle(_request("오늘 일정 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "live_data_result"
    assert response.payload["answer"]["task_id"] == "calendar_today"
    structured = response.payload["answer"]["structured_payload"]
    assert structured["range_kind"] == "day"
    assert structured["event_count"] == 1
    assert response.payload["guide"]["artifacts"] == []
    assert "오늘 일정 1건입니다" in response.payload["response"]["response"]


def test_ask_text_returns_month_calendar_agenda(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._list_local_calendar_events",
        lambda **kwargs: [
            {
                "calendar_name": "Home",
                "title": "여의도 국회 의사당 방문",
                "location": "여의도 국회의사당",
                "start_at": datetime(2026, 4, 7, 0, 0, tzinfo=timezone.utc),
                "end_at": datetime(2026, 4, 8, 0, 0, tzinfo=timezone.utc),
                "all_day": True,
                "start_label": "종일 일정",
                "end_label": "",
                "date_label": "2026년 4월 7일 화요일",
            },
            {
                "calendar_name": "Home",
                "title": "주간 회의",
                "location": "",
                "start_at": datetime(2026, 4, 18, 10, 0, tzinfo=timezone.utc),
                "end_at": datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
                "all_day": False,
                "start_label": "오전 10:00",
                "end_label": "오전 11:00",
                "date_label": "2026년 4월 18일 토요일",
            },
        ],
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._now_in_zone",
        lambda zone_name: datetime(2026, 4, 4, 4, 13, tzinfo=timezone.utc),
    )

    response = service.handle(_request("이번달 일정 알려줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "live_data_result"
    assert response.payload["answer"]["task_id"] == "calendar_today"
    structured = response.payload["answer"]["structured_payload"]
    assert structured["range_kind"] == "month"
    assert structured["event_count"] == 2
    assert structured["start_date"] == "2026-04-01"
    assert "이번 달 일정 2건입니다" in response.payload["response"]["response"]


def test_ask_text_records_unmapped_request_backlog(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()

    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: {
            "query_result": {
                "query": kwargs.get("query", ""),
                "response": "현재 검색된 근거가 질문의 핵심 표현과 맞지 않아 바로 답하면 잘못된 안내가 될 수 있습니다.",
                "spoken_response": "현재 검색된 근거가 질문의 핵심 표현과 맞지 않아 바로 답하면 잘못된 안내가 될 수 있습니다.",
                "has_evidence": False,
                "citations": [],
                "status": {
                    "mode": "no_evidence",
                    "safe_mode": False,
                    "degraded_mode": False,
                    "generation_blocked": False,
                    "write_blocked": False,
                    "rebuild_index_required": False,
                },
                "render_hints": {
                    "response_type": "no_evidence",
                    "primary_source_type": "none",
                    "source_profile": "none",
                    "interaction_mode": "general_query",
                    "citation_count": 0,
                    "truncated": False,
                },
                "exploration": {
                    "mode": "general_query",
                    "target_file": "",
                    "target_document": "",
                    "file_candidates": [],
                    "document_candidates": [],
                    "class_candidates": [],
                    "function_candidates": [],
                },
                "guide_directive": {
                    "intent": "",
                    "skill": "",
                    "loop_stage": "presenting",
                    "clarification_prompt": "",
                    "missing_slots": [],
                    "suggested_replies": [],
                    "should_hold": False,
                },
            }
        },
    )

    response = service.handle(_request("식재료 주문해줘", session_id="session-skill-backlog"))

    assert response.ok is True
    backlog = list_skill_backlog()
    assert backlog[0]["query_text"] == "식재료 주문해줘"
    assert backlog[0]["occurrence_count"] == 1
    assert backlog[0]["last_status_mode"] == "no_evidence"


def test_ask_text_executes_action_map(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()

    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.intent_skill_store._detect_local_app_installed",
        lambda app_name: app_name == "Spotify",
    )
    monkeypatch.setattr(
        "jarvis.service.application.execute_action",
        lambda target: ActionResult(
            success=True,
            spoken_response=f"{target.label}을 실행했습니다.",
            display_response=f"{target.label}을(를) 실행했습니다.",
            label=target.label,
            action_type=target.action_type,
            target=target.target,
        ),
    )

    create_skill_profile(
        {
            "skill_id": "spotify",
            "title": "Spotify",
            "local_app_name": "Spotify",
            "open_supported": True,
            "api_provider": "Spotify Web API",
            "api_configured": True,
        }
    )
    create_action_map(
        {
            "map_id": "spotify_focus_flow",
            "title": "Spotify Focus Flow",
            "trigger_query": "집중 음악 시작",
            "nodes": [
                {"node_id": "node_open", "skill_id": "spotify", "title": "Open Spotify", "x": 32, "y": 48},
                {"node_id": "node_play", "skill_id": "spotify", "title": "Start Focus Playlist", "x": 320, "y": 48, "config": {"mode": "api"}},
            ],
            "edges": [
                {"edge_id": "edge_1", "source": "node_open", "target": "node_play", "label": "then"},
            ],
        }
    )

    response = service.handle(_request("집중 음악 시작해줘", session_id="session-action-map"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "action_result"
    assert response.payload["answer"]["task_id"] == "action_map_execute"
    payload = response.payload["answer"]["structured_payload"]
    assert payload["map_id"] == "spotify_focus_flow"
    assert payload["summary"]["executed"] == 1
    assert payload["summary"]["api_ready"] == 1
    assert payload["steps"][0]["status"] == "executed"
    assert payload["steps"][1]["status"] == "api_ready"
    assert response.payload["guide"]["artifacts"] == []


def test_ask_text_uses_builtin_weather_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._fetch_weather",
        lambda location, fallback_label=None: (
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


def test_ask_text_builtin_weather_ignores_empty_location_particles(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    captured: dict[str, str] = {}

    def fake_fetch(location: str, fallback_label: str | None = None):
        captured["location"] = location
        captured["fallback_label"] = fallback_label or ""
        return (
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
                "weather": [],
            },
            "https://wttr.in/?format=j1&lang=ko",
        )

    monkeypatch.setattr("jarvis.service.builtin_capabilities._fetch_weather", fake_fetch)

    response = service.handle(_request("오늘 날씨는 ?"))

    assert response.ok is True
    assert captured["location"] == ""
    assert captured["fallback_label"] == "현재 위치"
    assert "는 ?" not in response.payload["response"]["response"]
    assert response.payload["response"]["response"].startswith("서울 현재 날씨는 맑음")


def test_ask_text_builtin_weather_network_failure_response_is_not_duplicated(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._fetch_weather",
        lambda location, fallback_label=None: (
            {
                "current_condition": [
                    {
                        "weatherDesc": [{"value": "현재 위치 날씨 데이터를 가져오지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요."}],
                    }
                ],
                "nearest_area": [{"areaName": [{"value": "현재 위치"}]}],
                "weather": [],
            },
            "https://wttr.in/?format=j1&lang=ko",
        ),
    )

    response = service.handle(_request("오늘 날씨는 ?"))

    assert response.ok is True
    assert response.payload["response"]["response"] == (
        "현재 위치 날씨 데이터를 가져오지 못했습니다. 네트워크 상태를 확인한 뒤 다시 시도해 주세요."
    )


def test_ask_text_builtin_weather_uses_requested_location_label_and_resolved_lookup(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.builtin_capabilities._resolve_weather_lookup_target",
        lambda location: "37.4827,126.9291",
    )

    captured: dict[str, str] = {}

    def fake_fetch(location: str, fallback_label: str | None = None):
        captured["location"] = location
        captured["fallback_label"] = fallback_label or ""
        return (
            {
                "current_condition": [
                    {
                        "temp_C": "8",
                        "FeelsLikeC": "6",
                        "weatherDesc": [{"value": "Partly cloudy"}],
                    }
                ],
                "nearest_area": [{"areaName": [{"value": "Sowondong"}]}],
                "weather": [],
            },
            "https://wttr.in/37.4827,126.9291?format=j1&lang=ko",
        )

    monkeypatch.setattr("jarvis.service.builtin_capabilities._fetch_weather", fake_fetch)

    response = service.handle(_request("신림동 오늘 날씨 알려줘"))

    assert response.ok is True
    assert captured["location"] == "37.4827,126.9291"
    assert captured["fallback_label"] == "신림동"
    assert response.payload["response"]["response"].startswith("신림동 현재 날씨는 Partly cloudy")
    assert response.payload["guide"]["artifacts"][0]["title"] == "신림동 현재 날씨"


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
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "math_eval"
    assert response.payload["answer"]["structured_payload"]["result"] == "3"
    assert response.payload["guide"]["presentation"] is None
    assert response.payload["guide"]["artifacts"] == []


def test_ask_text_uses_builtin_unit_conversion_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )

    response = service.handle(_request("3km는 몇 m야?"))

    assert response.ok is True
    assert response.payload["response"]["response"] == "3km는 3,000m입니다."
    assert response.payload["answer"]["kind"] == "utility_result"
    assert response.payload["answer"]["task_id"] == "unit_convert"
    assert response.payload["answer"]["structured_payload"]["to_unit"] == "m"


def test_ask_text_uses_builtin_document_open_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_document_task_target",
        lambda query, session_id="": {
            "title": "README.md",
            "path": "README.md",
            "full_path": "/tmp/README.md",
            "preview": "ProjectHub overview",
            "kind": "document",
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "README.md",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "README.md",
                        "kind": "document",
                        "path": "README.md",
                        "score": 1.0,
                        "preview": "ProjectHub overview",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
        },
    )

    response = service.handle(_request("README 열어줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "open_document"
    assert response.payload["guide"]["artifacts"][0]["title"] == "README.md"
    assert response.payload["guide"]["ui_hints"]["preferred_view"] == "detail_viewer"


def test_ask_text_uses_builtin_document_summary_response(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    readme = tmp_path / "README.md"
    readme.write_text(
        "# ProjectHub\n\n"
        "ProjectHub is an AI-native developer workspace.\n\n"
        "## Features\n"
        "- Terminal workflow\n"
        "- Repository explorer\n"
        "- Document viewer\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._build_navigation_window",
        lambda **kwargs: MenuBarExplorationState(mode="document_exploration"),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query, limit=4: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub is an AI-native developer workspace.",
            }
        ],
    )

    response = service.handle(_request("README 요약해줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "doc_summary"
    assert response.payload["guide"]["artifacts"][0]["title"] == "README.md"
    assert response.payload["guide"]["ui_hints"]["preferred_view"] == "detail_viewer"
    assert response.payload["answer"]["structured_payload"]["summary_lines"]


def test_ask_text_uses_builtin_document_explain_response(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    readme = tmp_path / "README.md"
    readme.write_text(
        "# ProjectHub\n\n"
        "ProjectHub is an AI-native developer workspace for repository navigation and document reasoning.\n\n"
        "## Platform\n"
        "Unified shell for terminal, repository, documents, and admin.\n\n"
        "## Developer Features\n"
        "Built-in terminal, repository explorer, document viewer, and evidence tracing.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._build_navigation_window",
        lambda **kwargs: MenuBarExplorationState(mode="document_exploration"),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query, limit=4: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub is an AI-native developer workspace.",
            }
        ] if query.lower() == "projecthub" else [],
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_topic_sources",
        lambda query, limit=6: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub is an AI-native developer workspace.",
            }
        ] if query.lower() == "projecthub" else [],
    )
    response = service.handle(_request("projecthub 에 대해 종합해서 설명해줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "doc_summary"
    assert response.payload["guide"]["artifacts"][0]["title"] == "README.md"
    assert response.payload["answer"]["structured_payload"]["summary_lines"]


def test_ask_text_uses_builtin_topic_summary_response(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    readme = tmp_path / "README.md"
    brochure = tmp_path / "ProjectHub_Brochure.pptx"
    hwp = tmp_path / "한글문서파일형식_revision1.1_20110124.hwp"
    cs_pdf = tmp_path / "씨샵.pdf"
    readme.write_text("# ProjectHub\nProjectHub is an AI-native developer workspace.", encoding="utf-8")
    brochure.write_text("placeholder", encoding="utf-8")
    hwp.write_text("placeholder", encoding="utf-8")
    cs_pdf.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query, limit=4: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub is an AI-native developer workspace.",
            },
            {
                "label": "ProjectHub_Brochure.pptx",
                "kind": "document",
                "path": "ProjectHub_Brochure.pptx",
                "full_path": str(brochure),
                "score": 2.8,
                "preview": "[Slide 1]\nDEVELOPER PRODUCTIVITY TOOL\nProjectHub macOS용 올인원 프로젝트 관리 도구\nAI 기반 자율 코딩 시스템 내장\n내장 터미널",
            },
            {
                "label": "한글문서파일형식_revision1.1_20110124.hwp",
                "kind": "document",
                "path": "legacy/한글문서파일형식_revision1.1_20110124.hwp",
                "full_path": str(hwp),
                "score": 2.7,
                "preview": "(Hwp Document File Formats)",
            },
            {
                "label": "씨샵.pdf",
                "kind": "document",
                "path": "legacy/씨샵.pdf",
                "full_path": str(cs_pdf),
                "score": 2.6,
                "preview": "C# 언어 및 .NET Framework 소개",
            },
        ] if query.lower() == "projecthub" else [],
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_topic_sources",
        lambda query, limit=6: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub is an AI-native developer workspace.",
            },
            {
                "label": "ProjectHub_Brochure.pptx",
                "kind": "document",
                "path": "ProjectHub_Brochure.pptx",
                "full_path": str(brochure),
                "score": 2.8,
                "preview": "[Slide 1]\nDEVELOPER PRODUCTIVITY TOOL\nProjectHub macOS용 올인원 프로젝트 관리 도구\nAI 기반 자율 코딩 시스템 내장\n내장 터미널",
            },
            {
                "label": "한글문서파일형식_revision1.1_20110124.hwp",
                "kind": "document",
                "path": "legacy/한글문서파일형식_revision1.1_20110124.hwp",
                "full_path": str(hwp),
                "score": 2.7,
                "preview": "(Hwp Document File Formats)",
            },
            {
                "label": "씨샵.pdf",
                "kind": "document",
                "path": "legacy/씨샵.pdf",
                "full_path": str(cs_pdf),
                "score": 2.6,
                "preview": "C# 언어 및 .NET Framework 소개",
            },
        ] if query.lower() == "projecthub" else [],
    )

    def fake_load_document_task_content(full_path: str) -> dict[str, object]:
        if full_path == str(readme):
            return {
                "path": readme,
                "format": "markdown",
                "text": "# ProjectHub\nProjectHub is an AI-native developer workspace.\n\n## Features\nTerminal, repository, and documents.",
                "elements": [],
            }
        return {
            "path": brochure,
            "format": "pptx",
            "text": "[Slide 1]\nDEVELOPER PRODUCTIVITY TOOL\nProjectHub macOS용 올인원 프로젝트 관리 도구\nAI 기반 자율 코딩 시스템 내장\n내장 터미널\n\n[Slide 2]\nPROBLEM",
            "elements": [],
        }

    monkeypatch.setattr("jarvis.service.application._load_document_task_content", fake_load_document_task_content)
    monkeypatch.setattr(
        "jarvis.service.application._generate_topic_summary_with_llm",
        lambda query, topic_title, targets, fallback_summary_lines: {
            "query": query,
            "response": "ProjectHub는 AI 기반 터미널, 저장소 탐색, 문서 뷰어를 통합한 macOS용 개발 작업 공간입니다. 관련 자료들은 ProjectHub가 프로젝트 관리와 문서 근거 확인을 한 화면에서 처리하도록 설계됐다는 점을 공통으로 보여줍니다.",
            "spoken_response": "ProjectHub는 AI 기반 터미널, 저장소 탐색, 문서 뷰어를 통합한 macOS용 개발 작업 공간입니다. 관련 자료들은 ProjectHub가 프로젝트 관리와 문서 근거 확인을 한 화면에서 처리하도록 설계됐다는 점을 공통으로 보여줍니다.",
            "has_evidence": True,
            "citations": [],
            "status": {"mode": "builtin_capability"},
            "render_hints": {"response_type": "builtin_answer", "interaction_mode": "document_exploration"},
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": target["title"],
                        "kind": "document",
                        "path": target["path"],
                        "score": 1.0,
                        "preview": target["preview"],
                    }
                    for target in targets
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
            "guide_directive": {"suggested_replies": [f"{targets[0]['title']} 열어줘"]},
            "answer_kind": "retrieval_result",
            "task_id": "doc_summary",
            "structured_payload": {
                "title": topic_title,
                "format": "multi_document",
                "summary_lines": fallback_summary_lines,
                "outline": [],
                "source_titles": [target["title"] for target in targets],
                "source_count": len(targets),
                "ai_synthesized": True,
                "model_id": "qwen3.5:9b",
            },
            "ui_hints": {
                "show_documents": True,
                "show_repository": True,
                "show_inspector": False,
                "preferred_view": "dashboard",
            },
        },
    )

    response = service.handle(_request("ProjectHub 에 대해 설명해줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "doc_summary"
    assert response.payload["answer"]["structured_payload"]["title"] == "ProjectHub"
    assert response.payload["answer"]["structured_payload"]["source_count"] == 2
    assert len(response.payload["guide"]["artifacts"]) == 2
    assert response.payload["answer"]["text"].startswith("ProjectHub는")
    assert response.payload["answer"]["structured_payload"]["source_titles"] == ["README.md", "ProjectHub_Brochure.pptx"]
    assert response.payload["answer"]["structured_payload"]["ai_synthesized"] is True
    assert response.payload["guide"]["ui_hints"]["preferred_view"] == "dashboard"


def test_ask_text_uses_builtin_topic_summary_response_for_descriptor_query(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    readme = tmp_path / "JARVIS_README.md"
    architecture = tmp_path / "JARVIS_Architecture.md"
    readme.write_text("# JARVIS\nJARVIS는 로컬 AI 비서입니다.", encoding="utf-8")
    architecture.write_text("# JARVIS Architecture\nSwift host와 Python core로 구성됩니다.", encoding="utf-8")

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_topic_sources",
        lambda query, limit=6: [
            {
                "label": "JARVIS_README.md",
                "kind": "document",
                "path": "JARVIS_README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "JARVIS는 로컬 AI 비서입니다.",
            },
            {
                "label": "JARVIS_Architecture.md",
                "kind": "document",
                "path": "JARVIS_Architecture.md",
                "full_path": str(architecture),
                "score": 2.9,
                "preview": "Swift host와 Python core로 구성됩니다.",
            },
        ] if query.lower() == "jarvis" else [],
    )

    def fake_load_document_task_content(full_path: str) -> dict[str, object]:
        if full_path == str(readme):
            return {
                "path": readme,
                "format": "markdown",
                "text": "# JARVIS\nJARVIS는 로컬 AI 비서입니다.\n\n사용자 질의, 문서 탐색, 자동화 흐름을 지원합니다.",
                "elements": [],
            }
        return {
            "path": architecture,
            "format": "markdown",
            "text": "# JARVIS Architecture\nSwift host와 Python core로 구성됩니다.\n\n문서 검색, 터미널, 뷰어를 하나의 워크스페이스로 통합합니다.",
            "elements": [],
        }

    monkeypatch.setattr("jarvis.service.application._load_document_task_content", fake_load_document_task_content)
    monkeypatch.setattr(
        "jarvis.service.application._generate_topic_summary_with_llm",
        lambda query, topic_title, targets, fallback_summary_lines: {
            "query": query,
            "response": "JARVIS는 로컬에서 실행되는 AI 비서로, Swift host와 Python core를 결합해 터미널, 문서 탐색, 작업 자동화를 하나의 흐름으로 묶습니다. 관련 자료들은 JARVIS가 문서 근거 기반 응답과 워크스페이스 통합을 핵심 기술 사양으로 둔다는 점을 공통으로 보여줍니다.",
            "spoken_response": "JARVIS는 로컬에서 실행되는 AI 비서로, Swift host와 Python core를 결합해 터미널, 문서 탐색, 작업 자동화를 하나의 흐름으로 묶습니다. 관련 자료들은 JARVIS가 문서 근거 기반 응답과 워크스페이스 통합을 핵심 기술 사양으로 둔다는 점을 공통으로 보여줍니다.",
            "has_evidence": True,
            "citations": [],
            "status": {"mode": "builtin_capability"},
            "render_hints": {"response_type": "builtin_answer", "interaction_mode": "document_exploration"},
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": target["title"],
                        "kind": "document",
                        "path": target["path"],
                        "score": 1.0,
                        "preview": target["preview"],
                    }
                    for target in targets
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
            "guide_directive": {"suggested_replies": [f"{targets[0]['title']} 열어줘"]},
            "answer_kind": "retrieval_result",
            "task_id": "doc_summary",
            "structured_payload": {
                "title": topic_title,
                "format": "multi_document",
                "summary_lines": fallback_summary_lines,
                "outline": [],
                "source_titles": [target["title"] for target in targets],
                "source_count": len(targets),
                "ai_synthesized": True,
                "model_id": "qwen3.5:9b",
            },
            "ui_hints": {
                "show_documents": True,
                "show_repository": True,
                "show_inspector": False,
                "preferred_view": "dashboard",
            },
        },
    )

    response = service.handle(_request("JARVIS의 기술 사양에 대해 알려줘"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "doc_summary"
    assert response.payload["answer"]["structured_payload"]["title"] == "JARVIS"
    assert response.payload["answer"]["structured_payload"]["source_count"] == 2
    assert len(response.payload["guide"]["artifacts"]) == 2
    assert response.payload["answer"]["text"].startswith("JARVIS는")


def test_ask_text_uses_builtin_document_outline_response(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    readme = tmp_path / "README.md"
    readme.write_text(
        "# ProjectHub\n\n"
        "## Features\n"
        "Terminal workflow\n\n"
        "## Documents\n"
        "Viewer and evidence tools\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._build_navigation_window",
        lambda **kwargs: MenuBarExplorationState(mode="document_exploration"),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query: [
            {
                "label": "README.md",
                "kind": "document",
                "path": "README.md",
                "full_path": str(readme),
                "score": 3.0,
                "preview": "ProjectHub outline",
            }
        ],
    )

    response = service.handle(_request("README 목차 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "doc_outline"
    assert response.payload["guide"]["artifacts"][0]["title"] == "README.md"
    assert response.payload["answer"]["structured_payload"]["outline"][0] == "ProjectHub"


def test_ask_text_uses_builtin_code_structure_outline_response(monkeypatch, tmp_path) -> None:
    service = JarvisApplicationService()
    app_code = tmp_path / "main.py"
    app_code.write_text(
        "import os\n"
        "from pathlib import Path\n\n"
        "class ProjectHubApp:\n"
        "    def run(self) -> None:\n"
        "        print('running')\n\n"
        "def build_workspace() -> None:\n"
        "    return None\n\n"
        "def main() -> None:\n"
        "    ProjectHubApp().run()\n",
        encoding="utf-8",
    )

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._build_navigation_window",
        lambda **kwargs: MenuBarExplorationState(mode="document_exploration"),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query: [
            {
                "label": "code:python",
                "kind": "document",
                "path": "src/main.py",
                "full_path": str(app_code),
                "score": 2.5,
                "preview": "Python application entrypoint",
            }
        ] if query.lower() == "code:python" else [],
    )

    response = service.handle(_request("code:python에서 전체 코드 구조에 대해 설명해줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "doc_outline"
    outline = response.payload["answer"]["structured_payload"]["outline"]
    assert any(entry == "class ProjectHubApp" for entry in outline)
    assert any(entry == "def main" for entry in outline)
    assert "코드 구조" in response.payload["response"]["response"]


def test_ask_text_uses_builtin_sheet_list_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_document_task_target",
        lambda query, session_id="": {
            "title": "diet.xlsx",
            "path": "diet.xlsx",
            "full_path": "/tmp/diet.xlsx",
            "preview": "",
            "kind": "document",
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "diet.xlsx",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "diet.xlsx",
                        "kind": "document",
                        "path": "diet.xlsx",
                        "score": 1.0,
                        "preview": "",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
        },
    )
    monkeypatch.setattr(
        "jarvis.service.application._load_document_task_content",
        lambda full_path: {
            "path": full_path,
            "format": "xlsx",
            "text": "",
            "elements": [
                DocumentElement(
                    element_type="table",
                    text="[Day1] Breakfast | Lunch",
                    metadata={"sheet_name": "Day1", "headers": ("Breakfast", "Lunch"), "rows": (("Egg", "Salad"),)},
                ),
                DocumentElement(
                    element_type="table",
                    text="[Day2] Breakfast | Lunch",
                    metadata={"sheet_name": "Day2", "headers": ("Breakfast", "Lunch"), "rows": (("Yogurt", "Soup"),)},
                ),
            ],
        },
    )

    response = service.handle(_request("diet.xlsx sheet 목록 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "sheet_list"
    assert len(response.payload["answer"]["structured_payload"]["sheets"]) == 2
    assert response.payload["answer"]["structured_payload"]["sheets"][0]["sheet_name"] == "Day1"


def test_ask_text_uses_builtin_document_section_for_slide(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_document_task_target",
        lambda query, session_id="": {
            "title": "brochure.pptx",
            "path": "brochure.pptx",
            "full_path": "/tmp/brochure.pptx",
            "preview": "",
            "kind": "document",
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "brochure.pptx",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "brochure.pptx",
                        "kind": "document",
                        "path": "brochure.pptx",
                        "score": 1.0,
                        "preview": "",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
        },
    )
    monkeypatch.setattr(
        "jarvis.service.application._load_document_task_content",
        lambda full_path: {
            "path": full_path,
            "format": "pptx",
            "text": "[Slide 1]\nIntro\n\n[Slide 2]\nDeveloper Features\nBuilt-in terminal\n[Notes] demo",
            "elements": [],
        },
    )

    response = service.handle(_request("brochure 2슬라이드 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "doc_section"
    assert response.payload["answer"]["structured_payload"]["section_kind"] == "slide"
    assert response.payload["answer"]["structured_payload"]["section_index"] == 2
    assert response.payload["answer"]["structured_payload"]["section_lines"][0] == "Developer Features"


def test_ask_text_uses_builtin_document_section_for_page(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_document_task_target",
        lambda query, session_id="": {
            "title": "guide.pdf",
            "path": "guide.pdf",
            "full_path": "/tmp/guide.pdf",
            "preview": "",
            "kind": "document",
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "guide.pdf",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "guide.pdf",
                        "kind": "document",
                        "path": "guide.pdf",
                        "score": 1.0,
                        "preview": "",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
        },
    )
    monkeypatch.setattr(
        "jarvis.service.application._load_document_task_content",
        lambda full_path: {
            "path": full_path,
            "format": "pdf",
            "text": "",
            "elements": [
                DocumentElement(element_type="text", text="Page one summary", metadata={"page": 1}),
                DocumentElement(element_type="text", text="Page two details", metadata={"page": 2}),
            ],
        },
    )

    response = service.handle(_request("guide.pdf 2페이지 내용 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "doc_section"
    assert response.payload["answer"]["structured_payload"]["section_kind"] == "page"
    assert response.payload["answer"]["structured_payload"]["section_label"] == "Page 2"
    assert response.payload["answer"]["structured_payload"]["section_lines"][0] == "Page two details"


def test_ask_text_uses_builtin_document_sheet_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_document_task_target_from_lookup",
        lambda lookup_query, session_id="": {
            "title": "diet.xlsx",
            "path": "diet.xlsx",
            "full_path": "/tmp/diet.xlsx",
            "preview": "",
            "kind": "document",
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "diet.xlsx",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "diet.xlsx",
                        "kind": "document",
                        "path": "diet.xlsx",
                        "score": 1.0,
                        "preview": "",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
        },
    )
    monkeypatch.setattr(
        "jarvis.service.application._load_document_task_content",
        lambda full_path: {
            "path": full_path,
            "format": "xlsx",
            "text": "",
            "elements": [
                DocumentElement(
                    element_type="table",
                    text="[Day1] Breakfast | Lunch",
                    metadata={"sheet_name": "Day1", "headers": ("Breakfast", "Lunch"), "rows": (("Egg", "Salad"),)},
                ),
                DocumentElement(
                    element_type="table",
                    text="[Day2] Breakfast | Lunch",
                    metadata={"sheet_name": "Day2", "headers": ("Breakfast", "Lunch"), "rows": (("Yogurt", "Soup"),)},
                ),
            ],
        },
    )

    response = service.handle(_request("diet.xlsx 2번째 시트 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "doc_sheet"
    assert response.payload["answer"]["structured_payload"]["sheet_name"] == "Day2"
    assert response.payload["answer"]["structured_payload"]["sheet_index"] == 2


def test_ask_text_uses_relative_document_section_from_session_state(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._build_navigation_window",
        lambda **kwargs: MenuBarExplorationState(mode="document_exploration"),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query: [
            {
                "label": "brochure.pptx",
                "kind": "document",
                "path": "brochure.pptx",
                "full_path": "/tmp/brochure.pptx",
                "score": 3.0,
                "preview": "Slide deck",
            }
        ] if "brochure" in query.lower() else [],
    )
    monkeypatch.setattr(
        "jarvis.service.application._load_document_task_content",
        lambda full_path: {
            "path": full_path,
            "format": "pptx",
            "text": "[Slide 1]\nIntro\n\n[Slide 2]\nDeveloper Features\n\n[Slide 3]\nRepository Explorer",
            "elements": [],
        },
    )

    first_response = service.handle(_request("brochure 2슬라이드 보여줘", session_id="session-relative-slide"))
    second_response = service.handle(_request("다음 슬라이드 보여줘", session_id="session-relative-slide"))

    assert first_response.ok is True
    assert second_response.ok is True
    assert second_response.payload["answer"]["task_id"] == "doc_section"
    assert second_response.payload["answer"]["structured_payload"]["section_index"] == 3
    assert second_response.payload["answer"]["structured_payload"]["section_lines"][0] == "Repository Explorer"


def test_ask_text_clarifies_document_outline_without_target(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._search_knowledge_base_documents",
        lambda query: [],
    )

    response = service.handle(_request("목차 보여줘", session_id="session-outline-clarify"))

    assert response.ok is True
    assert response.payload["answer"]["task_id"] == "doc_outline"
    assert response.payload["guide"]["has_clarification"] is True
    assert response.payload["guide"]["missing_slots"] == ["target_document"]


def test_ask_text_uses_recent_context_response(monkeypatch) -> None:
    service = JarvisApplicationService()

    monkeypatch.setattr("jarvis.service.application._prime_tts_cache_async", lambda payload: None)
    monkeypatch.setattr(
        "jarvis.service.application._run_menu_bridge_ask_with_fallback",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("menu bridge should not run")),
    )
    monkeypatch.setattr(
        "jarvis.service.application._resolve_recent_context_payload",
        lambda query, session_id="": {
            "query": query,
            "response": "방금 확인한 자료를 다시 열었습니다.",
            "spoken_response": "방금 확인한 자료를 다시 열었습니다.",
            "has_evidence": True,
            "citations": [
                {
                    "label": "[1]",
                    "source_path": "README.md",
                    "full_source_path": "/tmp/README.md",
                    "source_type": "document",
                    "quote": "ProjectHub overview",
                    "state": "valid",
                    "relevance_score": 1.0,
                    "heading_path": "Overview",
                }
            ],
            "status": {"mode": "builtin_capability"},
            "render_hints": {
                "response_type": "builtin_answer",
                "primary_source_type": "document",
                "source_profile": "recent_context",
                "interaction_mode": "document_exploration",
                "citation_count": 1,
                "truncated": False,
            },
            "exploration": {
                "mode": "document_exploration",
                "target_file": "",
                "target_document": "README.md",
                "file_candidates": [],
                "document_candidates": [
                    {
                        "label": "README.md",
                        "kind": "document",
                        "path": "README.md",
                        "score": 1.0,
                        "preview": "ProjectHub overview",
                    }
                ],
                "class_candidates": [],
                "function_candidates": [],
            },
            "guide_directive": {
                "intent": "recent_context",
                "skill": "builtin_recent_context",
                "loop_stage": "presenting",
                "clarification_prompt": "",
                "missing_slots": [],
                "suggested_replies": [],
                "should_hold": False,
            },
            "answer_kind": "retrieval_result",
            "task_id": "recent_context",
            "structured_payload": {"citation_count": 1},
            "ui_hints": {
                "show_documents": True,
                "show_repository": True,
                "show_inspector": True,
                "preferred_view": "detail_viewer",
            },
        },
    )

    response = service.handle(_request("방금 본 문서 다시 보여줘"))

    assert response.ok is True
    assert response.payload["answer"]["kind"] == "retrieval_result"
    assert response.payload["answer"]["task_id"] == "recent_context"
    assert response.payload["guide"]["artifacts"][0]["title"] == "README.md"
    assert response.payload["guide"]["ui_hints"]["preferred_view"] == "detail_viewer"


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
    assert len(llm_called) == 1
