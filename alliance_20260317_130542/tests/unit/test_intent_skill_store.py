"""Tests for persistent skill and action-map state."""

from jarvis.service.intent_skill_store import (
    build_action_map_execution_plan,
    build_skill_catalog,
    create_action_map,
    create_skill_profile,
    list_action_maps,
    list_skill_backlog,
    record_unmapped_request,
)


def test_build_skill_catalog_includes_custom_skill_profile(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "jarvis.service.intent_skill_store._detect_local_app_installed",
        lambda app_name: app_name == "Spotify",
    )

    create_skill_profile(
        {
            "skill_id": "spotify",
            "title": "Spotify",
            "summary": "Open Spotify locally and drive playback through API.",
            "local_app_name": "Spotify",
            "open_supported": True,
            "api_provider": "Spotify Web API",
            "api_configured": True,
            "api_scopes": ["user-read-playback-state", "user-modify-playback-state"],
        }
    )

    catalog = build_skill_catalog()
    spotify = next(skill for skill in catalog["skills"] if skill["skill_id"] == "spotify")

    assert spotify["title"] == "Spotify"
    assert spotify["api_provider"] == "Spotify Web API"
    assert spotify["effective_local_app_installed"] is True
    assert spotify["source_kind"] == "custom"


def test_build_skill_catalog_includes_default_builtin_profiles(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "jarvis.service.intent_skill_store._detect_local_app_installed",
        lambda app_name: app_name == "Calendar",
    )

    catalog = build_skill_catalog()

    calendar_view = next(skill for skill in catalog["skills"] if skill["skill_id"] == "macos_calendar_agenda_view")
    calendar_create = next(skill for skill in catalog["skills"] if skill["skill_id"] == "macos_calendar_create_event")
    calendar_followup = next(skill for skill in catalog["skills"] if skill["skill_id"] == "builtin_calendar_followup")
    calendar_update = next(skill for skill in catalog["skills"] if skill["skill_id"] == "macos_calendar_update_event")
    builtin_time = next(skill for skill in catalog["skills"] if skill["skill_id"] == "builtin_time")

    assert calendar_view["summary"] == "macOS Calendar의 오늘, 주간, 월간 일정을 읽어 요약합니다."
    assert calendar_view["local_app_name"] == "Calendar"
    assert calendar_view["open_supported"] is True
    assert "calendar_today" in calendar_view["linked_intent_ids"]
    assert calendar_create["summary"] == "macOS Calendar 앱에 로컬 일정을 생성합니다."
    assert calendar_create["local_app_name"] == "Calendar"
    assert calendar_create["open_supported"] is True
    assert calendar_create["effective_local_app_installed"] is True
    assert calendar_create["source_kind"] == "hybrid"
    assert calendar_update["summary"] == "macOS Calendar의 기존 일정을 찾아 날짜와 시간을 수정합니다."
    assert calendar_update["local_app_name"] == "Calendar"
    assert calendar_update["open_supported"] is True

    assert calendar_followup["summary"]
    assert "calendar_create" in calendar_create["linked_intent_ids"]
    assert "calendar_update" in calendar_update["linked_intent_ids"]
    assert "calendar_followup" in calendar_followup["linked_intent_ids"]
    assert builtin_time["summary"]


def test_record_unmapped_request_aggregates_occurrences(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))

    response_payload = {
        "response": "현재 검색된 근거가 질문과 맞지 않습니다.",
        "status": {"mode": "no_evidence"},
        "guide_directive": {"intent": "", "missing_slots": []},
    }

    record_unmapped_request(
        query="식재료 주문해줘",
        session_id="session-a",
        response_payload=response_payload,
    )
    record_unmapped_request(
        query="식재료 주문해줘",
        session_id="session-b",
        response_payload=response_payload,
    )

    backlog = list_skill_backlog()

    assert backlog[0]["query_text"] == "식재료 주문해줘"
    assert backlog[0]["occurrence_count"] == 2
    assert backlog[0]["session_ids"] == ["session-a", "session-b"]
    assert sum(backlog[0]["hour_histogram"].values()) == 2


def test_create_action_map_persists_nodes_and_edges(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))

    create_action_map(
        {
            "map_id": "spotify_focus_flow",
            "title": "Spotify Focus Flow",
            "nodes": [
                {"node_id": "node_open", "skill_id": "spotify", "title": "Open Spotify", "x": 32, "y": 48},
                {"node_id": "node_play", "skill_id": "spotify", "title": "Start Focus Playlist", "x": 320, "y": 48},
            ],
            "edges": [
                {"edge_id": "edge_1", "source": "node_open", "target": "node_play", "label": "then"},
            ],
        }
    )

    action_maps = list_action_maps()

    assert action_maps[0]["map_id"] == "spotify_focus_flow"
    assert len(action_maps[0]["nodes"]) == 2
    assert action_maps[0]["edges"][0]["label"] == "then"


def test_build_action_map_execution_plan_matches_trigger_query(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "jarvis.service.intent_skill_store._detect_local_app_installed",
        lambda app_name: app_name == "Spotify",
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

    plan = build_action_map_execution_plan("집중 음악 시작해줘")

    assert plan is not None
    assert plan["map_id"] == "spotify_focus_flow"
    assert [step["node_id"] for step in plan["steps"]] == ["node_open", "node_play"]
    assert plan["steps"][0]["status"] == "ready_to_launch"
    assert plan["steps"][1]["status"] == "api_ready"
