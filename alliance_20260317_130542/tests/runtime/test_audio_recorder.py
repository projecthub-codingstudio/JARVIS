"""Tests for microphone recording helper."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jarvis.runtime.audio_recorder import AudioRecorder, check_microphone_access


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


class TestCheckMicrophoneAccess:
    def test_returns_true_on_non_darwin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("jarvis.runtime.audio_recorder.platform.system", lambda: "Linux")
        assert check_microphone_access() is True

    def test_returns_true_when_no_afrecord(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import shutil as _shutil
        monkeypatch.setattr("jarvis.runtime.audio_recorder.platform.system", lambda: "Darwin")
        monkeypatch.setattr("jarvis.runtime.audio_recorder.shutil.which", lambda x: None)
        assert check_microphone_access() is True

    def test_returns_false_on_permission_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("jarvis.runtime.audio_recorder.platform.system", lambda: "Darwin")
        monkeypatch.setattr("jarvis.runtime.audio_recorder.shutil.which", lambda x: "/usr/bin/afrecord")

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "permission denied by TCC")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert check_microphone_access() is False
