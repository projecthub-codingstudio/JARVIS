"""Tests for local TTS runtime."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.tts_runtime import (
    LocalTTSRuntime,
    _qwen3_language_for_text,
    _qwen3_speaker_for_text,
)
from jarvis.runtime.voice_persona import JARVIS_PERSONA


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

    def test_select_voice_prefers_male_reed_for_korean(self) -> None:
        runtime = LocalTTSRuntime()

        voice = runtime._select_voice("안녕하세요. 시스템 상태를 보고드립니다.")

        assert voice == JARVIS_PERSONA.macos_voice_ko
        assert voice == "Reed (한국어(대한민국))"

    def test_select_voice_prefers_british_male_reed_for_english(self) -> None:
        runtime = LocalTTSRuntime()

        voice = runtime._select_voice("System check complete. Awaiting your instruction.")

        assert voice == JARVIS_PERSONA.macos_voice_en
        assert voice == "Reed (영어(영국))"

    def test_qwen_language_detection_prefers_korean_for_hangul_text(self) -> None:
        assert _qwen3_language_for_text("안녕하세요. 시스템 점검을 시작합니다.") == "Korean"

    def test_qwen_speaker_defaults_to_male_english_voice(self) -> None:
        assert _qwen3_speaker_for_text("System status report.") == "Ryan"

    def test_qwen_backend_short_circuits_when_monkeypatched(self, monkeypatch, tmp_path: Path) -> None:
        written = tmp_path / "tts.wav"

        def fake_qwen(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            output_path.write_bytes(b"RIFF")
            return output_path

        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_synthesize", fake_qwen)
        runtime = LocalTTSRuntime(backend="qwen3")

        result = runtime.synthesize("JARVIS online", written)

        assert result == written
        assert written.read_bytes() == b"RIFF"
