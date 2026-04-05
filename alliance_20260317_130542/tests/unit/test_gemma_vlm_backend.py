"""Tests for GemmaVlmBackend — model loading, generation, unload lifecycle."""

from __future__ import annotations

import pytest

from jarvis.contracts import LLMBackendProtocol, RuntimeDecision
from jarvis.runtime.gemma_vlm_backend import (
    GemmaVlmBackend,
    _resolve_model_id,
    is_gemma_vlm_model,
)


def test_resolve_model_id_alias_mapping() -> None:
    assert _resolve_model_id("gemma4:e2b") == "mlx-community/gemma-4-E2B-it-4bit"
    assert _resolve_model_id("gemma4:e4b") == "mlx-community/gemma-4-E4B-it-4bit"
    assert _resolve_model_id("gemma-4-e4b") == "mlx-community/gemma-4-E4B-it-4bit"


def test_resolve_model_id_passthrough_unknown() -> None:
    assert _resolve_model_id("some/custom/repo") == "some/custom/repo"


def test_is_gemma_vlm_model_detection() -> None:
    assert is_gemma_vlm_model("gemma4:e4b") is True
    assert is_gemma_vlm_model("gemma4:e2b") is True
    assert is_gemma_vlm_model("mlx-community/gemma-4-E4B-it-4bit") is True
    assert is_gemma_vlm_model("exaone3.5:7.8b") is False
    assert is_gemma_vlm_model("qwen3.5:9b") is False


def test_backend_satisfies_protocol() -> None:
    backend = GemmaVlmBackend()
    assert isinstance(backend, LLMBackendProtocol)


def test_backend_initial_state() -> None:
    backend = GemmaVlmBackend()
    assert backend.is_loaded is False
    assert backend.model_id == ""


def test_generate_raises_when_no_model_loaded() -> None:
    backend = GemmaVlmBackend()
    with pytest.raises(RuntimeError, match="No Gemma model loaded"):
        backend.generate("test prompt", "context", "read_only")


def test_unload_is_noop_when_nothing_loaded() -> None:
    backend = GemmaVlmBackend()
    # Should not raise
    backend.unload()
    assert backend.is_loaded is False


def test_load_with_mocked_mlx_vlm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify load() uses mlx_vlm correctly without actually downloading."""
    fake_model = object()
    fake_processor = object()
    fake_config = object()
    calls: dict[str, object] = {}

    def fake_load(repo_id: str) -> tuple[object, object]:
        calls["load_repo"] = repo_id
        return fake_model, fake_processor

    def fake_load_config(repo_id: str) -> object:
        calls["config_repo"] = repo_id
        return fake_config

    import mlx_vlm
    import mlx_vlm.utils
    monkeypatch.setattr(mlx_vlm, "load", fake_load)
    monkeypatch.setattr(mlx_vlm.utils, "load_config", fake_load_config)

    backend = GemmaVlmBackend()
    decision = RuntimeDecision(
        tier="balanced",
        backend="mlx",
        model_id="gemma4:e4b",
        context_window=8192,
    )
    backend.load(decision)

    assert backend.is_loaded is True
    assert backend.model_id == "mlx-community/gemma-4-E4B-it-4bit"
    assert calls["load_repo"] == "mlx-community/gemma-4-E4B-it-4bit"
    assert calls["config_repo"] == "mlx-community/gemma-4-E4B-it-4bit"


def test_load_skips_when_same_model_already_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    load_count = 0

    def fake_load(repo_id: str) -> tuple[object, object]:
        nonlocal load_count
        load_count += 1
        return object(), object()

    import mlx_vlm
    import mlx_vlm.utils
    monkeypatch.setattr(mlx_vlm, "load", fake_load)
    monkeypatch.setattr(mlx_vlm.utils, "load_config", lambda _: object())

    backend = GemmaVlmBackend()
    decision = RuntimeDecision(
        tier="balanced", backend="mlx", model_id="gemma4:e4b", context_window=8192,
    )
    backend.load(decision)
    backend.load(decision)  # Second call should be no-op

    assert load_count == 1


def test_unload_clears_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import mlx_vlm
    import mlx_vlm.utils
    monkeypatch.setattr(mlx_vlm, "load", lambda _: (object(), object()))
    monkeypatch.setattr(mlx_vlm.utils, "load_config", lambda _: object())

    backend = GemmaVlmBackend()
    decision = RuntimeDecision(
        tier="balanced", backend="mlx", model_id="gemma4:e4b", context_window=8192,
    )
    backend.load(decision)
    assert backend.is_loaded is True

    backend.unload()
    assert backend.is_loaded is False
    assert backend.model_id == ""
