"""Tests for local TTS runtime."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import jarvis.runtime.tts_runtime as tts_runtime

from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.tts_runtime import (
    LocalTTSRuntime,
    _qwen3_clone_mode,
    _qwen3_do_sample,
    _qwen3_generation_kwargs,
    _qwen3_get_shared_voice_prompt,
    _qwen3_instruction,
    _qwen3_language_for_text,
    _qwen3_shared_voice_prompt_cache_path,
    _qwen3_shared_voice_reference_text,
    _qwen3_shared_voice_enabled,
    _qwen3_synthesize,
    _qwen3_speaker_for_text,
    _write_qwen_audio_file,
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

    def test_select_voice_prefers_yuna_premium_for_korean(self) -> None:
        runtime = LocalTTSRuntime()

        voice = runtime._select_voice("안녕하세요. 시스템 상태를 보고드립니다.")

        assert voice == JARVIS_PERSONA.macos_voice_ko
        assert voice == "Yuna (Premium)"

    def test_select_voice_prefers_british_male_reed_for_english(self) -> None:
        runtime = LocalTTSRuntime()

        voice = runtime._select_voice("System check complete. Awaiting your instruction.")

        assert voice == JARVIS_PERSONA.macos_voice_en
        assert voice == "Reed (영어(영국))"

    def test_resolve_available_voice_falls_back_from_yuna_premium_to_yuna(self, monkeypatch) -> None:
        runtime = LocalTTSRuntime()
        monkeypatch.setattr(
            "jarvis.runtime.tts_runtime._available_macos_say_voices",
            lambda binary: {"Yuna", "Reed (영어(영국))"},
        )

        voice = runtime._resolve_available_voice("Yuna (Premium)", binary="/usr/bin/say")

        assert voice == "Yuna"

    def test_qwen_language_detection_prefers_korean_for_hangul_text(self) -> None:
        assert _qwen3_language_for_text("안녕하세요. 시스템 점검을 시작합니다.") == "Korean"

    def test_qwen_speaker_defaults_to_male_english_voice(self) -> None:
        assert _qwen3_speaker_for_text("System status report.") == "Ryan"

    def test_qwen_shared_voice_enabled_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_QWEN_TTS_SHARED_VOICE", raising=False)
        assert _qwen3_shared_voice_enabled() is True

    def test_qwen_clone_mode_defaults_to_xvector(self, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_QWEN_TTS_CLONE_MODE", raising=False)
        assert _qwen3_clone_mode() == "xvector"

    def test_qwen_shared_voice_reference_text_defaults_by_language(self, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_QWEN_TTS_REF_TEXT", raising=False)
        monkeypatch.delenv("JARVIS_QWEN_TTS_REF_TEXT_EN", raising=False)
        monkeypatch.delenv("JARVIS_QWEN_TTS_REF_TEXT_KO", raising=False)

        assert "Good evening" in _qwen3_shared_voice_reference_text("English")
        assert "안녕하세요" in _qwen3_shared_voice_reference_text("Korean")

    def test_qwen_instruction_adds_korean_sentence_final_guidance(self, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_QWEN_TTS_INSTRUCT", raising=False)

        instruction = _qwen3_instruction(JARVIS_PERSONA, language="Korean")

        assert "sentence-final syllables" in instruction

    def test_qwen_sampling_is_disabled_by_default(self, monkeypatch) -> None:
        monkeypatch.delenv("JARVIS_QWEN_TTS_DO_SAMPLE", raising=False)

        assert _qwen3_do_sample() is False
        assert _qwen3_generation_kwargs(non_streaming_mode=True) == {
            "non_streaming_mode": True,
            "do_sample": False,
        }

    def test_qwen_backend_prefers_shared_voice_path_when_available(self, monkeypatch, tmp_path: Path) -> None:
        written = tmp_path / "clone.wav"

        def fake_shared(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            output_path.write_bytes(b"CLONE")
            return output_path

        def fail_custom(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            raise AssertionError("custom voice path should not run")

        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_try_shared_voice_synthesize", fake_shared)
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_generate_custom_voice", fail_custom)

        result = _qwen3_synthesize("System online", written, persona=JARVIS_PERSONA)

        assert result == written
        assert written.read_bytes() == b"CLONE"

    def test_qwen_backend_falls_back_to_custom_voice_when_shared_voice_unavailable(self, monkeypatch, tmp_path: Path) -> None:
        written = tmp_path / "custom.wav"

        def fake_shared(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            return None

        def fake_custom(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            output_path.write_bytes(b"CUSTOM")
            return output_path

        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_try_shared_voice_synthesize", fake_shared)
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_generate_custom_voice", fake_custom)

        result = _qwen3_synthesize("System online", written, persona=JARVIS_PERSONA)

        assert result == written
        assert written.read_bytes() == b"CUSTOM"

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

    def test_qwen_shared_voice_prompt_prefers_disk_cache(self, monkeypatch) -> None:
        sentinel = ["disk-prompt"]

        monkeypatch.setattr(tts_runtime, "_qwen3_shared_voice_prompts", {})
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_clone_mode", lambda: "xvector")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_instruction", lambda persona, language=None: "instr")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_speaker_for_language", lambda language: "Ryan")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_shared_voice_reference_text", lambda language: "seed")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_custom_model_path", "/tmp/custom")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_base_model_path", "/tmp/base")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._load_qwen3_shared_voice_prompt_from_disk", lambda signature: sentinel)

        class FailingCustomModel:
            def generate_custom_voice(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise AssertionError("custom voice generation should not run when disk cache exists")

        prompt = _qwen3_get_shared_voice_prompt(
            custom_model=FailingCustomModel(),
            base_model=object(),
            persona=JARVIS_PERSONA,
            language="Korean",
        )

        assert prompt is sentinel

    def test_qwen_shared_voice_prompt_persists_after_generation(self, monkeypatch) -> None:
        stored: list[tuple[str, object]] = []

        monkeypatch.setattr(tts_runtime, "_qwen3_shared_voice_prompts", {})
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_clone_mode", lambda: "xvector")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_instruction", lambda persona, language=None: "instr")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_speaker_for_language", lambda language: "Ryan")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_shared_voice_reference_text", lambda language: "seed")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_custom_model_path", "/tmp/custom")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_base_model_path", "/tmp/base")
        monkeypatch.setattr("jarvis.runtime.tts_runtime._load_qwen3_shared_voice_prompt_from_disk", lambda signature: None)
        monkeypatch.setattr("jarvis.runtime.tts_runtime._store_qwen3_shared_voice_prompt_to_disk", lambda signature, prompt: stored.append((signature, prompt)))

        class FakeCustomModel:
            def generate_custom_voice(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                return ["wav"], 24000

        class FakeBaseModel:
            def create_voice_clone_prompt(self, **kwargs):  # type: ignore[no-untyped-def]
                return ["generated-prompt"]

        prompt = _qwen3_get_shared_voice_prompt(
            custom_model=FakeCustomModel(),
            base_model=FakeBaseModel(),
            persona=JARVIS_PERSONA,
            language="Korean",
        )

        assert prompt == ["generated-prompt"]
        assert len(stored) == 1
        assert stored[0][1] == ["generated-prompt"]

    def test_qwen_shared_voice_prompt_cache_path_uses_menubar_data_dir(self, monkeypatch, tmp_path: Path) -> None:
        menubar_dir = tmp_path / "menubar-data"
        monkeypatch.setenv("JARVIS_MENUBAR_DATA_DIR", str(menubar_dir))
        monkeypatch.delenv("JARVIS_QWEN_TTS_PROMPT_CACHE_DIR", raising=False)

        signature = "korean|xvector|Ryan|instr|seed"
        path = _qwen3_shared_voice_prompt_cache_path(signature)

        expected_name = hashlib.sha256(signature.encode("utf-8")).hexdigest() + ".pt"
        assert path == menubar_dir / "tts_voice_prompts" / expected_name

    def test_qwen_backend_retries_after_previous_unavailable_state(self, monkeypatch, tmp_path: Path) -> None:
        written = tmp_path / "retry.wav"

        def fake_shared(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            return None

        def fake_custom(text: str, output_path: Path, *, persona, model_router=None):  # type: ignore[no-untyped-def]
            output_path.write_bytes(b"RETRY")
            return output_path

        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_try_shared_voice_synthesize", fake_shared)
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_generate_custom_voice", fake_custom)
        monkeypatch.setattr(tts_runtime, "_qwen3_available", False)

        result = _qwen3_synthesize("System online", written, persona=JARVIS_PERSONA)

        assert result == written
        assert written.read_bytes() == b"RETRY"

    def test_qwen_warmup_delegates_to_backend(self, monkeypatch) -> None:
        monkeypatch.setattr("jarvis.runtime.tts_runtime._qwen3_warmup", lambda *, persona, model_router=None: True)

        runtime = LocalTTSRuntime(backend="qwen3")

        assert runtime.warmup() is True

    def test_qwen_audio_file_adds_tail_padding(self, tmp_path: Path) -> None:
        sf = pytest.importorskip("soundfile")
        np = pytest.importorskip("numpy")

        output = tmp_path / "tail.wav"
        _write_qwen_audio_file(output, np.ones(24_000, dtype=np.float32), 24_000)

        data, sr = sf.read(str(output), dtype="float32")

        assert sr == 24_000
        assert len(data) > 24_000
