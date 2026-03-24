"""Shared query normalization helpers."""

from __future__ import annotations

from pathlib import Path

from jarvis.identifier_restoration import rewrite_query_with_identifiers


def normalize_spoken_code_query(text: str, *, knowledge_base_path: Path | None = None) -> str:
    """Preserve the original query and append high-confidence identifier anchors."""
    return rewrite_query_with_identifiers(
        text,
        knowledge_base_path=knowledge_base_path,
    ).rewritten_query
