from __future__ import annotations

from jarvis.learning.hint_injector import merge_entities


def test_explicit_wins_over_learned() -> None:
    explicit = {"row_ids": ["3"]}
    learned = {"row_ids": ["7"], "fields": ["dinner"]}
    merged = merge_entities(explicit=explicit, learned=learned)
    assert merged["row_ids"] == ["3"]
    assert merged["fields"] == ["dinner"]


def test_learned_fills_missing_keys() -> None:
    explicit = {}
    learned = {"row_ids": ["3"], "fields": ["dinner"]}
    merged = merge_entities(explicit=explicit, learned=learned)
    assert merged == {
        "row_ids": ["3"],
        "fields": ["dinner"],
        "__source_map": {"row_ids": "learned_pattern", "fields": "learned_pattern"},
    }


def test_source_map_marks_learned_entries_only() -> None:
    explicit = {"row_ids": ["3"]}
    learned = {"fields": ["dinner"]}
    merged = merge_entities(explicit=explicit, learned=learned)
    assert merged["__source_map"] == {"fields": "learned_pattern"}


def test_empty_learned_returns_explicit_unchanged() -> None:
    explicit = {"row_ids": ["3"]}
    merged = merge_entities(explicit=explicit, learned={})
    assert merged == {"row_ids": ["3"]}
