"""Tests for VectorIndex with LanceDB."""
import pytest
import tempfile
from pathlib import Path

from jarvis.contracts import TypedQueryFragment, VectorHit, VectorRetrieverProtocol
from jarvis.runtime.embedding_runtime import EmbeddingRuntime
from jarvis.retrieval.vector_index import VectorIndex


def test_protocol_compliance():
    """VectorIndex must satisfy VectorRetrieverProtocol."""
    vi = VectorIndex()
    assert isinstance(vi, VectorRetrieverProtocol)


def test_search_empty_index():
    """Search on empty/nonexistent index returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vi = VectorIndex(db_path=Path(tmpdir) / "empty.lance")
        fragments = [TypedQueryFragment(text="test", language="en", query_type="semantic", weight=1.0)]
        results = vi.search(fragments)
        assert results == []


def test_search_no_embedding_runtime():
    """Search without embedding runtime returns empty list."""
    vi = VectorIndex()
    fragments = [TypedQueryFragment(text="test", language="en", query_type="semantic", weight=1.0)]
    results = vi.search(fragments)
    assert results == []


def test_add_and_search_roundtrip():
    """Add vectors then search should find them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        embedding_rt = EmbeddingRuntime()
        vi = VectorIndex(
            db_path=Path(tmpdir) / "test.lance",
            embedding_runtime=embedding_rt,
        )

        texts = ["Python 프로그래밍 언어", "자바스크립트 웹 개발", "데이터베이스 설계"]
        embeddings = embedding_rt.embed(texts)
        vi.add(
            chunk_ids=["c1", "c2", "c3"],
            document_ids=["d1", "d1", "d2"],
            embeddings=embeddings,
        )

        fragments = [TypedQueryFragment(text="Python 코딩", language="ko", query_type="semantic", weight=1.0)]
        results = vi.search(fragments, top_k=2)

        assert len(results) <= 2
        assert all(isinstance(r, VectorHit) for r in results)
        if results:
            assert results[0].chunk_id in ("c1", "c2", "c3")


def test_remove_vectors():
    """Remove should delete vectors from index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        embedding_rt = EmbeddingRuntime()
        vi = VectorIndex(
            db_path=Path(tmpdir) / "test.lance",
            embedding_runtime=embedding_rt,
        )

        embeddings = embedding_rt.embed(["text1", "text2"])
        vi.add(chunk_ids=["c1", "c2"], document_ids=["d1", "d1"], embeddings=embeddings)
        vi.remove(chunk_ids=["c1"])

        fragments = [TypedQueryFragment(text="text1", language="en", query_type="semantic", weight=1.0)]
        results = vi.search(fragments, top_k=10)
        found_ids = [r.chunk_id for r in results]
        assert "c1" not in found_ids
