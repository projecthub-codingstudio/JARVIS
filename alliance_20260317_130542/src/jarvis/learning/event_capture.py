"""SessionEventCapture — converts orchestrator outputs into SessionEvent rows."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from jarvis.learning.pattern_store import PatternStore
from jarvis.learning.session_event import SessionEvent


class SessionEventCapture:
    def __init__(
        self,
        *,
        store: PatternStore,
        now: Callable[[], int] = lambda: int(time.time()),
    ) -> None:
        self._store = store
        self._now = now

    def record(
        self,
        *,
        session_id: str,
        turn_id: str,
        query_text: str,
        retrieval_task: str,
        entities: dict[str, object],
        outcome: str,
        reason_code: str,
        citation_paths: list[str],
        confidence: float,
    ) -> None:
        event = SessionEvent(
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            session_id=session_id,
            turn_id=turn_id,
            query_text=query_text,
            retrieval_task=retrieval_task,
            entities=entities,
            outcome=outcome,
            reason_code=reason_code,
            citation_paths=list(citation_paths),
            confidence=confidence,
            created_at=self._now(),
        )
        self._store.save_event(event)
