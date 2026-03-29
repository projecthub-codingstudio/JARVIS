"""Tests for MLX backend preflight caching."""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from jarvis.runtime import mlx_backend


class TestMLXImportProbeCache:
    def test_reads_recent_failure_cache(self, monkeypatch, tmp_path: Path) -> None:
        cache_path = tmp_path / "mlx-probe.json"
        cache_path.write_text(
            json.dumps({
                "ok": False,
                "detail": "cached failure",
                "timestamp": mlx_backend.time.time(),
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(mlx_backend, "_MLX_PROBE_CACHE", cache_path)

        result = mlx_backend._read_probe_cache()

        assert result == (False, "cached failure")

    def test_ignores_expired_cache(self, monkeypatch, tmp_path: Path) -> None:
        cache_path = tmp_path / "mlx-probe.json"
        cache_path.write_text(
            json.dumps({
                "ok": False,
                "detail": "expired failure",
                "timestamp": mlx_backend.time.time() - (mlx_backend._MLX_PROBE_TTL_SECONDS + 5),
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(mlx_backend, "_MLX_PROBE_CACHE", cache_path)

        assert mlx_backend._read_probe_cache() is None


class TestMLXBackendGenerate:
    def test_uses_sampler_based_generate_api(self, monkeypatch) -> None:
        calls: dict[str, object] = {}

        class FakeTokenizer:
            def apply_chat_template(self, messages, add_generation_prompt=True):
                calls["messages"] = messages
                return "formatted"

            def encode(self, text):
                # Simulate ~100 tokens for the formatted prompt
                return list(range(100))

        fake_mlx_lm = types.ModuleType("mlx_lm")
        fake_sample_utils = types.ModuleType("mlx_lm.sample_utils")

        def fake_make_sampler(temp, top_p, min_p, min_tokens_to_keep):
            calls["sampler_args"] = (temp, top_p, min_p, min_tokens_to_keep)
            return "sampler"

        def fake_generate(model, tokenizer, *, prompt, max_tokens, sampler):
            calls["generate_args"] = {
                "model": model,
                "tokenizer": tokenizer,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "sampler": sampler,
            }
            return "generated response"

        fake_mlx_lm.generate = fake_generate
        fake_sample_utils.make_sampler = fake_make_sampler
        monkeypatch.setitem(sys.modules, "mlx_lm", fake_mlx_lm)
        monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", fake_sample_utils)

        backend = mlx_backend.MLXBackend()
        backend._model = object()
        backend._tokenizer = FakeTokenizer()
        backend._model_id = "mlx-community/Qwen3-14B-4bit"

        result = backend.generate("질문", "문맥", "read_only")

        assert result == "generated response"
        assert calls["sampler_args"] == (0.7, 0.9, 0.0, 1)
        # Dynamic: context_window(8192) - prompt_tokens(100) - reserve(256) = 7836
        assert calls["generate_args"] == {
            "model": backend._model,
            "tokenizer": backend._tokenizer,
            "prompt": "formatted",
            "max_tokens": 7836,
            "sampler": "sampler",
        }
