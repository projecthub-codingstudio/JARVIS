from __future__ import annotations

import json
from pathlib import Path


def test_retrieval_regression_fixture_has_minimum_coverage() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "retrieval_regression_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    queries = payload["queries"]
    assert len(queries) >= 40

    categories = {item["category"] for item in queries}
    assert "document_section_lookup" in categories
    assert "table_row_field_lookup" in categories
    assert "mixed_greeting_task" in categories
    assert "numeric_in_prose" in categories
    assert "stt_corruption" in categories
    assert "stt_slot_corruption" in categories
    assert "transcript_tail_noise" in categories
    assert "mixed_task_disambiguation" in categories
    assert "live_data_request" in categories


def test_retrieval_regression_fixture_has_required_fields() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "retrieval_regression_v1.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    for item in payload["queries"]:
        assert item["id"]
        assert item["query"]
        assert item["expected_retrieval_task"]
        assert item["category"]
