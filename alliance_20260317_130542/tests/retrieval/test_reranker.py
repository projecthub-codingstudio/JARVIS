from __future__ import annotations

from jarvis.contracts import HybridSearchResult
from jarvis.retrieval.reranker import Reranker


class _CapturingModel:
    def __init__(self) -> None:
        self.last_pairs: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]], batch_size: int = 16) -> list[float]:
        self.last_pairs = list(pairs)
        return [0.5 for _ in pairs]


def test_reranker_does_not_apply_naive_512_char_truncation() -> None:
    reranker = Reranker()
    model = _CapturingModel()
    reranker._ensure_model = lambda: model  # type: ignore[method-assign]

    long_passage = "가나다라" * 300
    results = [
        HybridSearchResult(
            chunk_id="chunk-1",
            document_id="doc-1",
            rrf_score=0.1,
            snippet="",
        )
    ]

    reranker.rerank(
        "한글 문서 구조 설명",
        results,
        top_k=1,
        chunk_texts={"chunk-1": long_passage},
    )

    assert model.last_pairs
    assert model.last_pairs[0][1] == long_passage


def test_reranker_returns_original_order_when_model_unavailable() -> None:
    reranker = Reranker()
    reranker._ensure_model = lambda: None  # type: ignore[method-assign]

    results = [
        HybridSearchResult(chunk_id="a", document_id="doc", rrf_score=1.0, snippet="a"),
        HybridSearchResult(chunk_id="b", document_id="doc", rrf_score=0.5, snippet="b"),
    ]

    reranked = reranker.rerank("test", results, top_k=2)

    assert [item.chunk_id for item in reranked] == ["a", "b"]
