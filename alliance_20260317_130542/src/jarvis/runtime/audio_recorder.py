"""Local audio recording helpers for push-to-talk voice mode.

VAD (Voice Activity Detection) is deferred to Phase 2.
Current approach: fixed-duration recording via afrecord/rec/ffmpeg.
Phase 2 will integrate Silero VAD for silence-aware recording.
"""

from __future__ import annotations

import logging
import platform
import unicodedata
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


def _nfc(text: str) -> str:
    """Normalize Unicode to NFC for reliable string comparison.

    macOS APIs (Swift/AVFoundation) often return NFD-encoded Korean,
    while ffmpeg and Python literals use NFC.  Normalizing both sides
    to NFC ensures 'Revelator통합' matches regardless of source.
    """
    return unicodedata.normalize("NFC", text)


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


# Virtual/loopback devices that should never be auto-selected as microphone
_VIRTUAL_DEVICE_KEYWORDS = frozenset({
    "blackhole", "loopback", "soundflower", "obs virtual",
    "ndi audio", "boom", "eqmac", "steam streaming",
    "jump desktop", "parallels",
})


def _find_system_default_audio_index(ffmpeg_binary: str) -> str:
    """Find the macOS system default audio input device index for ffmpeg.

    Queries the system default input device name via AVFoundation (swift),
    then resolves it to an ffmpeg AVFoundation index.  Falls back to the
    first non-virtual audio device if the system default cannot be resolved.
    """
    # 1) Get system default input device name via AVFoundation
    default_name: str | None = None
    swift_binary = shutil.which("swift")
    if swift_binary:
        try:
            result = subprocess.run(
                [
                    swift_binary, "-e",
                    "import AVFoundation; "
                    "if let d = AVCaptureDevice.default(for: .audio) "
                    "{ print(d.localizedName) }",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                default_name = result.stdout.strip().splitlines()[0]
                logger.info("macOS default input device: %s", default_name)
        except (subprocess.TimeoutExpired, OSError):
            pass

    # 2) Get ffmpeg device list
    try:
        list_result = subprocess.run(
            [ffmpeg_binary, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        logger.warning("Cannot list audio devices; using index 0 as last resort")
        return "0"

    devices = _parse_avfoundation_audio_devices(list_result.stderr)
    if not devices:
        return "0"

    # 3) Match system default by name (Unicode-normalized)
    if default_name:
        default_needle = _nfc(default_name).lower()
        for name, index in devices.items():
            if _nfc(name).lower() == default_needle:
                logger.info("System default '%s' → ffmpeg index %s", default_name, index)
                return index
        for name, index in devices.items():
            if default_needle in _nfc(name).lower():
                logger.info("System default '%s' ~ ffmpeg index %s (%s)", default_name, index, name)
                return index

    # 4) Fallback: first non-virtual audio device
    for name, index in devices.items():
        if not any(kw in name.lower() for kw in _VIRTUAL_DEVICE_KEYWORDS):
            logger.info("Auto-selected non-virtual device: %s (index %s)", name, index)
            return index

    # 5) Last resort
    first_index = next(iter(devices.values()))
    logger.warning("All devices appear virtual; using first: index %s", first_index)
    return first_index


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

        On macOS with ffmpeg/AVFoundation, records extra time at the start
        to absorb device initialization delay, then trims the silent lead-in.

        Raises RuntimeError if no recorder binary is found or recording fails.
        """
        output = output_path.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        binary = self._resolve_binary()
        if binary is None:
            raise RuntimeError("No supported recorder found (afrecord/rec/ffmpeg)")

        is_ffmpeg_darwin = Path(binary).name == "ffmpeg" and platform.system() == "Darwin"

        # Record extra 3s at the beginning to absorb AVFoundation
        # device initialization delay (first-time TCC + device warmup).
        raw_output = output.with_suffix(".raw.wav") if is_ffmpeg_darwin else output
        cmd = self._build_command(binary, raw_output)

        if is_ffmpeg_darwin:
            cmd = self._extend_duration(cmd, extra_seconds=3)

        logger.warning("Recording cmd: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=max(30, self._duration_seconds + 15),
            check=False,
        )
        logger.warning("Recording exit=%d stderr=%s", result.returncode, result.stderr.strip()[:300])
        if result.returncode != 0:
            raise RuntimeError(_summarize_recording_error(result.stderr))

        # Trim the silent device-warmup lead-in
        if is_ffmpeg_darwin and raw_output.exists():
            self._trim_leadin(binary, raw_output, output)
            raw_output.unlink(missing_ok=True)

        _normalize_audio(output)
        return output

    @staticmethod
    def _extend_duration(cmd: list[str], extra_seconds: int) -> list[str]:
        """Return a copy of cmd with -t value increased by extra_seconds."""
        cmd = list(cmd)
        try:
            t_idx = cmd.index("-t")
            original = int(cmd[t_idx + 1])
            cmd[t_idx + 1] = str(original + extra_seconds)
        except (ValueError, IndexError):
            pass
        return cmd

    @staticmethod
    def _trim_leadin(binary: str, raw_path: Path, output_path: Path) -> None:
        """Trim silent lead-in from recording.

        Skips the first 3 seconds (AVFoundation warmup) and keeps
        the rest as the actual recording.
        """
        try:
            result = subprocess.run(
                [
                    binary,
                    "-ss", "3",
                    "-i", str(raw_path),
                    "-c", "copy",
                    "-y", str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode != 0 or not output_path.exists():
                # Fallback: use raw recording as-is
                logger.warning("Trim failed, using raw recording")
                raw_path.rename(output_path)
        except (subprocess.TimeoutExpired, OSError):
            raw_path.rename(output_path)

    def _resolve_binary(self) -> str | None:
        if self._binary_path is not None:
            return self._binary_path
        # On macOS, prefer ffmpeg (AVFoundation) for reliable channel/sample-rate
        # control.  Falls back to afrecord/rec only when ffmpeg is absent.
        if platform.system() == "Darwin":
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
            device = self._resolve_ffmpeg_device(binary)
            if device is None:
                if self._input_device is not None:
                    raise RuntimeError(
                        f"마이크 장치 '{self._input_device}'을(를) 찾을 수 없습니다. "
                        "시스템 설정에서 입력 장치를 확인해 주세요."
                    )
                device = _find_system_default_audio_index(binary)
            return [
                binary,
                "-f",
                "avfoundation",
                "-i",
                f":{device}",
                "-t",
                str(self._duration_seconds),
                # Downmix all input channels to mono — works for stereo,
                # 5.1 (Revelator통합), and any channel layout.  Replaces
                # the previous pan=mono|c0=c0 which only took channel 0.
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
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg -list_devices timed out (30s); cannot resolve device '%s'", self._input_device)
            return None
        except OSError as e:
            logger.warning("ffmpeg -list_devices failed: %s", e)
            return None

        devices = _parse_avfoundation_audio_devices(result.stderr)
        logger.debug("AVFoundation audio devices found: %s", devices)

        if not devices:
            logger.warning("No AVFoundation audio devices parsed from ffmpeg output")
            return None

        needle = _nfc(self._input_device).lower()

        # 1) Exact match (case-insensitive, Unicode-normalized)
        for name, index in devices.items():
            if _nfc(name).lower() == needle:
                logger.info("Device '%s' resolved to index %s (exact match)", self._input_device, index)
                return index
        # 2) Partial match — prefer longest device name to avoid
        #    e.g. "Revelator" (MIDI) matching before "Revelator통합" (audio)
        partial_matches: list[tuple[str, str]] = []
        for name, index in devices.items():
            if needle in _nfc(name).lower():
                partial_matches.append((name, index))
        if partial_matches:
            best = max(partial_matches, key=lambda x: len(x[0]))
            logger.info("Device '%s' resolved to index %s (partial match: '%s')", self._input_device, best[1], best[0])
            return best[1]

        logger.warning(
            "Device '%s' not found in AVFoundation devices: %s",
            self._input_device, list(devices.keys()),
        )
        return None


def _normalize_audio(audio_path: Path, min_rms_threshold: float = 0.005) -> None:
    """Normalize audio peak level in-place using sox.

    Only normalizes when the recording contains meaningful signal (RMS above
    *min_rms_threshold* on a 0-1 scale).  This prevents amplifying background
    noise or static to full scale when the microphone captured no speech.
    """
    sox_binary = _find_binary("sox")
    if sox_binary is None:
        return

    # Pre-check: measure RMS before normalizing to avoid amplifying noise.
    try:
        stat_result = subprocess.run(
            [sox_binary, str(audio_path), "-n", "stat"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in stat_result.stderr.splitlines():
            if "RMS     amplitude" in line:
                rms = float(line.split()[-1])
                if rms < min_rms_threshold:
                    logger.debug(
                        "Normalization skipped: RMS %.6f below threshold %.3f (likely noise)",
                        rms, min_rms_threshold,
                    )
                    return
                break
    except (subprocess.TimeoutExpired, OSError, ValueError):
        pass  # On error, proceed with normalization.

    normalized = audio_path.with_suffix(".norm.wav")
    try:
        result = subprocess.run(
            [sox_binary, "--norm", str(audio_path), str(normalized)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0 and normalized.exists():
            normalized.replace(audio_path)
            logger.debug("Audio normalized via sox --norm")
        else:
            logger.debug("sox normalization skipped: %s", result.stderr.strip()[:100])
    except (subprocess.TimeoutExpired, OSError):
        pass
    finally:
        normalized.unlink(missing_ok=True)
