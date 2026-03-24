"""Tests for local TTS runtime."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.tts_runtime import LocalTTSRuntime


class TestLocalTTSRuntime:
    def test_writes_text_fallback_for_txt_output(self, tmp_path: Path) -> None:
        runtime = LocalTTSRuntime()
        output = tmp_path / "response.txt"
        result = runtime.synthesize("음성 응답 테스트", output)
        assert result == output
        assert output.read_text(encoding="utf-8") == "음성 응답 테스트"

    def test_rejects_empty_text(self, tmp_path: Path) -> None:
        runtime = LocalTTSRuntime()
        with pytest.raises(RuntimeError):
            runtime.synthesize("   ", tmp_path / "empty.txt")

    def test_model_router_load_and_release(self, tmp_path: Path) -> None:
        router = ModelRouter(memory_limit_gb=16.0)
        runtime = LocalTTSRuntime(model_router=router)
        output = tmp_path / "tts.txt"
        runtime.synthesize("router tts", output)
        assert router.active_model is None

    def test_prepare_text_for_say_expands_code_tokens(self) -> None:
        runtime = LocalTTSRuntime()

        prepared = runtime._prepare_text_for_say("파이프라인 클래스 Pipeline.py 와 ProviderResult 를 설명해줘")

        assert "파이프라인 dot p y" in prepared
        assert "Provider Result" in prepared
