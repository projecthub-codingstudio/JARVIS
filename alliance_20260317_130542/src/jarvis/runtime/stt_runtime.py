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
    ) -> None:
        self._binary_path = binary_path
        self._model_path = model_path
        self._language = language or os.getenv("JARVIS_STT_LANGUAGE", _DEFAULT_LANGUAGE)
        self._model_router = model_router
        self._estimated_memory_gb = estimated_memory_gb

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
        return [
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
    """Check if a PCM WAV file has enough energy to contain speech.

    Reads the WAV header to detect bit-depth (16 or 32-bit PCM) and
    normalises the RMS to a 16-bit scale so the threshold is consistent
    regardless of recorder backend.
    """
    try:
        with open(audio_path, "rb") as f:
            header = f.read(44)
            if len(header) < 44 or header[:4] != b"RIFF":
                return True  # Not a standard WAV — skip check, let whisper decide.
            # WAV header byte 34-35: bits per sample (little-endian uint16).
            bits_per_sample = struct.unpack_from("<H", header, 34)[0]
            raw = f.read()
        if bits_per_sample == 32:
            sample_size = 4
            fmt = "i"  # signed 32-bit int
            scale = 1.0 / (1 << 16)  # normalise to 16-bit range
        elif bits_per_sample == 16:
            sample_size = 2
            fmt = "h"  # signed 16-bit int
            scale = 1.0
        else:
            return True  # Unusual bit depth — skip check.
        n_samples = len(raw) // sample_size
        if n_samples == 0:
            return False
        samples = struct.unpack(f"<{n_samples}{fmt}", raw[: n_samples * sample_size])
        rms = (sum(s * s for s in samples) / n_samples) ** 0.5 * scale
        logger.debug(
            "Audio RMS energy: %.1f (threshold: %.1f, bits=%d)",
            rms, threshold, bits_per_sample,
        )
        return rms >= threshold
    except Exception:
        return True  # On error, let whisper proceed.


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
