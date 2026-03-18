"""Tests for whisper.cpp STT runtime wrapper."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.stt_runtime import WhisperCppSTT


class TestWhisperCppSTT:
    def test_uses_text_input_directly_for_test_mode(self, tmp_path: Path) -> None:
        transcript = tmp_path / "sample.txt"
        transcript.write_text("음성 테스트 전사", encoding="utf-8")

        runtime = WhisperCppSTT()
        assert runtime.transcribe(transcript) == "음성 테스트 전사"

    def test_uses_sidecar_transcript_when_present(self, tmp_path: Path) -> None:
        audio = tmp_path / "sample.wav"
        audio.write_bytes(b"RIFF")
        sidecar = tmp_path / "sample.txt"
        sidecar.write_text("sidecar transcript", encoding="utf-8")

        runtime = WhisperCppSTT()
        assert runtime.transcribe(audio) == "sidecar transcript"

    def test_missing_binary_without_sidecar_raises(self, tmp_path: Path) -> None:
        audio = tmp_path / "sample.wav"
        audio.write_bytes(b"RIFF")
        runtime = WhisperCppSTT(binary_path="/nonexistent/whisper-cli")

        with pytest.raises(RuntimeError):
            runtime.transcribe(audio)

    def test_model_router_load_and_release(self, tmp_path: Path) -> None:
        audio = tmp_path / "sample.txt"
        audio.write_text("router transcript", encoding="utf-8")
        router = ModelRouter(memory_limit_gb=16.0)
        runtime = WhisperCppSTT(model_router=router)

        assert runtime.transcribe(audio) == "router transcript"
        assert router.active_model is None
