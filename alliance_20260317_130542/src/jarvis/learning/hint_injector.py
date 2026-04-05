"""HintInjector — safely merge learned entity hints into planner-extracted entities."""
from __future__ import annotations


def merge_entities(
    *,
    explicit: dict[str, object],
    learned: dict[str, object],
) -> dict[str, object]:
    """Merge learned hints into explicit entities. Explicit always wins."""
    if not learned:
        return dict(explicit)

    merged: dict[str, object] = dict(explicit)
    source_map: dict[str, str] = {}
    for key, value in learned.items():
        if key == "__source_map":
            continue
        if key in merged and merged[key]:
            continue
        merged[key] = value
        source_map[key] = "learned_pattern"

    if source_map:
        merged["__source_map"] = source_map
    return merged
