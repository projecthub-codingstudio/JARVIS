from __future__ import annotations

from jarvis.learning.embedding_adapter import BgeM3Adapter


class _FakeRuntime:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t))] * 4 for t in texts]


def test_adapter_embed_returns_list() -> None:
    adapter = BgeM3Adapter(runtime=_FakeRuntime())
    emb = adapter.embed("hello")
    assert emb == [5.0, 5.0, 5.0, 5.0]


def test_adapter_similarity_computes_cosine() -> None:
    adapter = BgeM3Adapter(runtime=_FakeRuntime())
    sim = adapter.similarity("abc", "abc")
    assert abs(sim - 1.0) < 1e-6


def test_adapter_similarity_zero_vector_returns_zero() -> None:
    class ZeroRuntime:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0, 0.0] for _ in texts]

    adapter = BgeM3Adapter(runtime=ZeroRuntime())
    assert adapter.similarity("a", "b") == 0.0
