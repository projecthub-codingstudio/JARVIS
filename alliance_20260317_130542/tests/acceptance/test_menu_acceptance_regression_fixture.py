from __future__ import annotations

import json
from pathlib import Path


def test_menu_acceptance_regression_fixture_has_minimum_coverage() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "menu_acceptance_regression_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    queries = payload["queries"]
    assert len(queries) >= 5

    categories = {item["category"] for item in queries}
    assert "diet_slot_repair" in categories
    assert "greeting_plus_day_slot_repair" in categories
    assert "transcript_tail_noise" in categories
    assert "stable_table_lookup" in categories


def test_menu_acceptance_regression_fixture_has_required_fields() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "menu_acceptance_regression_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    for item in payload["queries"]:
        assert item["id"]
        assert item["raw_transcript"]
        assert item["expected_display_text"]
        assert item["expected_final_query"]
        assert item["expected_spoken_response"]
        assert item["category"]
