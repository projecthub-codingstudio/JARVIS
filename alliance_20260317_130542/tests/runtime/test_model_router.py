"""Tests for ModelRouter."""
from __future__ import annotations

from jarvis.runtime.model_router import ModelRouter


class TestModelRouter:
    def test_allows_model_within_budget(self) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        assert router.request_load("llm-a", 8.0) is True
        assert router.active_model == "llm-a"
        assert router.active_memory_gb == 8.0

    def test_rejects_model_over_budget(self) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        assert router.request_load("too-big", 20.0) is False
        assert router.active_model is None

    def test_switches_active_model(self) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        assert router.request_load("stt", 2.0) is True
        assert router.request_load("llm", 10.0) is True
        assert router.active_model == "llm"
        assert router.active_memory_gb == 10.0

    def test_release_clears_matching_model(self) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        router.request_load("tts", 3.0)
        router.release("tts")
        assert router.active_model is None
        assert router.active_memory_gb == 0.0

    def test_release_non_active_model_is_noop(self) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        router.request_load("llm", 9.0)
        router.release("other")
        assert router.active_model == "llm"
