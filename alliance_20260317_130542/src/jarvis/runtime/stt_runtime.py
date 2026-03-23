"""Local speech-to-text runtime using whisper.cpp."""

from __future__ import annotations

import logging
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from jarvis.runtime.model_router import ModelRouter

logger = logging.getLogger(__name__)

_DEFAULT_BINARY_CANDIDATES = ("whisper-cli", "main")
_DEFAULT_MEMORY_GB = 2.0
_COMMON_BINARY_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)
_DEFAULT_MODEL_FILENAMES = (
    "ggml-small.bin",
    "ggml-base.bin",
    "ggml-medium.bin",
)
_COMMON_MODEL_DIRS = (
    Path.cwd() / "models",
    Path.home() / ".jarvis" / "models",
)
_DEFAULT_LANGUAGE = "ko"

# --- Hallucination detection ---
# Patterns that indicate whisper.cpp hallucination (repetitive or boilerplate).
_HALLUCINATION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Repeated bracketed tokens: [뭐지?] [뭐지?] ...
    re.compile(r"^(\[.+?\]\s*){3,}$"),
    # Same short phrase repeated 3+ times
    re.compile(r"^(.{2,20}?)\1{2,}"),
    # Common Korean hallucination phrases on silence
    re.compile(r"이 영상은.*영상에서", re.DOTALL),
    re.compile(r"(구독|좋아요|알림).*(구독|좋아요|알림)", re.DOTALL),
    re.compile(r"시청해\s*주셔서\s*감사합니다"),
    re.compile(r"MBC\s*뉴스"),
)

# Minimum RMS energy threshold for 16-bit PCM audio.
_MIN_RMS_ENERGY = 200.0


