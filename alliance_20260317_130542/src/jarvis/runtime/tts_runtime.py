"""Local text-to-speech runtime with JARVIS persona support.

Supports two backends:
  1. macOS `say` — fast, no model loading, uses configured system voices
  2. Qwen3-TTS — neural TTS with custom voice persona (optional quality mode)

Backend selection defaults to macOS `say`; Qwen3-TTS remains opt-in.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import importlib.util
import io
import logging
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from jarvis.runtime_paths import resolve_menubar_data_dir
from jarvis.runtime.model_router import ModelRouter
from jarvis.runtime.voice_persona import DEFAULT_PERSONA, VoicePersona

logger = logging.getLogger(__name__)

_DEFAULT_MEMORY_GB = 2.0
_QWEN3_TTS_CUSTOM_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"
_QWEN3_TTS_BASE_MODEL = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
_QWEN3_TTS_EN_SPEAKER = "Ryan"
_QWEN3_TTS_KO_SPEAKER = "Ryan"
_QWEN3_TTS_DEFAULT_INSTRUCT = (
    "Speak like a calm, polished, male AI assistant with a subtle British-leaning tone. "
    "Low-medium pitch, measured pacing, precise diction, understated wit, "
    "never bubbly, never cartoonish, never exaggerated."
)
_QWEN3_TTS_SHARED_REF_TEXT_EN = (
    "Good evening. All systems are stable and ready for your command."
)
_QWEN3_TTS_SHARED_REF_TEXT_KO = (
    "안녕하세요. 모든 시스템이 안정적으로 작동 중이며 명령을 기다리고 있습니다."
)
_QWEN3_TTS_TAIL_PAD_MS = 220
_QWEN3_TTS_DO_SAMPLE = False
_HANGUL_RE = re.compile(r"[가-힣]")
_CODE_TOKEN_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9]+)?\b")
_KOREAN_TTS_ALIASES = {
    "pipeline": "파이프라인",
}
_MACOS_SAY_VOICE_LINE_RE = re.compile(r"^(?P<name>.+?)\s{2,}\S+\s+#")
_macos_say_voices_cache: dict[str, set[str]] = {}
_macos_say_voices_lock = threading.Lock()


class LocalTTSRuntime:
    """Local TTS with persona support and multi-backend.

    Defaults to macOS `say` for low-latency playback.
    Qwen3-TTS remains available as an opt-in backend.
    """

    def __init__(
        self,
        *,
        voice: str | None = None,
        backend: str = "say",
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

    def warmup(self) -> bool:
        """Best-effort warmup for the configured TTS backend."""
        if self._backend in ("auto", "qwen3"):
            if _qwen3_warmup(persona=self._persona, model_router=self._model_router):
                return True
            if self._backend == "qwen3":
                return False
        return bool(self._binary_path or shutil.which("say"))

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

    def _resolve_available_voice(self, desired_voice: str, *, binary: str) -> str:
        available = _available_macos_say_voices(binary)
        if not available or desired_voice in available:
            return desired_voice
        for candidate in _fallback_macos_say_voices(desired_voice):
            if candidate in available:
                return candidate
        return desired_voice

    def _synthesize_macos_say(self, text: str, output_path: Path) -> Path:
        """Synthesize via macOS `say` command with language-appropriate voice."""
        binary = self._binary_path or shutil.which("say")
        if binary is None:
            raise RuntimeError("macOS `say` command not found")

        prepared_text = self._prepare_text_for_say(text)
        voice = self._resolve_available_voice(self._select_voice(prepared_text), binary=binary)

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


def _available_macos_say_voices(binary: str) -> set[str]:
    with _macos_say_voices_lock:
        cached = _macos_say_voices_cache.get(binary)
        if cached is not None:
            return cached
    try:
        result = subprocess.run(
            [binary, "-v", "?"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return set()
    if result.returncode != 0:
        return set()
    voices: set[str] = set()
    for line in result.stdout.splitlines():
        match = _MACOS_SAY_VOICE_LINE_RE.match(line.strip())
        if match is not None:
            voices.add(match.group("name").strip())
    with _macos_say_voices_lock:
        _macos_say_voices_cache[binary] = voices
    return voices


def _fallback_macos_say_voices(desired_voice: str) -> tuple[str, ...]:
    candidates: list[str] = []
    if desired_voice.endswith(" (Premium)"):
        candidates.append(desired_voice.removesuffix(" (Premium)"))
    if "한국어" in desired_voice or desired_voice.startswith("Yuna"):
        candidates.extend(
            [
                "Yuna (Premium)",
                "Yuna",
                "Reed (한국어(대한민국))",
                "Rocko (한국어(대한민국))",
            ]
        )
    if "영어" in desired_voice:
        candidates.extend(
            [
                "Reed (영어(영국))",
                "Reed (영어(미국))",
                "Eddy (영어(영국))",
            ]
        )
    seen: list[str] = []
    for candidate in candidates:
        if candidate != desired_voice and candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


# --- Qwen3-TTS Backend ---

_qwen3_custom_model = None
_qwen3_custom_model_path = ""
_qwen3_base_model = None
_qwen3_base_model_path = ""
_qwen3_shared_voice_prompts: dict[str, object] = {}
_qwen3_available: bool | None = None
_qwen3_state_lock = threading.RLock()


def _qwen3_synthesize(
    text: str,
    output_path: Path,
    *,
    persona: VoicePersona,
    model_router: ModelRouter | None = None,
) -> Path | None:
    """Synthesize using qwen-tts with shared cross-language voice when available."""
    global _qwen3_available

    if _qwen3_shared_voice_enabled():
        result = _qwen3_try_shared_voice_synthesize(
            text,
            output_path,
            persona=persona,
            model_router=model_router,
        )
        if result is not None:
            _qwen3_available = True
            return result

    return _qwen3_generate_custom_voice(
        text,
        output_path,
        persona=persona,
        model_router=model_router,
    )


def _qwen3_try_shared_voice_synthesize(
    text: str,
    output_path: Path,
    *,
    persona: VoicePersona,
    model_router: ModelRouter | None = None,
) -> Path | None:
    custom_model_path = _resolve_qwen3_tts_custom_model_path()
    base_model_path = _resolve_qwen3_tts_base_model_path()
    if custom_model_path is None or base_model_path is None:
        return None

    imported = _import_qwen3_runtime()
    if imported is None:
        return None
    torch, Qwen3TTSModel = imported

    if model_router is not None:
        granted = model_router.request_load("tts-qwen3-shared", 6.0)
        if not granted:
            return None

    try:
        language = _qwen3_language_for_text(text)
        with _qwen3_state_lock:
            custom_model = _load_qwen3_custom_model(
                custom_model_path,
                torch=torch,
                qwen3_model_class=Qwen3TTSModel,
            )
            base_model = _load_qwen3_base_model(
                base_model_path,
                torch=torch,
                qwen3_model_class=Qwen3TTSModel,
            )
            prompt_items = _qwen3_get_shared_voice_prompt(
                custom_model=custom_model,
                base_model=base_model,
                persona=persona,
                language=language,
            )
            with _capture_third_party_tts_output():
                wavs, sr = base_model.generate_voice_clone(
                    text=text,
                    language=language,
                    voice_clone_prompt=prompt_items,
                    **_qwen3_generation_kwargs(non_streaming_mode=True),
                )
        _write_qwen_audio_file(output_path, wavs[0], sr)
        return output_path
    except Exception as exc:
        logger.warning("Shared Qwen3-TTS voice clone failed: %s", exc)
        return None
    finally:
        if model_router is not None:
            model_router.release("tts-qwen3-shared")


def _qwen3_generate_custom_voice(
    text: str,
    output_path: Path,
    *,
    persona: VoicePersona,
    model_router: ModelRouter | None = None,
) -> Path | None:
    global _qwen3_available

    custom_model_path = _resolve_qwen3_tts_custom_model_path()
    if custom_model_path is None:
        _qwen3_available = False
        return None

    imported = _import_qwen3_runtime()
    if imported is None:
        _qwen3_available = False
        return None
    torch, Qwen3TTSModel = imported

    if model_router is not None:
        granted = model_router.request_load("tts-qwen3", 4.0)
        if not granted:
            return None

    try:
        with _qwen3_state_lock:
            custom_model = _load_qwen3_custom_model(
                custom_model_path,
                torch=torch,
                qwen3_model_class=Qwen3TTSModel,
            )
            with _capture_third_party_tts_output():
                language = _qwen3_language_for_text(text)
                wavs, sr = custom_model.generate_custom_voice(
                    text=text,
                    language=language,
                    speaker=_qwen3_speaker_for_text(text),
                    instruct=_qwen3_instruction(persona, language=language),
                    **_qwen3_generation_kwargs(non_streaming_mode=True),
                )
        _write_qwen_audio_file(output_path, wavs[0], sr)
        _qwen3_available = True
        return output_path
    except Exception as exc:
        logger.warning("Qwen3-TTS synthesis failed: %s", exc)
        return None
    finally:
        if model_router is not None:
            model_router.release("tts-qwen3")


def _resolve_qwen3_tts_custom_model_path() -> Path | None:
    return _resolve_qwen3_tts_snapshot_path(
        env_var="JARVIS_QWEN_TTS_MODEL_PATH",
        cache_dir_name="models--Qwen--Qwen3-TTS-12Hz-0.6B-CustomVoice",
    )


def _resolve_qwen3_tts_base_model_path() -> Path | None:
    return _resolve_qwen3_tts_snapshot_path(
        env_var="JARVIS_QWEN_TTS_BASE_MODEL_PATH",
        cache_dir_name="models--Qwen--Qwen3-TTS-12Hz-0.6B-Base",
    )


def _resolve_qwen3_tts_snapshot_path(*, env_var: str, cache_dir_name: str) -> Path | None:
    configured = os.getenv(env_var, "").strip()
    if configured:
        candidate = Path(configured).expanduser().resolve()
        if candidate.exists():
            return candidate

    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / cache_dir_name
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


def _load_qwen3_custom_model(model_path: Path, *, torch, qwen3_model_class):  # type: ignore[no-untyped-def]
    global _qwen3_custom_model, _qwen3_custom_model_path
    if _qwen3_custom_model is None or _qwen3_custom_model_path != str(model_path):
        logger.info("Loading Qwen3-TTS custom voice model...")
        with _capture_third_party_tts_output():
            _qwen3_custom_model = qwen3_model_class.from_pretrained(
                str(model_path),
                device_map="cpu",
                dtype=torch.float32,
            )
        _qwen3_custom_model_path = str(model_path)
        logger.info("Qwen3-TTS custom voice model loaded")
    return _qwen3_custom_model


def _load_qwen3_base_model(model_path: Path, *, torch, qwen3_model_class):  # type: ignore[no-untyped-def]
    global _qwen3_base_model, _qwen3_base_model_path
    if _qwen3_base_model is None or _qwen3_base_model_path != str(model_path):
        logger.info("Loading Qwen3-TTS base voice clone model...")
        with _capture_third_party_tts_output():
            _qwen3_base_model = qwen3_model_class.from_pretrained(
                str(model_path),
                device_map="cpu",
                dtype=torch.float32,
            )
        _qwen3_base_model_path = str(model_path)
        logger.info("Qwen3-TTS base voice clone model loaded")
    return _qwen3_base_model


def _qwen3_warmup(*, persona: VoicePersona, model_router: ModelRouter | None = None) -> bool:
    global _qwen3_available

    custom_model_path = _resolve_qwen3_tts_custom_model_path()
    if custom_model_path is None:
        _qwen3_available = False
        return False

    imported = _import_qwen3_runtime()
    if imported is None:
        _qwen3_available = False
        return False
    torch, Qwen3TTSModel = imported

    requested_key = "tts-qwen3-warmup"
    requested_memory = 6.0 if _qwen3_shared_voice_enabled() else 4.0
    if model_router is not None:
        granted = model_router.request_load(requested_key, requested_memory)
        if not granted:
            return False

    try:
        with _qwen3_state_lock:
            custom_model = _load_qwen3_custom_model(
                custom_model_path,
                torch=torch,
                qwen3_model_class=Qwen3TTSModel,
            )
            if _qwen3_shared_voice_enabled():
                base_model_path = _resolve_qwen3_tts_base_model_path()
                if base_model_path is None:
                    return False
                base_model = _load_qwen3_base_model(
                    base_model_path,
                    torch=torch,
                    qwen3_model_class=Qwen3TTSModel,
                )
                _qwen3_get_shared_voice_prompt(
                    custom_model=custom_model,
                    base_model=base_model,
                    persona=persona,
                    language="English",
                )
                _qwen3_get_shared_voice_prompt(
                    custom_model=custom_model,
                    base_model=base_model,
                    persona=persona,
                    language="Korean",
                )
        _qwen3_available = True
        return True
    except Exception as exc:
        logger.warning("Qwen3-TTS warmup failed: %s", exc)
        return False
    finally:
        if model_router is not None:
            model_router.release(requested_key)


def _qwen3_get_shared_voice_prompt(*, custom_model, base_model, persona: VoicePersona, language: str):  # type: ignore[no-untyped-def]
    global _qwen3_shared_voice_prompts

    seed_text = _qwen3_shared_voice_reference_text(language)
    clone_mode = _qwen3_clone_mode()
    instruction = _qwen3_instruction(persona, language=language)
    speaker = _qwen3_speaker_for_language(language)
    signature = "|".join(
        (
            language,
            clone_mode,
            speaker,
            instruction,
            seed_text,
            _qwen3_custom_model_path,
            _qwen3_base_model_path,
        )
    )
    cached = _qwen3_shared_voice_prompts.get(signature)
    if cached is not None:
        return cached

    disk_cached = _load_qwen3_shared_voice_prompt_from_disk(signature)
    if disk_cached is not None:
        _qwen3_shared_voice_prompts[signature] = disk_cached
        return disk_cached

    with _capture_third_party_tts_output():
        wavs, sr = custom_model.generate_custom_voice(
            text=seed_text,
            language=language,
            speaker=speaker,
            instruct=instruction,
            **_qwen3_generation_kwargs(non_streaming_mode=True),
        )
    use_xvector_only = clone_mode == "xvector"
    with _capture_third_party_tts_output():
        prompt = base_model.create_voice_clone_prompt(
            ref_audio=(wavs[0], sr),
            ref_text=None if use_xvector_only else seed_text,
            x_vector_only_mode=use_xvector_only,
        )
    _qwen3_shared_voice_prompts[signature] = prompt
    _store_qwen3_shared_voice_prompt_to_disk(signature, prompt)
    return prompt


def _qwen3_shared_voice_prompt_cache_path(signature: str) -> Path:
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    return _qwen3_shared_prompt_cache_dir() / f"{digest}.pt"


def _qwen3_shared_prompt_cache_dir() -> Path:
    configured = os.getenv("JARVIS_QWEN_TTS_PROMPT_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return resolve_menubar_data_dir() / "tts_voice_prompts"


def _load_qwen3_shared_voice_prompt_from_disk(signature: str):  # type: ignore[no-untyped-def]
    prompt_path = _qwen3_shared_voice_prompt_cache_path(signature)
    if not prompt_path.exists():
        return None
    imported = _import_qwen3_runtime()
    if imported is None:
        return None
    torch, _ = imported
    try:
        return torch.load(prompt_path, map_location="cpu", weights_only=False)
    except Exception as exc:
        logger.warning("Failed to load cached Qwen3 shared voice prompt: %s", exc)
        return None


def _store_qwen3_shared_voice_prompt_to_disk(signature: str, prompt) -> None:  # type: ignore[no-untyped-def]
    imported = _import_qwen3_runtime()
    if imported is None:
        return
    torch, _ = imported
    prompt_path = _qwen3_shared_voice_prompt_cache_path(signature)
    try:
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(prompt, prompt_path)
    except Exception as exc:
        logger.warning("Failed to persist Qwen3 shared voice prompt: %s", exc)


def _write_qwen_audio_file(output_path: Path, waveform, sample_rate: int) -> None:  # type: ignore[no-untyped-def]
    import numpy as np
    import soundfile as sf

    data = np.asarray(waveform, dtype=np.float32)
    tail_ms = _qwen3_tail_pad_ms()
    if tail_ms > 0:
        silence_samples = int(sample_rate * tail_ms / 1000)
        if silence_samples > 0:
            data = np.concatenate([data, np.zeros(silence_samples, dtype=data.dtype)])
    sf.write(str(output_path), data, sample_rate)


def _qwen3_language_for_text(text: str) -> str:
    hangul_chars = len(_HANGUL_RE.findall(text))
    if hangul_chars > max(1, len(text) // 8):
        return "Korean"
    return "English"


def _qwen3_speaker_for_language(language: str) -> str:
    if language == "Korean":
        return os.getenv("JARVIS_QWEN_TTS_SPEAKER_KO", _QWEN3_TTS_KO_SPEAKER).strip() or _QWEN3_TTS_KO_SPEAKER
    return os.getenv("JARVIS_QWEN_TTS_SPEAKER_EN", _QWEN3_TTS_EN_SPEAKER).strip() or _QWEN3_TTS_EN_SPEAKER


def _qwen3_speaker_for_text(text: str) -> str:
    return _qwen3_speaker_for_language(_qwen3_language_for_text(text))


def _qwen3_instruction(persona: VoicePersona, *, language: str | None = None) -> str:
    configured = os.getenv("JARVIS_QWEN_TTS_INSTRUCT", "").strip()
    if configured:
        return configured
    base_instruction = persona.speaker_description.strip() or _QWEN3_TTS_DEFAULT_INSTRUCT
    if language == "Korean":
        return (
            f"{base_instruction} "
            "When speaking Korean, articulate sentence-final syllables fully, "
            "finish each final consonant cleanly, and do not clip the ending."
        )
    return base_instruction


def _qwen3_shared_voice_enabled() -> bool:
    configured = os.getenv("JARVIS_QWEN_TTS_SHARED_VOICE", "1").strip().lower()
    return configured not in {"0", "false", "no", "off"}


def _qwen3_clone_mode() -> str:
    configured = os.getenv("JARVIS_QWEN_TTS_CLONE_MODE", "xvector").strip().lower()
    if configured == "icl":
        return "icl"
    return "xvector"


def _qwen3_shared_voice_reference_text(language: str) -> str:
    env_name = "JARVIS_QWEN_TTS_REF_TEXT_KO" if language == "Korean" else "JARVIS_QWEN_TTS_REF_TEXT_EN"
    configured = os.getenv(env_name, "").strip()
    if configured:
        return configured
    configured = os.getenv("JARVIS_QWEN_TTS_REF_TEXT", "").strip()
    if configured:
        return configured
    if language == "Korean":
        return _QWEN3_TTS_SHARED_REF_TEXT_KO
    return _QWEN3_TTS_SHARED_REF_TEXT_EN


def _qwen3_tail_pad_ms() -> int:
    configured = os.getenv("JARVIS_TTS_TAIL_PAD_MS", "").strip()
    if configured.isdigit():
        return max(0, int(configured))
    return _QWEN3_TTS_TAIL_PAD_MS


def _qwen3_generation_kwargs(*, non_streaming_mode: bool) -> dict[str, object]:
    return {
        "non_streaming_mode": non_streaming_mode,
        "do_sample": _qwen3_do_sample(),
    }


def _qwen3_do_sample() -> bool:
    configured = os.getenv("JARVIS_QWEN_TTS_DO_SAMPLE", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return _QWEN3_TTS_DO_SAMPLE


def _import_qwen3_runtime():  # type: ignore[no-untyped-def]
    try:
        logging.getLogger("sox").setLevel(logging.ERROR)
        with _capture_third_party_tts_output(), _hide_mlx_from_transformers():
            import torch
            from qwen_tts import Qwen3TTSModel
        return torch, Qwen3TTSModel
    except ImportError:
        return None


@contextlib.contextmanager
def _capture_third_party_tts_output():
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        yield
    captured = "\n".join(
        part.strip()
        for part in (stdout_buffer.getvalue(), stderr_buffer.getvalue())
        if part.strip()
    )
    if captured:
        logger.debug("Suppressed third-party TTS output: %s", captured[:400])


@contextlib.contextmanager
def _hide_mlx_from_transformers():
    """Prevent transformers/qwen_tts import from touching unstable local MLX installs."""
    real_find_spec = importlib.util.find_spec
    real_version = importlib.metadata.version

    def patched_find_spec(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "mlx":
            return None
        return real_find_spec(name, *args, **kwargs)

    def patched_version(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name == "mlx":
            raise importlib.metadata.PackageNotFoundError(name)
        return real_version(name, *args, **kwargs)

    importlib.util.find_spec = patched_find_spec
    importlib.metadata.version = patched_version
    try:
        yield
    finally:
        importlib.util.find_spec = real_find_spec
        importlib.metadata.version = real_version
