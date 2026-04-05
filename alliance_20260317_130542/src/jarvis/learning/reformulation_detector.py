"""ReformulationDetector — find in-session failure→success pairs."""
from __future__ import annotations

from collections.abc import Callable

from jarvis.learning.session_event import SessionEvent, ReformulationPair


SimilarityFn = Callable[[str, str], float]


class ReformulationDetector:
    def __init__(
        self,
        *,
        similarity_fn: SimilarityFn,
        min_similarity: float = 0.5,
        window_seconds: int = 300,
    ) -> None:
        self._similarity = similarity_fn
        self._min_sim = min_similarity
        self._window = window_seconds

    def find_pairs(self, events: list[SessionEvent]) -> list[ReformulationPair]:
        ordered = sorted(events, key=lambda e: e.created_at)
        pairs: list[ReformulationPair] = []

        for i, failure in enumerate(ordered):
            if failure.outcome not in ("abstain", "clarify"):
                continue
            for j in range(i + 1, len(ordered)):
                candidate = ordered[j]
                if candidate.created_at - failure.created_at > self._window:
                    break
                if candidate.outcome != "answer":
                    continue
                sim = self._similarity(failure.query_text, candidate.query_text)
                if sim >= self._min_sim:
                    pairs.append(ReformulationPair(
                        failure=failure, success=candidate, similarity=sim,
                    ))
                    break
        return pairs
