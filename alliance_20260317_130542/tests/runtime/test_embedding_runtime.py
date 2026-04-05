"""Tests for EmbeddingRuntime with BGE-M3."""
from pathlib import Path

import pytest
from jarvis.runtime.embedding_runtime import EmbeddingRuntime, _resolve_local_model_path
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


def test_default_device_uses_cpu(monkeypatch):
    monkeypatch.delenv("JARVIS_EMBEDDING_DEVICE", raising=False)
    rt = EmbeddingRuntime()
    assert rt._device == "cpu"


def test_env_device_override(monkeypatch):
    monkeypatch.setenv("JARVIS_EMBEDDING_DEVICE", "mps")
    rt = EmbeddingRuntime()
    assert rt._device == "mps"


def test_resolve_local_model_path_prefers_complete_snapshot(tmp_path, monkeypatch):
    cache_root = tmp_path / ".cache" / "huggingface" / "hub"
    snapshot_root = cache_root / "models--BAAI--bge-m3" / "snapshots"
    incomplete = snapshot_root / "older"
    complete = snapshot_root / "newer"
    incomplete.mkdir(parents=True)
    complete.mkdir(parents=True)
    (complete / "config.json").write_text("{}", encoding="utf-8")
    (complete / "modules.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    assert _resolve_local_model_path("BAAI/bge-m3") == str(complete)


def test_resolve_local_model_path_returns_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert _resolve_local_model_path("BAAI/bge-m3") is None
