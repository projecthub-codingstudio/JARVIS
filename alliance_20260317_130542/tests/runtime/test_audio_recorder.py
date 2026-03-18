"""Tests for microphone recording helper."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jarvis.runtime.audio_recorder import AudioRecorder


class TestAudioRecorder:
    def test_builds_rec_command_and_returns_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        output = tmp_path / "ptt.wav"
        captured: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["cmd"] = cmd
            output.write_bytes(b"RIFF")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        recorder = AudioRecorder(binary_path="/opt/homebrew/bin/rec", duration_seconds=3)
        result = recorder.record_once(output)

        assert result == output
        assert captured["cmd"] == [
            "/opt/homebrew/bin/rec", "-q", "-c", "1", "-r", "16000",
            str(output), "trim", "0", "3",
        ]

    def test_nonzero_exit_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        output = tmp_path / "ptt.wav"

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "device busy")

        monkeypatch.setattr(subprocess, "run", fake_run)
        recorder = AudioRecorder(binary_path="/opt/homebrew/bin/rec")

        with pytest.raises(RuntimeError):
            recorder.record_once(output)
