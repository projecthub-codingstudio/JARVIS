"""PatternStore — SQLite-backed persistence for session events and learned patterns."""
from __future__ import annotations

import sqlite3
from typing import Iterable

from jarvis.learning.session_event import SessionEvent
from jarvis.learning.learned_pattern import LearnedPattern


class PatternStore:
    def __init__(self, *, db: sqlite3.Connection) -> None:
        self._db = db
        self._db.row_factory = sqlite3.Row

    # ---- events ----
    def save_event(self, event: SessionEvent) -> None:
        row = event.to_row()
        self._db.execute(
            "INSERT OR REPLACE INTO session_events "
            "(event_id, session_id, turn_id, query_text, retrieval_task, entities_json, "
            " outcome, reason_code, citation_paths, confidence, created_at, analyzed_at) "
            "VALUES (:event_id, :session_id, :turn_id, :query_text, :retrieval_task, :entities_json, "
            " :outcome, :reason_code, :citation_paths, :confidence, :created_at, NULL)",
            row,
        )
        self._db.commit()

    def get_session_events(self, session_id: str) -> list[SessionEvent]:
        rows = self._db.execute(
            "SELECT * FROM session_events WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
        return [SessionEvent.from_row(dict(r)) for r in rows]

    def get_unanalyzed_events(self, *, before: int) -> list[SessionEvent]:
        rows = self._db.execute(
            "SELECT * FROM session_events WHERE analyzed_at IS NULL AND created_at <= ? "
            "ORDER BY session_id, created_at",
            (before,),
        ).fetchall()
        return [SessionEvent.from_row(dict(r)) for r in rows]

    def mark_analyzed(self, event_ids: Iterable[str], *, analyzed_at: int) -> None:
        ids = list(event_ids)
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        self._db.execute(
            f"UPDATE session_events SET analyzed_at = ? WHERE event_id IN ({placeholders})",
            (analyzed_at, *ids),
        )
        self._db.commit()

    # ---- patterns ----
    def save_pattern(self, pattern: LearnedPattern) -> None:
        row = pattern.to_row()
        self._db.execute(
            "INSERT OR REPLACE INTO learned_patterns "
            "(pattern_id, canonical_query, failed_variants, retrieval_task, entity_hints_json, "
            " reformulation_type, success_count, citation_paths, created_at, last_used_at) "
            "VALUES (:pattern_id, :canonical_query, :failed_variants, :retrieval_task, :entity_hints_json, "
            " :reformulation_type, :success_count, :citation_paths, :created_at, :last_used_at)",
            row,
        )
        self._db.commit()

    def get_pattern(self, pattern_id: str) -> LearnedPattern | None:
        row = self._db.execute(
            "SELECT * FROM learned_patterns WHERE pattern_id = ?", (pattern_id,)
        ).fetchone()
        return LearnedPattern.from_row(dict(row)) if row else None

    def get_patterns_by_task(self, retrieval_task: str) -> list[LearnedPattern]:
        rows = self._db.execute(
            "SELECT * FROM learned_patterns WHERE retrieval_task = ? ORDER BY success_count DESC",
            (retrieval_task,),
        ).fetchall()
        return [LearnedPattern.from_row(dict(r)) for r in rows]

    def increment_pattern_usage(self, pattern_id: str, *, now: int) -> None:
        self._db.execute(
            "UPDATE learned_patterns SET success_count = success_count + 1, last_used_at = ? "
            "WHERE pattern_id = ?",
            (now, pattern_id),
        )
        self._db.commit()
