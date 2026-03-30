"""E2E tests for STT-only voice mode."""
from __future__ import annotations

from pathlib import Path

from jarvis.contracts import ConversationTurn
from jarvis.cli.voice_session import VoiceSession
from jarvis.runtime.audio_recorder import AudioRecorder
from jarvis.runtime.stt_runtime import WhisperCppSTT
from jarvis.runtime.tts_runtime import LocalTTSRuntime


class StubOrchestrator:
    def __init__(self) -> None:
        self.received_input = ""

    def handle_turn(self, user_input: str) -> ConversationTurn:
        self.received_input = user_input
        return ConversationTurn(user_input=user_input, assistant_output="음성 응답", has_evidence=True)


class StubRecorder(AudioRecorder):
    def __init__(self, *, transcript: str) -> None:
        super().__init__(binary_path="/opt/homebrew/bin/rec")
        self._transcript = transcript

    def record_once(self, output_path: Path) -> Path:
        output_path.write_bytes(b"RIFF")
        output_path.with_suffix(".txt").write_text(self._transcript, encoding="utf-8")
        return output_path


class TestVoiceSession:
    def test_audio_file_transcribes_and_runs_turn(self, tmp_path: Path) -> None:
        transcript = tmp_path / "query.txt"
        transcript.write_text("음성으로 질문합니다", encoding="utf-8")

        orchestrator = StubOrchestrator()
        session = VoiceSession(orchestrator=orchestrator, stt_runtime=WhisperCppSTT())
        turn = session.handle_audio_file(transcript)

        assert orchestrator.received_input == "음성으로 질문합니다"
        assert turn.assistant_output == "음성 응답"

    def test_audio_file_round_trip_with_tts(self, tmp_path: Path) -> None:
        transcript = tmp_path / "query.txt"
        transcript.write_text("음성으로 질문합니다", encoding="utf-8")
        output = tmp_path / "answer.txt"

        orchestrator = StubOrchestrator()
        session = VoiceSession(
            orchestrator=orchestrator,
            stt_runtime=WhisperCppSTT(),
            tts_runtime=LocalTTSRuntime(),
        )
        turn, generated = session.handle_audio_file_with_tts(transcript, output_path=output)

        assert turn.assistant_output == "음성 응답"
        assert generated == output
        assert output.read_text(encoding="utf-8") == "음성 응답"

    def test_push_to_talk_once_records_and_handles_turn(self, tmp_path: Path) -> None:
        orchestrator = StubOrchestrator()
        session = VoiceSession(
            orchestrator=orchestrator,
            stt_runtime=WhisperCppSTT(),
            recorder=StubRecorder(transcript="PTT 질문"),
        )

        turn = session.record_and_handle_once()

        assert orchestrator.received_input == "PTT 질문"
        assert turn.assistant_output == "음성 응답"

    def test_push_to_talk_once_can_return_transcript_only(self) -> None:
        orchestrator = StubOrchestrator()
        session = VoiceSession(
            orchestrator=orchestrator,
            stt_runtime=WhisperCppSTT(),
            recorder=StubRecorder(transcript="회의 일정 정리"),
        )

        transcript = session.record_and_transcribe_once()

        assert transcript == "회의 일정 정리"
        assert orchestrator.received_input == ""
