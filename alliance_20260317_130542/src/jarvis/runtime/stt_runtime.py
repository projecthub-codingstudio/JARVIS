"""Local speech-to-text runtime using whisper.cpp."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jarvis.runtime.model_router import ModelRouter

_DEFAULT_BINARY_CANDIDATES = ("whisper-cli", "main")
_DEFAULT_MEMORY_GB = 2.0


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
        language: str = "auto",
        model_router: ModelRouter | None = None,
        estimated_memory_gb: float = _DEFAULT_MEMORY_GB,
    ) -> None:
        self._binary_path = binary_path
        self._model_path = model_path
        self._language = language
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

        binary = self._resolve_binary()
        if binary is None:
            raise RuntimeError("whisper.cpp binary not found and no transcript fallback available")
        if self._model_path is None:
            raise RuntimeError("STT model path is required for whisper.cpp transcription")

        if self._model_router is not None:
            granted = self._model_router.request_load("stt-whispercpp", self._estimated_memory_gb)
            if not granted:
                raise RuntimeError("ModelRouter denied loading whisper.cpp STT")

        try:
            result = subprocess.run(
                [
                    binary,
                    "-m",
                    str(self._model_path),
                    "-f",
                    str(path),
                    "-l",
                    self._language,
                    "-nt",
                ],
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
        return text

    def _resolve_binary(self) -> str | None:
        if self._binary_path is not None:
            return self._binary_path
        for candidate in _DEFAULT_BINARY_CANDIDATES:
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved
        return None
