"""Best-effort spoken-response prediction for early TTS prefetch.

This module is intentionally conservative. It predicts only deterministic
diet table answers where the eventual spoken response is stable enough to
match the main answer path exactly.
"""

from __future__ import annotations

import sqlite3
import re
from pathlib import Path

from jarvis.runtime.mlx_runtime import (
    _parse_table_row,
    _render_table_row,
    _requested_table_field_pairs,
    _requested_table_fields,
)
from jarvis.runtime_paths import resolve_menubar_data_dir
from jarvis.transcript_repair import build_transcript_repair

_DAY_QUERY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*일차")
_DIET_QUERY_HINT_RE = re.compile(r"(다이어트|식단표|식단|메뉴|아침|점심|저녁)", re.IGNORECASE)


def predict_prefetchable_spoken_response(
    query: str,
    *,
    data_dir: Path | None = None,
) -> str:
    repaired = build_transcript_repair(query)
    final_query = repaired.final_query.strip()
    if not final_query or not _DIET_QUERY_HINT_RE.search(final_query):
        return ""

    requested_fields = _requested_table_fields(final_query)
    requested_pairs = _requested_table_field_pairs(final_query)
    if requested_pairs:
        rendered_rows = []
        for day_value, pair_fields in requested_pairs.items():
            row_text = _lookup_diet_table_row_text(
                day=day_value,
                requested_fields=pair_fields,
                data_dir=data_dir,
            )
            if not row_text:
                return ""
            parsed = _parse_table_row(row_text)
            if not parsed:
                return ""
            rendered = _render_table_row(parsed, requested_fields=pair_fields, spoken=True).strip()
            if rendered:
                rendered_rows.append(rendered)
        return " / ".join(rendered_rows).strip()

    if not requested_fields:
        return ""

    requested_days = list(dict.fromkeys(int(value) for value in _DAY_QUERY_RE.findall(final_query)))
    if len(requested_days) != 1:
        return ""

    row_text = _lookup_diet_table_row_text(
        day=requested_days[0],
        requested_fields=requested_fields,
        data_dir=data_dir,
    )
    if not row_text:
        return ""

    parsed = _parse_table_row(row_text)
    if not parsed:
        return ""

    return _render_table_row(parsed, requested_fields=requested_fields, spoken=True).strip()


def _lookup_diet_table_row_text(
    *,
    day: int,
    requested_fields: list[str],
    data_dir: Path | None = None,
) -> str:
    db_path = (data_dir or resolve_menubar_data_dir()) / "jarvis.db"
    if not db_path.exists():
        return ""

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            SELECT d.path, c.text
            FROM chunks c
            JOIN documents d ON d.document_id = c.document_id
            WHERE c.heading_path LIKE 'table-row-%'
              AND c.text LIKE ?
            """,
            (f"%Day={day} |%",),
        ).fetchall()
    finally:
        connection.close()

    candidates: list[tuple[int, int, str]] = []
    for path, text in rows:
        parsed = _parse_table_row(str(text))
        if not parsed:
            continue
        if any(not parsed.get(field, "").strip() for field in requested_fields):
            continue
        candidates.append((_diet_document_score(str(path)), len(str(path)), str(text)))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _diet_document_score(path: str) -> int:
    lowered = path.lower()
    score = 0
    if "diet" in lowered or "식단" in lowered:
        score += 4
    if "supplement" in lowered:
        score += 1
    if "14day" in lowered or "14days" in lowered:
        score += 1
    if lowered.endswith(".xlsx"):
        score += 1
    return score