class WhisperCppSTT:
    """Speech-to-text wrapper around whisper.cpp CLI.

    The preferred path is a local whisper.cpp binary plus a model file.
    For deterministic local testing, a sibling `.txt` transcript file is
    accepted as a fallback input source.
    """

    def __init__(
        self,
        *,
        binary_path: str | None = None,
        model_path: Path | None = None,
        language: str | None = None,
        model_router: ModelRouter | None = None,
        estimated_memory_gb: float = _DEFAULT_MEMORY_GB,
        vocabulary_hint: str | None = None,
    ) -> None:
        self._binary_path = binary_path
        self._model_path = model_path
        self._language = language or os.getenv("JARVIS_STT_LANGUAGE", _DEFAULT_LANGUAGE)
        self._model_router = model_router
        self._estimated_memory_gb = estimated_memory_gb
        # Vocabulary hint: domain-specific terms passed to whisper --prompt.
        # Improves recognition of technical terms (e.g., "OLE 개체 속성").
        self._vocabulary_hint = vocabulary_hint or os.getenv("JARVIS_STT_VOCAB", "")

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe an audio file to text."""
        path = audio_path.expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {path}")

        # Test/dev fallback: use provided transcript when available.
        if path.suffix.lower() == ".txt":
            return path.read_text(encoding="utf-8").strip()
        transcript_path = path.with_suffix(".txt")
        if transcript_path.exists():
            return transcript_path.read_text(encoding="utf-8").strip()

        # Pre-check: skip transcription if audio is silence.
        if not _has_speech_energy(path):
            logger.info("Audio energy below threshold — skipping transcription")
            raise RuntimeError("음성이 감지되지 않았습니다. 마이크에 대고 다시 말씀해 주세요.")

        binary = self._resolve_binary()
        if binary is None:
            raise RuntimeError(
                "whisper.cpp 실행 파일을 찾을 수 없습니다. "
                "whisper-cli를 설치하거나 JARVIS_STT_BINARY를 설정해 주세요."
            )
        model_path = self._resolve_model_path()
        if model_path is None:
            raise RuntimeError("STT 모델 경로가 설정되지 않았습니다. JARVIS_STT_MODEL을 지정해 주세요.")

        if self._model_router is not None:
            granted = self._model_router.request_load("stt-whispercpp", self._estimated_memory_gb)
            if not granted:
                raise RuntimeError("ModelRouter denied loading whisper.cpp STT")

        try:
            result = subprocess.run(
                self._build_command(binary=binary, model_path=model_path, audio_path=path),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        finally:
            if self._model_router is not None:
                self._model_router.release("stt-whispercpp")

        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            raise RuntimeError(f"whisper.cpp failed: {stderr}")

        text = result.stdout.strip()
        if not text:
            raise RuntimeError("whisper.cpp returned empty transcript")

        # Post-check: detect hallucinated output.
        if _is_hallucination(text):
            logger.warning("Hallucination detected, discarding: %s", text[:80])
            raise RuntimeError("음성이 감지되지 않았습니다. 마이크에 대고 다시 말씀해 주세요.")

        return text

    def _build_command(self, *, binary: str, model_path: Path, audio_path: Path) -> list[str]:
        cmd = [
            binary,
            "-m",
            str(model_path),
            "-f",
            str(audio_path),
            "-l",
            self._language,
            "-nt",
            # Anti-hallucination flags
            "--suppress-nst",
            "--no-speech-thold",
            "0.3",
            "--entropy-thold",
            "2.2",
        ]
        # Vocabulary hint: guides whisper to correctly recognize domain terms.
        # whisper.cpp uses --prompt as initial context for the decoder,
        # biasing it toward the provided vocabulary.
        if self._vocabulary_hint:
            cmd.extend(["--prompt", self._vocabulary_hint])
        return cmd

    def _resolve_binary(self) -> str | None:
        explicit = self._binary_path or os.getenv("JARVIS_STT_BINARY")
        if explicit is not None:
            explicit_path = Path(explicit).expanduser()
            if explicit_path.exists():
                return str(explicit_path.resolve())
            return None
        for candidate in _DEFAULT_BINARY_CANDIDATES:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved
        for directory in _COMMON_BINARY_DIRS:
            for candidate in _DEFAULT_BINARY_CANDIDATES:
                binary_path = directory / candidate
                if binary_path.exists():
                    return str(binary_path)
        return None

    def _resolve_model_path(self) -> Path | None:
        explicit = self._model_path
        if explicit is None:
            env_model = os.getenv("JARVIS_STT_MODEL")
            if env_model:
                explicit = Path(env_model).expanduser()
        if explicit is not None:
            return explicit.expanduser().resolve()
        for directory in _COMMON_MODEL_DIRS:
            for filename in _DEFAULT_MODEL_FILENAMES:
                candidate = directory / filename
                if candidate.exists():
                    return candidate.resolve()
        return None


def _has_speech_energy(audio_path: Path, threshold: float = _MIN_RMS_ENERGY) -> bool:
    """Check if an audio file contains speech using Silero VAD.

    Uses Silero VAD (neural network) for accurate speech detection.
    Falls back to RMS energy check if Silero is unavailable.

    Silero VAD requires 16kHz mono audio — the recording pipeline
    already converts via ffmpeg, so this is always satisfied.
    """
    # Try Silero VAD first (ML-based, more accurate)
    silero_result = _has_speech_silero(audio_path)
    if silero_result is not None:
        return silero_result

    # Fallback: energy-based RMS check
    return _has_speech_energy_rms(audio_path, threshold)


# --- Silero VAD ---

_silero_model = None
_silero_available: bool | None = None


def _load_silero_model():
    """Lazy-load Silero VAD model (cached across calls)."""
    global _silero_model, _silero_available

    if _silero_available is False:
        return None
    if _silero_model is not None:
        return _silero_model

    try:
        from silero_vad import load_silero_vad
        _silero_model = load_silero_vad()
        _silero_available = True
        logger.info("Silero VAD model loaded")
        return _silero_model
    except Exception as exc:
        _silero_available = False
        logger.debug("Silero VAD unavailable: %s — using energy fallback", exc)
        return None


def _load_wav_as_tensor(audio_path: Path):
    """Load a WAV file as a torch float32 tensor at 16kHz.

    Avoids torchaudio's read_audio() which requires torchcodec in
    torchaudio >= 2.10. Directly reads PCM WAV using struct.
    """
    import torch

    with open(audio_path, "rb") as f:
        header = f.read(44)
        if len(header) < 44 or header[:4] != b"RIFF":
            return None
        bits_per_sample = struct.unpack_from("<H", header, 34)[0]
        sample_rate = struct.unpack_from("<I", header, 24)[0]
        raw = f.read()

    if bits_per_sample == 16:
        n = len(raw) // 2
        samples = struct.unpack(f"<{n}h", raw[:n * 2])
        tensor = torch.FloatTensor(samples) / 32768.0
    elif bits_per_sample == 32:
        n = len(raw) // 4
        samples = struct.unpack(f"<{n}i", raw[:n * 4])
        tensor = torch.FloatTensor(samples) / 2147483648.0
    else:
        return None

    # Resample to 16kHz if needed (Silero requires 16kHz)
    if sample_rate != 16000 and sample_rate > 0:
        # Simple decimation for common rates (44100→16000, 48000→16000)
        ratio = sample_rate / 16000
        indices = torch.arange(0, len(tensor), ratio).long()
        indices = indices[indices < len(tensor)]
        tensor = tensor[indices]

    return tensor


def _has_speech_silero(audio_path: Path, threshold: float = 0.3) -> bool | None:
    """Check for speech using Silero VAD. Returns None if unavailable."""
    model = _load_silero_model()
    if model is None:
        return None

    try:
        from silero_vad import get_speech_timestamps

        wav = _load_wav_as_tensor(audio_path)
        if wav is None:
            return None

        timestamps = get_speech_timestamps(wav, model, threshold=threshold)
        has_speech = len(timestamps) > 0

        if timestamps:
            total_speech_ms = sum(
                (ts["end"] - ts["start"]) for ts in timestamps
            ) / 16  # 16 samples per ms at 16kHz
            logger.debug(
                "Silero VAD: %d speech segments, %.0fms total speech",
                len(timestamps), total_speech_ms,
            )
        else:
            logger.debug("Silero VAD: no speech detected")

        return has_speech
    except Exception as exc:
        logger.debug("Silero VAD check failed: %s", exc)
        return None


def _has_speech_energy_rms(audio_path: Path, threshold: float = _MIN_RMS_ENERGY) -> bool:
    """Fallback: check if a PCM WAV file has enough RMS energy for speech."""
    try:
        with open(audio_path, "rb") as f:
            header = f.read(44)
            if len(header) < 44 or header[:4] != b"RIFF":
                return True
            bits_per_sample = struct.unpack_from("<H", header, 34)[0]
            raw = f.read()
        if bits_per_sample == 32:
            sample_size = 4
            fmt = "i"
            scale = 1.0 / (1 << 16)
        elif bits_per_sample == 16:
            sample_size = 2
            fmt = "h"
            scale = 1.0
        else:
            return True
        n_samples = len(raw) // sample_size
        if n_samples == 0:
            return False
        samples = struct.unpack(f"<{n_samples}{fmt}", raw[: n_samples * sample_size])
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5 * scale
        logger.debug(
            "RMS energy fallback: %.1f (threshold: %.1f, bits=%d)",
            rms, threshold, bits_per_sample,
        )
        return rms >= threshold
    except Exception:
        return True


def _is_hallucination(text: str) -> bool:
    """Return True if the transcript looks like a whisper hallucination."""
    cleaned = text.strip()
    if not cleaned:
        return True
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern.search(cleaned):
            return True
    # Check for excessive repetition of any short segment.
    words = cleaned.split()
    if len(words) >= 4:
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.25:
            return True
    return False
