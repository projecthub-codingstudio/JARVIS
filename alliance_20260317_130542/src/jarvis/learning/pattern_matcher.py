"""PatternMatcher — in-memory cosine-similarity index over learned patterns."""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.learning.learned_pattern import LearnedPattern


EmbedFn = Callable[[str], list[float]]


@dataclass(frozen=True)
class PatternMatch:
    pattern: LearnedPattern
    score: float


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class PatternMatcher:
    def __init__(
        self,
        *,
        embed_fn: EmbedFn,
        min_similarity: float = 0.75,
        top_k: int = 3,
    ) -> None:
        self._embed = embed_fn
        self._min_sim = min_similarity
        self._top_k = top_k
        self._entries: list[tuple[LearnedPattern, list[float]]] = []

    def index(self, entries: list[tuple[LearnedPattern, list[float]]]) -> None:
        self._entries = list(entries)

    def add(self, pattern: LearnedPattern, embedding: list[float]) -> None:
        self._entries.append((pattern, embedding))

    def find(self, query: str, *, retrieval_task: str) -> list[PatternMatch]:
        query_emb = self._embed(query)
        scored: list[PatternMatch] = []
        for pattern, emb in self._entries:
            if pattern.retrieval_task != retrieval_task:
                continue
            score = _cosine(query_emb, emb)
            if score < self._min_sim:
                continue
            scored.append(PatternMatch(pattern=pattern, score=score))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[: self._top_k]
