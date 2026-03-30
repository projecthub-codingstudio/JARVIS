"""Tests for shared runtime context helpers."""
from __future__ import annotations

from pathlib import Path

from jarvis.app.runtime_context import (
    create_llm_backend,
    ensure_vector_index_ready,
    resolve_knowledge_base_path,
)
from jarvis.contracts import RuntimeDecision
from jarvis.core.error_monitor import ErrorMonitor
from jarvis.observability.metrics import MetricsCollector
from jarvis.runtime.model_router import ModelRouter


def _decision(*, backend: str = "mlx", model_id: str = "qwen3:14b") -> RuntimeDecision:
    return RuntimeDecision(
        tier="balanced",
        backend=backend,
        model_id=model_id,
        context_window=8192,
        max_retrieved_chunks=8,
        generation_timeout_ms=30_000,
        reasoning_enabled=True,
    )


class TestCreateLLMBackend:
    def test_forced_stub_model_skips_backend_loading(self, monkeypatch) -> None:
        def _unexpected_import(*args, **kwargs):
            raise AssertionError("backend load should be skipped for stub model")

        monkeypatch.setattr("jarvis.runtime.mlx_backend.mlx_import_probe", _unexpected_import)

        runtime = create_llm_backend(
            _decision(model_id="stub"),
            metrics=MetricsCollector(),
            error_monitor=ErrorMonitor(),
            allow_mlx=True,
        )

        assert runtime._model_id == "stub"
        assert runtime.status_detail == "forced stub backend"

    def test_skips_mlx_when_probe_fails(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "jarvis.runtime.mlx_backend.mlx_import_probe",
            lambda: (False, "mlx probe failed"),
        )
        # Also force LlamaCppBackend.load() to fail so we reach the stub
        import jarvis.runtime.llamacpp_backend as _lcpp

        monkeypatch.setattr(
            _lcpp.LlamaCppBackend,
            "load",
            lambda self, decision: (_ for _ in ()).throw(
                RuntimeError("ollama unavailable in test")
            ),
        )

        runtime = create_llm_backend(
            _decision(),
            metrics=MetricsCollector(),
            error_monitor=ErrorMonitor(),
            allow_mlx=True,
        )

        assert runtime._model_id == "stub"
        assert "MLX preflight failed" in runtime.status_detail
        assert "Ollama fallback failed" in runtime.status_detail

    def test_tracks_loaded_llm_in_model_router(self, monkeypatch) -> None:
        class FakeBackend:
            def __init__(self, *, model_router=None, estimated_memory_gb: float = 0.0) -> None:
                self.model_id = ""
                self._model_router = model_router
                self._estimated_memory_gb = estimated_memory_gb

            def load(self, decision) -> None:
                assert self._model_router is not None
                granted = self._model_router.request_load(decision.model_id, self._estimated_memory_gb)
                assert granted is True
                self.model_id = decision.model_id

            def unload(self) -> None:
                if self._model_router is not None and self.model_id:
                    self._model_router.release(self.model_id)
                    self.model_id = ""

        monkeypatch.setattr(
            "jarvis.runtime.mlx_backend.mlx_import_probe",
            lambda: (True, ""),
        )
        monkeypatch.setattr("jarvis.runtime.mlx_backend.MLXBackend", FakeBackend)

        router = ModelRouter(memory_limit_gb=16.0)
        runtime = create_llm_backend(
            _decision(model_id="qwen3.5:9b"),
            model_router=router,
            metrics=MetricsCollector(),
            error_monitor=ErrorMonitor(),
            allow_mlx=True,
        )

        assert router.active_model == "qwen3.5:9b"
        runtime.unload()
        assert router.active_model is None


class TestEnsureVectorIndexReady:
    def test_starts_background_backfill(self) -> None:
        import time
        events: list[str] = []

        class FakePipeline:
            def __init__(self) -> None:
                self.calls = 0

            def backfill_embeddings(self, *, batch_size: int) -> int:
                self.calls += 1
                assert batch_size == 64
                if self.calls <= 2:
                    return 12
                return 0

        pipeline = FakePipeline()
        ensure_vector_index_ready(
            pipeline=pipeline,
            vector_index=object(),
            chunk_count=24,
            reporter=events.append,
        )

        # Function returns immediately (no sync backfill)
        # Background thread runs
        time.sleep(0.2)
        assert pipeline.calls >= 1

    def test_skips_when_no_chunks(self) -> None:
        class FakePipeline:
            def __init__(self) -> None:
                self.called = False

            def backfill_embeddings(self, *, batch_size: int) -> int:
                self.called = True
                return 0

        pipeline = FakePipeline()
        ensure_vector_index_ready(
            pipeline=pipeline,
            vector_index=object(),
            chunk_count=0,
        )

        assert pipeline.called is False


class TestResolveKnowledgeBasePath:
    def test_prefers_explicit_candidate(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("JARVIS_KNOWLEDGE_BASE", str(tmp_path / "env-kb"))
        explicit = tmp_path / "explicit-kb"
        assert resolve_knowledge_base_path(explicit) == explicit.resolve()

    def test_uses_env_override(self, tmp_path: Path, monkeypatch) -> None:
        env_path = tmp_path / "env-kb"
        monkeypatch.setenv("JARVIS_KNOWLEDGE_BASE", str(env_path))
        assert resolve_knowledge_base_path() == env_path.resolve()

    def test_defaults_to_cwd_knowledge_base(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_KNOWLEDGE_BASE", raising=False)
        monkeypatch.chdir(tmp_path)
        assert resolve_knowledge_base_path() == (tmp_path / "knowledge_base").resolve()
