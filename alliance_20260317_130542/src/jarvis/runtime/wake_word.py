"""Wake Word Detector — "Hey JARVIS" activation via OpenWakeWord.

Listens to microphone audio and triggers a callback when the wake
word is detected. Uses OpenWakeWord with the pre-trained "hey_jarvis"
model for accurate, low-latency detection.

Usage:
    detector = WakeWordDetector(on_wake=my_callback)
    detector.start()   # Starts background listening
    detector.stop()    # Stops listening

The detector runs in a background thread and processes audio in
80ms chunks (1280 samples at 16kHz). Detection threshold defaults
to 0.5 (adjustable).
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_CHUNK_SAMPLES = 1280  # 80ms at 16kHz
_DEFAULT_THRESHOLD = 0.5
_DEFAULT_MODEL = "hey_jarvis_v0.1"


class WakeWordDetector:
    """Background wake word detector using OpenWakeWord.

    Listens to the default microphone and calls `on_wake` when
    "Hey JARVIS" is detected above the confidence threshold.
    """

    def __init__(
        self,
        *,
        on_wake: Callable[[], None],
        model_name: str = _DEFAULT_MODEL,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> None:
        self._on_wake = on_wake
        self._model_name = model_name
        self._threshold = threshold
        self._running = False
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start background wake word listening."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="wake-word",
        )
        self._thread.start()
        logger.info("Wake word detector started (model=%s, threshold=%.2f)",
                     self._model_name, self._threshold)

    def stop(self) -> None:
        """Stop wake word listening."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("Wake word detector stopped")

    def _listen_loop(self) -> None:
        """Background thread: capture audio and run wake word detection."""
        try:
            import pyaudio
            from openwakeword.model import Model
        except ImportError as exc:
            logger.warning("Wake word dependencies missing: %s", exc)
            self._running = False
            return

        try:
            oww_model = Model(
                wakeword_models=[self._model_name],
                inference_framework="onnx",
            )
        except Exception as exc:
            logger.warning("Wake word model load failed: %s", exc)
            self._running = False
            return

        audio = None
        stream = None
        try:
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=_SAMPLE_RATE,
                input=True,
                frames_per_buffer=_CHUNK_SAMPLES,
            )

            logger.info("Microphone stream open — listening for 'Hey JARVIS'")

            while self._running:
                try:
                    pcm = stream.read(_CHUNK_SAMPLES, exception_on_overflow=False)
                except OSError:
                    continue

                # Run prediction
                prediction = oww_model.predict_clip(pcm)

                # Check for wake word activation
                for model_name, scores in prediction.items():
                    if any(score >= self._threshold for score in scores):
                        logger.info("Wake word detected: %s (score=%.3f)",
                                     model_name, max(scores))
                        oww_model.reset()  # Reset to avoid repeated triggers
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


def is_available() -> bool:
    """Check if wake word detection dependencies are installed."""
    try:
        import pyaudio  # noqa: F401
        import openwakeword  # noqa: F401
        return True
    except ImportError:
        return False
