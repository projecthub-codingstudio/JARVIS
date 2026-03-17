"""ConversationStore — persistent conversation history via SQLite."""
from __future__ import annotations

import sqlite3

from jarvis.contracts import ConversationTurn


class ConversationStore:
    """Conversation history storage. SQLite when db provided, in-memory otherwise."""

    def __init__(self, *, db: sqlite3.Connection | None = None) -> None:
        self._db = db
        self._turns: list[ConversationTurn] = []

    def save_turn(self, turn: ConversationTurn) -> None:
        self._turns.append(turn)
        if self._db is not None:
            self._db.execute(
                "INSERT OR REPLACE INTO conversation_turns"
                " (turn_id, user_input, assistant_output, has_evidence, created_at, completed_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    turn.turn_id,
                    turn.user_input,
                    turn.assistant_output,
                    1 if turn.has_evidence else 0,
                    turn.created_at.isoformat() if turn.created_at else None,
                    turn.completed_at.isoformat() if turn.completed_at else None,
                ),
            )
            self._db.commit()

    def get_recent_turns(self, limit: int = 10) -> list[ConversationTurn]:
        if self._db is not None:
            rows = self._db.execute(
                "SELECT turn_id, user_input, assistant_output, has_evidence, created_at"
                " FROM conversation_turns ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            turns = []
            for row in reversed(rows):  # reverse to chronological order
                turns.append(ConversationTurn(
                    turn_id=row[0],
                    user_input=row[1],
                    assistant_output=row[2],
                    has_evidence=bool(row[3]),
                ))
            return turns
        return self._turns[-limit:]
