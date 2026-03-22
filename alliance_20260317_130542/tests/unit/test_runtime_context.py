"""Tests for shared runtime context helpers."""
from __future__ import annotations

from jarvis.app.runtime_context import create_llm_backend, ensure_vector_index_ready
from jarvis.contracts import RuntimeDecision
from jarvis.core.error_monitor import ErrorMonitor
from jarvis.observability.metrics import MetricsCollector


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


class TestEnsureVectorIndexReady:
    def test_backfills_one_batch_when_table_missing(self) -> None:
        events: list[str] = []

        class FakePipeline:
            def __init__(self) -> None:
                self.calls = 0

            def backfill_embeddings(self, *, batch_size: int) -> int:
                self.calls += 1
                assert batch_size == 32
                return 12

        class FakeVectorIndex:
            def _get_table(self) -> object | None:
                return None

        pipeline = FakePipeline()
        ensure_vector_index_ready(
            pipeline=pipeline,
            vector_index=FakeVectorIndex(),
            chunk_count=24,
            reporter=events.append,
        )

        assert pipeline.calls == 1
        assert events == ["   [embeddings] initialized LanceDB table (12 chunks)"]

    def test_skips_when_table_already_exists(self) -> None:
        class FakePipeline:
            def __init__(self) -> None:
                self.called = False

            def backfill_embeddings(self, *, batch_size: int) -> int:
                self.called = True
                return 99

        class FakeVectorIndex:
            def _get_table(self) -> object:
                return object()

        pipeline = FakePipeline()
        ensure_vector_index_ready(
            pipeline=pipeline,
            vector_index=FakeVectorIndex(),
            chunk_count=24,
        )

        assert pipeline.called is False
