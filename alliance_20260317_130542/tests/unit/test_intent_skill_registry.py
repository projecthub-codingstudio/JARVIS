"""Tests for the intent skill registry."""

from jarvis.service.intent_skill_registry import load_intent_skill_registry


def test_intent_skill_registry_loads_entries() -> None:
    registry = load_intent_skill_registry()

    assert registry.version == "2026-04-04"
    assert len(registry.entries) >= 10


def test_intent_skill_registry_contains_relative_date_and_calendar_followup() -> None:
    registry = load_intent_skill_registry()

    relative_date = registry.get("relative_date")
    calendar_followup = registry.get("calendar_followup")
    calendar_today = registry.get("calendar_today")
    calendar_create = registry.get("calendar_create")
    calendar_update = registry.get("calendar_update")

    assert relative_date is not None
    assert relative_date.skill_id == "builtin_date_relative"
    assert "last_relative_date" in relative_date.stores_context

    assert calendar_followup is not None
    assert calendar_followup.requires_live_data is False
    assert calendar_followup.implementation_status == "implemented"

    assert calendar_today is not None
    assert calendar_today.skill_id == "macos_calendar_agenda_view"
    assert calendar_today.response_kind == "live_data_result"
    assert calendar_today.implementation_status == "implemented"

    assert calendar_create is not None
    assert calendar_create.skill_id == "macos_calendar_create_event"
    assert calendar_create.response_kind == "action_result"
    assert calendar_create.implementation_status == "implemented"

    assert calendar_update is not None
    assert calendar_update.skill_id == "macos_calendar_update_event"
    assert calendar_update.response_kind == "action_result"
    assert calendar_update.implementation_status == "implemented"


def test_intent_skill_registry_exposes_dispatchable_and_backlog_entries() -> None:
    registry = load_intent_skill_registry()

    dispatchable_ids = {entry.intent_id for entry in registry.dispatchable_entries()}
    backlog_ids = {entry.intent_id for entry in registry.backlog_entries()}

    assert "relative_date" in dispatchable_ids
    assert "calendar_today" in dispatchable_ids
    assert "calendar_create" in dispatchable_ids
    assert "calendar_update" in dispatchable_ids
    assert "calendar_today" not in backlog_ids
    assert "calendar_create" not in backlog_ids
