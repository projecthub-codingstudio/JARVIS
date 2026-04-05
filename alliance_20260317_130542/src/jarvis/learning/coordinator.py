"""LearningCoordinator — facade over capture, detect, extract, match, inject."""
from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from jarvis.learning.event_capture import SessionEventCapture
from jarvis.learning.hint_injector import merge_entities
from jarvis.learning.pattern_matcher import PatternMatcher
from jarvis.learning.pattern_extractor import PatternExtractor
from jarvis.learning.pattern_store import PatternStore
from jarvis.learning.reformulation_detector import ReformulationDetector


EmbedFn = Callable[[str], list[float]]
SimilarityFn = Callable[[str, str], float]


class LearningCoordinator:
    def __init__(
        self,
        *,
        store: PatternStore,
        embed_fn: EmbedFn,
        similarity_fn: SimilarityFn,
        now: Callable[[], int] = lambda: int(time.time()),
        min_pair_similarity: float = 0.5,
        min_match_similarity: float = 0.75,
        window_seconds: int = 300,
    ) -> None:
        self._store = store
        self._embed = embed_fn
        self._now = now
        self._capture = SessionEventCapture(store=store, now=now)
        self._detector = ReformulationDetector(
            similarity_fn=similarity_fn,
            min_similarity=min_pair_similarity,
            window_seconds=window_seconds,
        )
        self._extractor = PatternExtractor()
        self._matcher = PatternMatcher(
            embed_fn=embed_fn,
            min_similarity=min_match_similarity,
            top_k=3,
        )

    def record_outcome(
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
        now_override: int | None = None,
    ) -> None:
        now_fn = (lambda: now_override) if now_override is not None else self._now
        capture = SessionEventCapture(store=self._store, now=now_fn)
        capture.record(
            session_id=session_id, turn_id=turn_id, query_text=query_text,
            retrieval_task=retrieval_task, entities=entities,
            outcome=outcome, reason_code=reason_code,
            citation_paths=citation_paths, confidence=confidence,
        )

    def analyze_unanalyzed(self, *, before: int) -> int:
        events = self._store.get_unanalyzed_events(before=before)
        if not events:
            return 0

        by_session: dict[str, list] = {}
        for event in events:
            by_session.setdefault(event.session_id, []).append(event)

        patterns_created = 0
        analyzed_event_ids: list[str] = []
        for session_events in by_session.values():
            pairs = self._detector.find_pairs(session_events)
            for pair in pairs:
                pattern = self._extractor.extract(
                    pair,
                    pattern_id=f"pat-{uuid.uuid4().hex[:12]}",
                    now=self._now(),
                )
                if pattern is not None:
                    self._store.save_pattern(pattern)
                    patterns_created += 1
            analyzed_event_ids.extend(e.event_id for e in session_events)

        self._store.mark_analyzed(analyzed_event_ids, analyzed_at=self._now())
        return patterns_created

    def refresh_index(self) -> None:
        all_patterns = []
        for task in ("table_lookup", "document_qa", "code_lookup", "multi_doc_qa"):
            all_patterns.extend(self._store.get_patterns_by_task(task))

        entries = [(p, self._embed(p.canonical_query)) for p in all_patterns]
        self._matcher.index(entries)

    def find_hints(self, *, query: str, retrieval_task: str) -> dict[str, object] | None:
        matches = self._matcher.find(query, retrieval_task=retrieval_task)
        if not matches:
            return None
        top = matches[0]
        self._store.increment_pattern_usage(top.pattern.pattern_id, now=self._now())
        return dict(top.pattern.entity_hints)

    def inject_hints(
        self,
        *,
        query: str,
        retrieval_task: str,
        explicit_entities: dict[str, object],
    ) -> dict[str, object]:
        learned = self.find_hints(query=query, retrieval_task=retrieval_task)
        if learned is None:
            return dict(explicit_entities)
        return merge_entities(explicit=explicit_entities, learned=learned)
