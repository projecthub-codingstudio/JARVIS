"""TaskLogStore — persistent task log storage for observability."""
from __future__ import annotations

import json
import sqlite3

from jarvis.contracts import TaskLogEntry, TaskStatus


class TaskLogStore:
    """Task log storage. SQLite when db provided, in-memory otherwise."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db
        self._entries: list[TaskLogEntry] = []

    def log_entry(self, entry: TaskLogEntry) -> None:
        self._entries.append(entry)
        if self._db is not None:
            self._db.execute(
                "INSERT INTO task_logs"
                " (entry_id, turn_id, stage, status, error_code, duration_ms, metadata)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.entry_id,
                    entry.turn_id,
                    entry.stage,
                    entry.status.value,
                    entry.error_code,
                    entry.duration_ms,
                    json.dumps(entry.metadata, default=str),
                ),
            )
            self._db.commit()

    def get_entries_for_turn(self, turn_id: str) -> list[TaskLogEntry]:
        if self._db is not None:
            rows = self._db.execute(
                "SELECT entry_id, turn_id, stage, status, error_code, duration_ms, metadata"
                " FROM task_logs WHERE turn_id = ? ORDER BY created_at",
                (turn_id,),
            ).fetchall()
            return [
                TaskLogEntry(
                    entry_id=r[0],
                    turn_id=r[1],
                    stage=r[2],
                    status=TaskStatus(r[3]),
                    error_code=r[4],
                    duration_ms=r[5],
                    metadata=json.loads(r[6]) if r[6] else {},
                )
                for r in rows
            ]
        return [e for e in self._entries if e.turn_id == turn_id]
