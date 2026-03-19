"""Voice session orchestration for STT-first CLI mode.

Phase 1: fixed-duration push-to-talk via afrecord/rec.
Phase 2 (deferred): Silero VAD for silence-aware recording + wake word.
"""

from __future__ import annotations

import logging
from pathlib import Path
import tempfile

from jarvis.contracts import ConversationTurn
from jarvis.core.orchestrator import Orchestrator
from jarvis.runtime.audio_recorder import AudioRecorder, check_microphone_access
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime

logger = logging.getLogger(__name__)


class VoiceSession:
    """Run a single voice interaction from audio file to answer.

    Phase 1 scope: file-based STT, push-to-talk once, STT→LLM→TTS pipeline.
    Phase 2 scope (deferred): Silero VAD, live voice loop with wake word.
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
            return self.handle_audio_file(audio_path)
