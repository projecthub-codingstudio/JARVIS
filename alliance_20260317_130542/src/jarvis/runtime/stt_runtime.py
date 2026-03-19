"""Local speech-to-text runtime using whisper.cpp."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from jarvis.runtime.model_router import ModelRouter

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
