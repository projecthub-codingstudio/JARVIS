"""Local text-to-speech runtime for Phase 2 voice mode."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jarvis.runtime.model_router import ModelRouter

_DEFAULT_MEMORY_GB = 2.0


class LocalTTSRuntime:
    """Local TTS wrapper with macOS `say` support and test fallback."""

    def __init__(
        self,
        *,
        voice: str = "Sora",
        backend: str = "say",
        binary_path: str | None = None,
        model_router: ModelRouter | None = None,
        estimated_memory_gb: float = _DEFAULT_MEMORY_GB,
    ) -> None:
        self._voice = voice
        self._backend = backend
        self._binary_path = binary_path
        self._model_router = model_router
        self._estimated_memory_gb = estimated_memory_gb

    def synthesize(self, text: str, output_path: Path) -> Path:
        """Synthesize text to an output file."""
        clean_text = text.strip()
        if not clean_text:
            raise RuntimeError("Cannot synthesize empty text")

        path = output_path.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Deterministic test fallback.
        if path.suffix.lower() == ".txt":
            path.write_text(clean_text, encoding="utf-8")
            return path

        if self._backend != "say":
            raise RuntimeError(f"Unsupported TTS backend: {self._backend}")

        binary = self._binary_path or shutil.which("say")
        if binary is None:
            raise RuntimeError("macOS `say` command not found")

        if self._model_router is not None:
            granted = self._model_router.request_load("tts-local", self._estimated_memory_gb)
            if not granted:
                raise RuntimeError("ModelRouter denied loading local TTS")

        try:
            result = subprocess.run(
                [
                    binary,
                    "-v",
                    self._voice,
                    "-o",
                    str(path),
                    clean_text,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        finally:
            if self._model_router is not None:
                self._model_router.release("tts-local")

        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            raise RuntimeError(f"TTS synthesis failed: {stderr}")

        return path
