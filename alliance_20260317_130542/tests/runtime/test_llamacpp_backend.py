"""Tests for Ollama-backed llama.cpp compatibility runtime."""
from __future__ import annotations

from types import SimpleNamespace

from jarvis.contracts import RuntimeDecision
from jarvis.runtime.llamacpp_backend import LlamaCppBackend


def _decision(model_id: str = "qwen3:14b") -> RuntimeDecision:
    return RuntimeDecision(
        tier="balanced",
        backend="llamacpp",
        model_id=model_id,
        context_window=8192,
        max_retrieved_chunks=8,
        generation_timeout_ms=30_000,
        reasoning_enabled=False,
    )


class TestLlamaCppBackend:
    def test_load_starts_server_when_needed(self, monkeypatch) -> None:
        backend = LlamaCppBackend()
        calls = {"reachable": 0}

        monkeypatch.setattr(backend, "_resolve_binary", lambda: "/usr/local/bin/ollama")

        def fake_reachable() -> bool:
            calls["reachable"] += 1
            return calls["reachable"] >= 2

        monkeypatch.setattr(backend, "_server_reachable", fake_reachable)
        monkeypatch.setattr(backend, "_check_model_available", lambda model_tag: model_tag == "qwen3:14b")
        monkeypatch.setattr(
            "jarvis.runtime.llamacpp_backend.subprocess.Popen",
            lambda *args, **kwargs: SimpleNamespace(poll=lambda: None),
        )
        monkeypatch.setattr("jarvis.runtime.llamacpp_backend.time.sleep", lambda _: None)

        backend.load(_decision())

        assert backend.is_loaded is True
        assert backend.model_id == "qwen3:14b"
        assert backend.status_detail == "OK (qwen3:14b)"

    def test_load_reports_missing_binary(self, monkeypatch) -> None:
        backend = LlamaCppBackend()
        monkeypatch.setattr(backend, "_server_reachable", lambda: False)
        monkeypatch.setattr(backend, "_resolve_binary", lambda: None)

        try:
            backend.load(_decision())
        except RuntimeError as exc:
            assert "Ollama binary not found" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
