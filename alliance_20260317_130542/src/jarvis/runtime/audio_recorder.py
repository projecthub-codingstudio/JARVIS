"""Local audio recording helpers for push-to-talk voice mode.

VAD (Voice Activity Detection) is deferred to Phase 2.
Current approach: fixed-duration recording via afrecord/rec/ffmpeg.
Phase 2 will integrate Silero VAD for silence-aware recording.
"""

from __future__ import annotations

import logging
import platform
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_RECORD_SECONDS = 8
_DEFAULT_SAMPLE_RATE = 16000
_COMMON_BINARY_DIRS = (
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)
_AVFOUNDATION_AUDIO_SECTION = "AVFoundation audio devices"


def _summarize_recording_error(stderr: str) -> str:
    """Reduce recorder stderr to a short user-facing message."""
    lowered = stderr.lower()
    if "permission denied" in lowered or "not authorized" in lowered or "tcc" in lowered:
        return "마이크 접근 권한이 없습니다. 시스템 설정 > 개인정보 보호 > 마이크를 확인해 주세요."
    if "input/output error" in lowered or "error opening input" in lowered:
        return "선택한 마이크 장치를 열 수 없습니다. 다른 입력 장치를 선택해 주세요."
    if "no such file or directory" in lowered or "not found" in lowered:
        return "오디오 녹음 백엔드를 찾을 수 없습니다."
    compact = stderr.strip().splitlines()
    if not compact:
        return "녹음에 실패했습니다."
    return compact[-1][:200]


def check_microphone_access() -> bool:
    """Pre-flight check for microphone access on macOS.

    Uses a short afrecord probe to verify TCC microphone permission.
    Returns True if recording is likely to succeed, False otherwise.
    On non-macOS systems, always returns True (no TCC).
    """
    import platform

    if platform.system() != "Darwin":
        return True

    afrecord = shutil.which("afrecord")
    if afrecord is None:
        # No afrecord — can't pre-check, assume OK and let record_once handle it
        return True

    try:
        result = subprocess.run(
            [afrecord, "-f", "WAVE", "-d", "0.1", "/dev/null"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.lower()
            if "permission" in stderr or "denied" in stderr or "tcc" in stderr:
                logger.warning("Microphone access denied — check System Settings > Privacy > Microphone")
                return False
        return True
    except (subprocess.TimeoutExpired, OSError):
        return True


def _find_binary(name: str) -> str | None:
    """Resolve a recorder binary from PATH or common install locations."""
    resolved = shutil.which(name)
    if resolved is not None:
        return resolved
    for directory in _COMMON_BINARY_DIRS:
        candidate = directory / name
        if candidate.exists():
            return str(candidate)
    return None


def _parse_avfoundation_audio_devices(stderr: str) -> dict[str, str]:
    """Return `{device_name: index}` from ffmpeg avfoundation listing stderr."""
    devices: dict[str, str] = {}
    in_audio_section = False
    for raw_line in stderr.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if _AVFOUNDATION_AUDIO_SECTION.lower() in lowered:
            in_audio_section = True
            continue
        if in_audio_section and "avfoundation video devices" in lowered:
            in_audio_section = False
            continue
        if not in_audio_section:
            continue
        match = re.search(r"\[(\d+)\]\s+(.+)$", line)
        if match:
            devices[match.group(2).strip()] = match.group(1)
    return devices


class AudioRecorder:
    """Record a short utterance from the system microphone."""

    def __init__(
        self,
        *,
        binary_path: str | None = None,
        input_device: str | None = None,
        duration_seconds: int = _DEFAULT_RECORD_SECONDS,
        sample_rate_hz: int = _DEFAULT_SAMPLE_RATE,
    ) -> None:
        self._binary_path = binary_path
        self._input_device = input_device.strip() if input_device and input_device.strip() else None
        self._duration_seconds = duration_seconds
        self._sample_rate_hz = sample_rate_hz

    def record_once(self, output_path: Path) -> Path:
        """Record a single utterance to a WAV file.

        Raises RuntimeError if no recorder binary is found or recording fails.
        """
        output = output_path.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        binary = self._resolve_binary()
        if binary is None:
            raise RuntimeError("No supported recorder found (afrecord/rec/ffmpeg)")

        cmd = self._build_command(binary, output)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(30, self._duration_seconds + 5),
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(_summarize_recording_error(result.stderr))
        return output

    def _resolve_binary(self) -> str | None:
        if self._binary_path is not None:
            return self._binary_path
        if self._input_device is not None:
            # Device-specific capture is most reliable via ffmpeg avfoundation.
            resolved = _find_binary("ffmpeg")
            if resolved is not None:
                return resolved
        for candidate in ("afrecord", "rec"):
            resolved = _find_binary(candidate)
            if resolved is not None:
                return resolved
        return None

    def _build_command(self, binary: str, output_path: Path) -> list[str]:
        name = Path(binary).name
        if name == "ffmpeg":
            device = self._resolve_ffmpeg_device(binary) or "default"
            return [
                binary,
                "-f",
                "avfoundation",
                "-i",
                f":{device}",
                "-t",
                str(self._duration_seconds),
                "-ac",
                "1",
                "-ar",
                str(self._sample_rate_hz),
                "-y",
                str(output_path),
            ]
        if name == "afrecord":
            if self._input_device is not None:
                raise RuntimeError("Input device selection currently requires the `ffmpeg` recorder")
            return [
                binary,
                "-f",
                "WAVE",
                "-d",
                str(self._duration_seconds),
                str(output_path),
            ]
        command = [
            binary,
            "-q",
        ]
        if self._input_device is not None:
            raise RuntimeError("Input device selection currently requires the `ffmpeg` recorder")
        command.extend([
            "-c",
            "1",
            "-r",
            str(self._sample_rate_hz),
            str(output_path),
            "trim",
            "0",
            str(self._duration_seconds),
        ])
        return command

    def _resolve_ffmpeg_device(self, binary: str) -> str | None:
        if self._input_device is None:
            return None
        if self._input_device.isdigit():
            return self._input_device

        try:
            result = subprocess.run(
                [
                    binary,
                    "-f",
                    "avfoundation",
                    "-list_devices",
                    "true",
                    "-i",
                    "",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (subprocess.TimeoutExpired, OSError):
            return self._input_device

        devices = _parse_avfoundation_audio_devices(result.stderr)
        for name, index in devices.items():
            if name == self._input_device:
                return index
        for name, index in devices.items():
            if self._input_device.lower() in name.lower():
                return index
        return self._input_device
