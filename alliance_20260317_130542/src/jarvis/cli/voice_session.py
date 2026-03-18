"""Voice session orchestration for STT-first CLI mode."""

from __future__ import annotations

from pathlib import Path
import tempfile

from jarvis.contracts import ConversationTurn
from jarvis.core.orchestrator import Orchestrator
from jarvis.runtime.audio_recorder import AudioRecorder
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime


class VoiceSession:
    """Run a single voice interaction from audio file to answer."""

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
        """Record one utterance from the microphone and handle it."""
        if self._recorder is None:
            raise RuntimeError("Audio recorder not configured")
        with tempfile.TemporaryDirectory(prefix="jarvis-voice-") as tmpdir:
            audio_path = Path(tmpdir) / "ptt.wav"
            self._recorder.record_once(audio_path)
            return self.handle_audio_file(audio_path)
