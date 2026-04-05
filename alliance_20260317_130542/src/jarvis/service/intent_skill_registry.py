"""Load and query the intent-to-skill registry."""

from __future__ import annotations

from dataclasses import dataclass
import json
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class IntentSkillEntry:
    intent_id: str
    skill_id: str
    category: str
    executor: str
    response_kind: str
    requires_retrieval: bool
    requires_live_data: bool
    stores_context: tuple[str, ...]
    automation_ready: bool
    implementation_status: str
    example_queries: tuple[str, ...]


@dataclass(frozen=True)
class IntentSkillRegistry:
    version: str
    description: str
    entries: tuple[IntentSkillEntry, ...]

    def get(self, intent_id: str) -> IntentSkillEntry | None:
        normalized = intent_id.strip()
        if not normalized:
            return None
        for entry in self.entries:
            if entry.intent_id == normalized:
                return entry
        return None

    def implemented_entries(self) -> tuple[IntentSkillEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.implementation_status.startswith("implemented")
        )

    def dispatchable_entries(self) -> tuple[IntentSkillEntry, ...]:
        return self.implemented_entries()

    def planned_entries(self) -> tuple[IntentSkillEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if entry.implementation_status == "planned"
        )

    def backlog_entries(self) -> tuple[IntentSkillEntry, ...]:
        return tuple(
            entry
            for entry in self.entries
            if not entry.implementation_status.startswith("implemented")
        )


def _registry_path() -> Path:
    return Path(__file__).with_name("intent_skill_map.v1.json")


def _entry_from_dict(payload: dict[str, object]) -> IntentSkillEntry:
    return IntentSkillEntry(
        intent_id=str(payload.get("intent_id", "")).strip(),
        skill_id=str(payload.get("skill_id", "")).strip(),
        category=str(payload.get("category", "")).strip(),
        executor=str(payload.get("executor", "")).strip(),
        response_kind=str(payload.get("response_kind", "")).strip(),
        requires_retrieval=bool(payload.get("requires_retrieval", False)),
        requires_live_data=bool(payload.get("requires_live_data", False)),
        stores_context=tuple(
            str(item).strip()
            for item in payload.get("stores_context", [])
            if str(item).strip()
        ),
        automation_ready=bool(payload.get("automation_ready", False)),
        implementation_status=str(payload.get("implementation_status", "")).strip(),
        example_queries=tuple(
            str(item).strip()
            for item in payload.get("example_queries", [])
            if str(item).strip()
        ),
    )


@lru_cache(maxsize=1)
def load_intent_skill_registry() -> IntentSkillRegistry:
    payload = json.loads(_registry_path().read_text(encoding="utf-8"))
    entries = tuple(
        _entry_from_dict(item)
        for item in payload.get("entries", [])
        if isinstance(item, dict)
    )
    return IntentSkillRegistry(
        version=str(payload.get("version", "")).strip(),
        description=str(payload.get("description", "")).strip(),
        entries=entries,
    )
