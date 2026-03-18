"""Tests for EmbeddingRuntime with BGE-M3."""
import pytest
from jarvis.runtime.embedding_runtime import EmbeddingRuntime
from jarvis.contracts import EmbeddingRuntimeProtocol


def test_protocol_compliance():
    """EmbeddingRuntime must satisfy EmbeddingRuntimeProtocol."""
    rt = EmbeddingRuntime()
    assert isinstance(rt, EmbeddingRuntimeProtocol)


def test_embed_returns_correct_shape():
    """embed() must return list[list[float]] with 1024 dimensions."""
    rt = EmbeddingRuntime()
    texts = ["hello world", "테스트 한국어"]
    result = rt.embed(texts)
    assert isinstance(result, list)
    assert len(result) == 2
    assert all(isinstance(v, list) for v in result)
    assert all(len(v) == 1024 for v in result)
    assert all(isinstance(x, float) for v in result for x in v)


def test_embed_empty_input():
    """embed([]) must return []."""
    rt = EmbeddingRuntime()
    assert rt.embed([]) == []


def test_embed_single_text():
    """embed() works with a single text."""
    rt = EmbeddingRuntime()
    result = rt.embed(["test"])
    assert len(result) == 1
    assert len(result[0]) == 1024


def test_load_unload_lifecycle():
    """load/unload cycle should not crash."""
    rt = EmbeddingRuntime()
    rt.load_model()
    result = rt.embed(["test"])
    assert len(result) == 1
    rt.unload_model()
    assert not rt.is_loaded
