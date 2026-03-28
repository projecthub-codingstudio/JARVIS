"""Local text-to-speech runtime with JARVIS persona support.

Supports two backends:
  1. macOS `say` — fast, no model loading, uses Reed male voices for JARVIS
  2. Qwen3-TTS — neural TTS with custom voice persona (Phase 2)

Backend selection: Qwen3-TTS preferred when available, macOS `say` fallback.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.voice_persona import DEFAULT_PERSONA, VoicePersona

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_GB = 2.0
_QWEN3_TTS_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_QWEN3_TTS_EN_SPEAKER = "Ryan"
_QWEN3_TTS_KO_SPEAKER = "Ryan"
_QWEN3_TTS_DEFAULT_INSTRUCT = (
    "Speak like a calm, polished, male AI assistant with a subtle British-leaning tone. "
    "Low-medium pitch, measured pacing, precise diction, understated wit, "
    "never bubbly, never cartoonish, never exaggerated."
)
_HANGUL_RE = re.compile(r"[가-힣]")
_CODE_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9]+)?\b")
_KOREAN_TTS_ALIASES = {
    "pipeline": "파이프라인",
}


class LocalTTSRuntime:
    """Local TTS with persona support and multi-backend.

    Tries Qwen3-TTS first for high-quality neural voice, falls back
    to macOS `say` with male Reed voices for JARVIS persona.
    """

    def __init__(
        self,
        *,
        voice: str | None = None,
        backend: str = "auto",
        binary_path: str | None = None,
        model_router: ModelRouter | None = None,
        estimated_memory_gb: float = _DEFAULT_MEMORY_GB,
        persona: VoicePersona | None = None,
    ) -> None:
        self._persona = persona or DEFAULT_PERSONA
        self._voice_override = voice  # None = auto-detect language
        self._backend = backend
        self._binary_path = binary_path
        self._model_router = model_router
        self._estimated_memory_gb = estimated_memory_gb

    @property
    def persona(self) -> VoicePersona:
        return self._persona

    def synthesize(self, text: str, output_path: Path) -> Path:
        """Synthesize text to an audio file using the best available backend."""
        clean_text = text.strip()
        if not clean_text:
            raise RuntimeError("Cannot synthesize empty text")

        path = output_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Deterministic test fallback.
        if path.suffix.lower() == ".txt":
            path.write_text(clean_text, encoding="utf-8")
            return path

        # Try Qwen3-TTS first (neural, high quality)
        if self._backend in ("auto", "qwen3"):
            result = self._synthesize_qwen3(clean_text, path)
            if result is not None:
                return result
            if self._backend == "qwen3":
                raise RuntimeError("Qwen3-TTS backend requested but unavailable")

        # Fallback: macOS `say` with persona voice
        return self._synthesize_macos_say(clean_text, path)

    def _synthesize_qwen3(self, text: str, output_path: Path) -> Path | None:
        """Attempt synthesis via Qwen3-TTS. Returns None if unavailable."""
        try:
            return _qwen3_synthesize(
                text, output_path,
                persona=self._persona,
                model_router=self._model_router,
            )
        except Exception as exc:
            logger.debug("Qwen3-TTS unavailable: %s — falling back to macOS say", exc)
            return None

    def _select_voice(self, text: str) -> str:
        """Select the appropriate macOS voice based on text language."""
        if self._voice_override:
            return self._voice_override
        # Detect if text is primarily Korean (contains Hangul)
        korean_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7a3' or '\u3131' <= c <= '\u3163')
        if korean_chars > len(text) * 0.2:
            return self._persona.macos_voice_ko
        return self._persona.macos_voice_en

    def _synthesize_macos_say(self, text: str, output_path: Path) -> Path:
        """Synthesize via macOS `say` command with language-appropriate voice."""
        binary = self._binary_path or shutil.which("say")
        if binary is None:
            raise RuntimeError("macOS `say` command not found")

        prepared_text = self._prepare_text_for_say(text)
        voice = self._select_voice(prepared_text)

        if self._model_router is not None:
            granted = self._model_router.request_load("tts-local", self._estimated_memory_gb)
            if not granted:
                raise RuntimeError("ModelRouter denied loading local TTS")

        try:
            cmd = [
                binary,
                "-v", voice,
                "-r", str(self._persona.macos_rate),
                "-o", str(output_path),
                prepared_text,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False,
            )
        finally:
            if self._model_router is not None:
                self._model_router.release("tts-local")

        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            raise RuntimeError(f"TTS synthesis failed: {stderr}")

        return output_path

    def _prepare_text_for_say(self, text: str) -> str:
        def replace_code_token(match: re.Match[str]) -> str:
            token = match.group(0)
            if any(char.isdigit() for char in token):
                return token
            if "." in token:
                stem, suffix = token.rsplit(".", 1)
                return f"{self._expand_identifier(stem)} dot {' '.join(suffix)}"
            return self._expand_identifier(token)

        return _CODE_TOKEN_RE.sub(replace_code_token, text)

    @staticmethod
    def _expand_identifier(token: str) -> str:
        alias = _KOREAN_TTS_ALIASES.get(token.lower())
        if alias is not None:
            return alias
        expanded = token.replace("_", " ")
        expanded = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", expanded)
        if token.isupper() and len(token) <= 5:
            return " ".join(token)
        return expanded


# --- Qwen3-TTS Backend ---

_qwen3_model = None
_qwen3_model_path = ""
_qwen3_available: bool | None = None


def _qwen3_synthesize(
    text: str,
    output_path: Path,
    *,
    persona: VoicePersona,
    model_router: ModelRouter | None = None,
) -> Path | None:
    """Synthesize using qwen-tts with a locally cached custom voice model."""
    global _qwen3_model, _qwen3_model_path, _qwen3_available

    if _qwen3_available is False:
        return None

    model_path = _resolve_qwen3_tts_model_path()
    if model_path is None:
        _qwen3_available = False
        return None

    try:
        import torch
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        _qwen3_available = False
        return None

    if model_router is not None:
        granted = model_router.request_load("tts-qwen3", 4.0)
        if not granted:
            return None

    try:
        # Lazy load model
        if _qwen3_model is None or _qwen3_model_path != str(model_path):
            logger.info("Loading Qwen3-TTS model...")
            _qwen3_model = Qwen3TTSModel.from_pretrained(
                str(model_path),
                device_map="cpu",
                dtype=torch.float32,
            )
            _qwen3_model_path = str(model_path)
            _qwen3_available = True
            logger.info("Qwen3-TTS model loaded")

        wavs, sr = _qwen3_model.generate_custom_voice(
            text=text,
            language=_qwen3_language_for_text(text),
            speaker=_qwen3_speaker_for_text(text),
            instruct=_qwen3_instruction(persona),
        )
        sf.write(str(output_path), wavs[0], sr)
        return output_path
    except Exception as exc:
        logger.warning("Qwen3-TTS synthesis failed: %s", exc)
        return None
    finally:
        if model_router is not None:
            model_router.release("tts-qwen3")


def _resolve_qwen3_tts_model_path() -> Path | None:
    configured = os.getenv("JARVIS_QWEN_TTS_MODEL_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.exists():
            return candidate

    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice"
    )
    main_ref = cache_root / "refs" / "main"
    if main_ref.exists():
        revision = main_ref.read_text(encoding="utf-8").strip()
        if revision:
            snapshot = cache_root / "snapshots" / revision
            if snapshot.exists():
                return snapshot

    snapshots_dir = cache_root / "snapshots"
    if snapshots_dir.exists():
        snapshots = sorted(
            (path for path in snapshots_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if snapshots:
            return snapshots[0]
    return None


def _qwen3_language_for_text(text: str) -> str:
    hangul_chars = len(_HANGUL_RE.findall(text))
    if hangul_chars > max(1, len(text) // 8):
        return "Korean"
    return "English"


def _qwen3_speaker_for_text(text: str) -> str:
    language = _qwen3_language_for_text(text)
    if language == "Korean":
        return os.getenv("JARVIS_QWEN_TTS_SPEAKER_KO", _QWEN3_TTS_KO_SPEAKER).strip() or _QWEN3_TTS_KO_SPEAKER
    return os.getenv("JARVIS_QWEN_TTS_SPEAKER_EN", _QWEN3_TTS_EN_SPEAKER).strip() or _QWEN3_TTS_EN_SPEAKER


def _qwen3_instruction(persona: VoicePersona) -> str:
    configured = os.getenv("JARVIS_QWEN_TTS_INSTRUCT", "").strip()
    if configured:
        return configured
    if persona.speaker_description.strip():
        return persona.speaker_description.strip()
    return _QWEN3_TTS_DEFAULT_INSTRUCT
