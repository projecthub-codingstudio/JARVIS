"""SessionEvent — one captured query outcome. ReformulationPair — failure+success."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SessionEvent:
    event_id: str
    session_id: str
    turn_id: str
    query_text: str
    retrieval_task: str
    entities: dict[str, object]
    outcome: str  # "answer" | "abstain" | "clarify"
    reason_code: str
    citation_paths: list[str]
    confidence: float
    created_at: int

    def to_row(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "query_text": self.query_text,
            "retrieval_task": self.retrieval_task,
            "entities_json": json.dumps(self.entities, ensure_ascii=False),
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "citation_paths": json.dumps(self.citation_paths, ensure_ascii=False),
            "confidence": self.confidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, object]) -> "SessionEvent":
        return cls(
            event_id=str(row["event_id"]),
            session_id=str(row["session_id"]),
            turn_id=str(row["turn_id"]),
            query_text=str(row["query_text"]),
            retrieval_task=str(row["retrieval_task"] or ""),
            entities=json.loads(str(row.get("entities_json") or "{}")),
            outcome=str(row["outcome"]),
            reason_code=str(row.get("reason_code") or ""),
            citation_paths=json.loads(str(row.get("citation_paths") or "[]")),
            confidence=float(row.get("confidence") or 0.0),
            created_at=int(row["created_at"]),
        )


@dataclass(frozen=True)
class ReformulationPair:
    failure: SessionEvent
    success: SessionEvent
    similarity: float

    @property
    def delta_seconds(self) -> int:
        return self.success.created_at - self.failure.created_at
