"""Local audio recording helpers for push-to-talk voice mode."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_DEFAULT_RECORD_SECONDS = 8
_DEFAULT_SAMPLE_RATE = 16000


class AudioRecorder:
    """Record a short utterance from the system microphone."""

    def __init__(
        self,
        *,
        binary_path: str | None = None,
        duration_seconds: int = _DEFAULT_RECORD_SECONDS,
        sample_rate_hz: int = _DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._binary_path = binary_path
        self._duration_seconds = duration_seconds
        self._sample_rate_hz = sample_rate_hz

    def record_once(self, output_path: Path) -> Path:
        """Record a single utterance to a WAV file."""
        output = output_path.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        binary = self._resolve_binary()
        if binary is None:
            raise RuntimeError("No supported recorder found (afrecord/rec)")

        cmd = self._build_command(binary, output)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(30, self._duration_seconds + 5),
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()[:200]
            raise RuntimeError(f"Audio recording failed: {stderr}")
        return output

    def _resolve_binary(self) -> str | None:
        if self._binary_path is not None:
            return self._binary_path
        for candidate in ("afrecord", "rec"):
            resolved = shutil.which(candidate)
            if resolved is not None:
                return resolved
        return None

    def _build_command(self, binary: str, output_path: Path) -> list[str]:
        name = Path(binary).name
        if name == "afrecord":
            return [
                binary,
                "-f",
                "WAVE",
                "-d",
                str(self._duration_seconds),
                str(output_path),
            ]
        return [
            binary,
            "-q",
            "-c",
            "1",
            "-r",
            str(self._sample_rate_hz),
            str(output_path),
            "trim",
            "0",
            str(self._duration_seconds),
        ]
