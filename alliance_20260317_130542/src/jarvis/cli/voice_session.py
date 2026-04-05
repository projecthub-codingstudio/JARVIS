"""Voice session orchestration for STT-first CLI mode.

Supports two activation modes:
  1. Push-to-talk: manual trigger → record → STT → LLM → TTS
  2. Wake word: "Hey JARVIS" → auto-record → STT → LLM → TTS → resume listening
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
import tempfile

from jarvis.contracts import ConversationTurn
from jarvis.core.orchestrator import Orchestrator
from jarvis.runtime.audio_recorder import AudioRecorder, check_microphone_access
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime

logger = logging.getLogger(__name__)


class VoiceSession:
    """Run voice interactions via push-to-talk or wake word activation.

    Modes:
      - Push-to-talk: call record_and_handle_once() directly
      - Wake word: call start_wake_word_loop() for "Hey JARVIS" activation
    """

    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        stt_runtime: WhisperCppSTT,
        tts_runtime: LocalTTSRuntime | None = None,
        recorder: AudioRecorder | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._stt_runtime = stt_runtime
        self._tts_runtime = tts_runtime
        self._recorder = recorder
        self._mic_checked = False
        self._wake_detector = None

    def handle_audio_file(self, audio_path: Path) -> ConversationTurn:
        """Transcribe an audio file and run a normal JARVIS turn."""
        transcript = self._stt_runtime.transcribe(audio_path).strip()
        if not transcript:
            raise RuntimeError("Empty transcript")
        return self._orchestrator.handle_turn(transcript)

    def handle_audio_file_with_tts(
        self,
        audio_path: Path,
        *,
        output_path: Path,
    ) -> tuple[ConversationTurn, Path]:
        """Run STT -> turn handling -> TTS output."""
        if self._tts_runtime is None:
            raise RuntimeError("TTS runtime not configured")
        turn = self.handle_audio_file(audio_path)
        synthesized = self._tts_runtime.synthesize(turn.assistant_output, output_path)
        return turn, synthesized

    def record_and_handle_once(self) -> ConversationTurn:
        """Record one utterance from the microphone and handle it.

        Performs a one-time microphone permission check on first call.
        """
        transcript = self.record_and_transcribe_once()
        return self._orchestrator.handle_turn(transcript)

    def record_and_handle_once_stream(
        self,
        *,
        on_token: Callable[[str], None] | None = None,
    ) -> ConversationTurn:
        """Record, transcribe, and stream the LLM response.

        Tokens are passed to on_token callback for real-time display.
        The full ConversationTurn is returned after generation completes
        (for TTS or other post-processing that needs the full text).
        """
        transcript = self.record_and_transcribe_once()

        stream_fn = getattr(self._orchestrator, "handle_turn_stream", None)
        if not callable(stream_fn):
            return self._orchestrator.handle_turn(transcript)

        turn: ConversationTurn | None = None
        for item in stream_fn(transcript):
            if isinstance(item, str):
                if on_token is not None:
                    on_token(item)
            else:
                turn = item

        if turn is None:
            return self._orchestrator.handle_turn(transcript)
        return turn

    def record_and_transcribe_once(self) -> str:
        """Record one utterance and return only the transcript."""
        if self._recorder is None:
            raise RuntimeError("Audio recorder not configured")
        if not self._mic_checked:
            if not check_microphone_access():
                raise RuntimeError(
                    "마이크 접근이 거부되었습니다. "
                    "시스템 설정 > 개인정보 보호 > 마이크에서 권한을 허용해 주세요."
                )
            self._mic_checked = True
        with tempfile.TemporaryDirectory(prefix="jarvis-voice-") as tmpdir:
            audio_path = Path(tmpdir) / "ptt.wav"
            self._recorder.record_once(audio_path)
            # Preserve recording for inspection
            debug_copy = Path("/tmp/jarvis_last_recording.wav")
            try:
                import shutil
                shutil.copy2(audio_path, debug_copy)
                logger.warning("Recording saved: %s", debug_copy)
            except OSError:
                pass
            transcript = self._stt_runtime.transcribe(audio_path).strip()
            if not transcript:
                raise RuntimeError("Empty transcript")
            return transcript

    # --- Wake Word Mode ---

    def start_wake_word_loop(
        self,
        *,
        on_wake: Callable[[], None] | None = None,
        on_transcript: Callable[[str], None] | None = None,
        on_response: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        device_index: int | None = None,
    ) -> None:
        """Start continuous wake word listening.

        When "Hey JARVIS" is detected:
          1. Calls on_wake() to signal activation
          2. Records audio (push-to-talk duration)
          3. Transcribes → calls on_transcript(text)
          4. LLM → generates response
          5. Calls on_response(text) + TTS playback
          6. Resumes listening for next wake word

        Args:
            on_wake: Called when wake word detected (e.g., play chime)
            on_transcript: Called with the STT transcript for display
            on_response: Called with LLM response text
            on_error: Called with error message on failure
        """
        try:
            from jarvis.runtime.wake_word import WakeWordDetector, is_available
        except ImportError:
            if on_error:
                on_error("OpenWakeWord가 설치되지 않았습니다.")
            return

        if not is_available():
            if on_error:
                on_error("Wake word 의존성(pyaudio, openwakeword)이 설치되지 않았습니다.")
            return

        def _handle_wake():
            """Called in the wake word thread when 'Hey JARVIS' detected."""
            logger.info("Wake word activated — starting voice interaction")

            # Pause detection (not stop — we're in the same thread!)
            if self._wake_detector is not None:
                self._wake_detector.pause()

            if on_wake is not None:
                try:
                    on_wake()
                except Exception:
                    pass

            try:
                # Record → Transcribe → LLM → TTS
                transcript = self.record_and_transcribe_once()
                logger.info("Transcript: %s", transcript[:80])

                if on_transcript is not None:
                    on_transcript(transcript)

                turn = self._orchestrator.handle_turn(transcript)
                response_text = turn.assistant_output or ""

                if on_response is not None:
                    on_response(response_text)

                # TTS playback
                if self._tts_runtime is not None and response_text:
                    self._speak(response_text)

            except RuntimeError as exc:
                msg = str(exc)
                logger.warning("Wake word interaction failed: %s", msg)
                if on_error is not None:
                    on_error(msg)
            except Exception as exc:
                logger.warning("Wake word interaction error: %s", exc)
                if on_error is not None:
                    on_error(str(exc))

            # Resume detection
            if self._wake_detector is not None:
                self._wake_detector.resume()

        self._wake_detector = WakeWordDetector(
            on_wake=_handle_wake,
            device_index=device_index,
        )
        self._wake_detector.start()
        logger.info("Wake word loop started — say 'Hey JARVIS' to activate")

    def stop_wake_word_loop(self) -> None:
        """Stop the wake word listening loop."""
        if self._wake_detector is not None:
            self._wake_detector.stop()
            self._wake_detector = None
            logger.info("Wake word loop stopped")

    @property
    def wake_word_active(self) -> bool:
        return self._wake_detector is not None and self._wake_detector.is_running

    def _speak(self, text: str) -> None:
        """Synthesize and play TTS audio."""
        if self._tts_runtime is None:
            return
        try:
            clean = _strip_markup_for_tts(text)
            if not clean.strip():
                return
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
                audio_path = Path(f.name)
            self._tts_runtime.synthesize(clean, audio_path)
            subprocess.run(
                ["afplay", str(audio_path)],
                timeout=60, check=False,
                capture_output=True,
            )
            audio_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("TTS playback failed: %s", exc)


import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"\*(.+?)\*")
_BRACKET_CITATION_RE = re.compile(r"\[(\d+)\]")
_BRACKET_FILE_RE = re.compile(r"\[([^\]]*\.\w{2,5})\]")
_BRACKET_SOURCE_RE = re.compile(r"\[([^\]]+)\]\s*파일")
_CODE_INLINE_RE = re.compile(r"`([^`]+)`")
_HEADING_RE = re.compile(r"^#{1,4}\s+", re.MULTILINE)
_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")


def _strip_markup_for_tts(text: str) -> str:
    """Remove markdown/markup tags for natural TTS reading."""
    t = text
    t = _BOLD_RE.sub(r"\1", t)
    t = _ITALIC_RE.sub(r"\1", t)
    t = _BRACKET_CITATION_RE.sub("", t)
    t = _BRACKET_SOURCE_RE.sub(r"\1 파일", t)
    t = _BRACKET_FILE_RE.sub(r"\1", t)
    t = _CODE_INLINE_RE.sub(r"\1", t)
    t = _HEADING_RE.sub("", t)
    t = _MARKDOWN_LINK_RE.sub(r"\1", t)
    # Clean up extra whitespace
    t = re.sub(r"  +", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
