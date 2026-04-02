"""Wake Word Detector — "Hey JARVIS" activation via OpenWakeWord.

Listens to microphone audio and triggers a callback when the wake
word is detected. Uses OpenWakeWord with the pre-trained "hey_jarvis"
model.

Key design decisions:
  - Auto-selects a real microphone (skips virtual mixers/aggregates)
  - Resamples from native rate (48kHz) to 16kHz for the model
  - Lower threshold (0.3) for Korean-accented pronunciation tolerance
  - Uses predict() not predict_clip() for streaming chunks
"""
from __future__ import annotations

import logging
import os
import struct
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_CHUNK_SAMPLES = 1280  # 80ms at 16kHz
_DEFAULT_THRESHOLD = 0.2  # Low threshold for Korean accent tolerance
_DEFAULT_MODEL = "hey_jarvis_v0.1"
_CUSTOM_MODEL_PATH = Path.home() / ".jarvis" / "models" / "hey_jarvis_ko.onnx"

# Virtual/aggregate device keywords to skip when auto-selecting
_VIRTUAL_DEVICE_KEYWORDS = (
    "mix", "stream", "blackhole", "eqmac", "boom", "ndi",
    "steam", "jump", "parallels", "통합", "aggregate",
)


def _find_real_microphone(pa) -> int | None:
    """Find a real microphone device, preferring MacBook Pro mic or USB audio."""
    candidates = []
    for i in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(i)
        except Exception:
            continue
        if info["maxInputChannels"] < 1:
            continue
        name = info["name"].lower()
        if any(kw in name for kw in _VIRTUAL_DEVICE_KEYWORDS):
            continue
        candidates.append((i, info["name"], info["maxInputChannels"]))

    if not candidates:
        return None

    # Prefer: MacBook Pro mic > USB > Revelator > others
    for idx, name, _ in candidates:
        if "macbook" in name.lower() and "마이크" in name:
            return idx
    for idx, name, _ in candidates:
        if "usb" in name.lower():
            return idx
    for idx, name, _ in candidates:
        if "revelator" in name.lower():
            return idx

    return candidates[0][0]


class WakeWordDetector:
    """Background wake word detector using OpenWakeWord.

    Listens to a real microphone and calls `on_wake` when
    "Hey JARVIS" is detected above the confidence threshold.
    """

    def __init__(
        self,
        *,
        on_wake: Callable[[], None],
        model_name: str = _DEFAULT_MODEL,
        threshold: float = _DEFAULT_THRESHOLD,
        device_index: int | None = None,
    ) -> None:
        self._on_wake = on_wake
        self._model_names = [model_name] if model_name != _DEFAULT_MODEL else resolve_wakeword_models()
        self._threshold = threshold if threshold != _DEFAULT_THRESHOLD else resolve_wakeword_threshold()
        self._device_index = device_index
        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def pause(self) -> None:
        """Pause detection (safe to call from the wake callback thread)."""
        self._paused = True

    def resume(self) -> None:
        """Resume detection after pause."""
        self._paused = False

    def start(self) -> None:
        """Start background wake word listening."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="wake-word",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop wake word listening."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _listen_loop(self) -> None:
        """Background thread: capture audio and run wake word detection."""
        try:
            import pyaudio
            import numpy as np
            from openwakeword.model import Model
        except ImportError as exc:
            logger.warning("Wake word dependencies missing: %s", exc)
            self._running = False
            return

        try:
            oww_model = Model(
                wakeword_models=self._model_names,
                inference_framework="onnx",
            )
        except Exception as exc:
            logger.warning("Wake word model load failed: %s", exc)
            self._running = False
            return
        logger.info("Wake word models: %s (threshold=%.2f)", self._model_names, self._threshold)

        audio = None
        stream = None
        try:
            audio = pyaudio.PyAudio()

            # Auto-select a real microphone if not specified
            device_idx = self._device_index
            if device_idx is None:
                device_idx = _find_real_microphone(audio)

            if device_idx is not None:
                dev_info = audio.get_device_info_by_index(device_idx)
                device_name = dev_info["name"]
                native_rate = int(dev_info["defaultSampleRate"])
            else:
                device_name = "default"
                native_rate = 48000

            logger.info("Wake word mic: [%s] %s (native %dHz)",
                        device_idx or "default", device_name, native_rate)

            # Open at native sample rate to avoid pyaudio resampling issues
            native_chunk = int(native_rate * _CHUNK_SAMPLES / _SAMPLE_RATE)
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=native_rate,
                input=True,
                input_device_index=device_idx,
                frames_per_buffer=native_chunk,
            )

            logger.info("Listening for 'Hey JARVIS' (threshold=%.2f)", self._threshold)

            while self._running:
                if self._paused:
                    import time
                    time.sleep(0.1)
                    continue

                try:
                    pcm_bytes = stream.read(native_chunk, exception_on_overflow=False)
                except OSError:
                    continue

                # Resample to 16kHz if needed
                if native_rate != _SAMPLE_RATE:
                    pcm_bytes = _resample_pcm(pcm_bytes, native_rate, _SAMPLE_RATE)

                # Convert to numpy int16 array for predict()
                pcm_array = np.frombuffer(pcm_bytes, dtype=np.int16)

                # Run prediction (streaming mode)
                prediction = oww_model.predict(pcm_array)

                # Check for wake word activation
                for model_name in oww_model.prediction_buffer:
                    scores = oww_model.prediction_buffer[model_name]
                    if scores and scores[-1] >= self._threshold:
                        logger.info("Wake word detected: %s (score=%.3f)",
                                    model_name, scores[-1])
                        oww_model.reset()
                        try:
                            self._on_wake()
                        except Exception as exc:
                            logger.warning("Wake callback error: %s", exc)

        except Exception as exc:
            logger.warning("Wake word listener error: %s", exc)
        finally:
            if stream is not None:
                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
            if audio is not None:
                try:
                    audio.terminate()
                except Exception:
                    pass
            self._running = False


def _resample_pcm(pcm_bytes: bytes, from_rate: int, to_rate: int) -> bytes:
    """Simple PCM resampling via linear interpolation."""
    import numpy as np

    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    ratio = to_rate / from_rate
    new_length = int(len(samples) * ratio)
    indices = np.linspace(0, len(samples) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(samples)), samples)
    return resampled.astype(np.int16).tobytes()


def is_available() -> bool:
    """Check if wake word detection dependencies are installed."""
    try:
        import pyaudio  # noqa: F401
        import openwakeword  # noqa: F401
        return True
    except ImportError:
        return False


def resolve_wakeword_models() -> list[str]:
    """Resolve wake word models, preferring a custom Korean model when present."""
    configured = os.getenv("JARVIS_WAKE_MODEL", "").strip()
    models: list[str] = []
    if configured:
        models.append(configured)
    if _CUSTOM_MODEL_PATH.exists():
        models.append(str(_CUSTOM_MODEL_PATH))
    if _DEFAULT_MODEL not in models:
        models.append(_DEFAULT_MODEL)
    return models


def resolve_wakeword_threshold() -> float:
    raw = os.getenv("JARVIS_WAKE_THRESHOLD", "").strip()
    if raw:
        try:
            value = float(raw)
            return min(0.95, max(0.05, value))
        except ValueError:
            logger.warning("Invalid JARVIS_WAKE_THRESHOLD=%r, using default %.2f", raw, _DEFAULT_THRESHOLD)
    return _DEFAULT_THRESHOLD
