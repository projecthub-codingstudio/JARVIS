# tests/unit/test_planner_hint_injection.py
from __future__ import annotations

from jarvis.core.planner import Planner


class _FakeCoordinator:
    def __init__(self, hints: dict) -> None:
        self._hints = hints

    def inject_hints(self, *, query: str, retrieval_task: str, explicit_entities: dict) -> dict:
        merged = dict(explicit_entities)
        for k, v in self._hints.items():
            if k not in merged:
                merged[k] = v
        return merged


def test_planner_applies_learned_hints_when_entities_empty() -> None:
    coord = _FakeCoordinator(hints={"row_ids": ["3"], "fields": ["dinner"]})
    planner = Planner(lightweight_backend=None, learning_coordinator=coord)
    analysis = planner.analyze("식단표 알려줘")
    assert "row_ids" in analysis.entities
    assert analysis.entities["row_ids"] == ["3"]


def test_planner_without_coordinator_works_unchanged() -> None:
    planner = Planner(lightweight_backend=None)
    analysis = planner.analyze("식단표 3일차 저녁 메뉴")
    assert analysis.retrieval_task == "table_lookup"
    assert "row_ids" in analysis.entities
