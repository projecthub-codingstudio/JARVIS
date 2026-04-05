"""BgeM3Adapter — wraps EmbeddingRuntime to provide embed_fn and similarity_fn."""
from __future__ import annotations

import math
from typing import Protocol


class _EmbeddingRuntimeLike(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class BgeM3Adapter:
    def __init__(self, *, runtime: _EmbeddingRuntimeLike) -> None:
        self._runtime = runtime

    def embed(self, text: str) -> list[float]:
        result = self._runtime.embed([text])
        return result[0] if result else []

    def similarity(self, a: str, b: str) -> float:
        vectors = self._runtime.embed([a, b])
        if len(vectors) != 2:
            return 0.0
        return self._cosine(vectors[0], vectors[1])

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)
