"""Tests for microphone recording helper."""
from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path

import pytest

from jarvis.runtime.audio_recorder import (
    AudioRecorder,
    _parse_avfoundation_audio_devices,
    check_microphone_access,
)


class TestAudioRecorder:
    def test_builds_rec_command_and_returns_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        output = tmp_path / "ptt.wav"
        captured: dict[str, object] = {}

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured["cmd"] = cmd
            output.write_bytes(b"RIFF")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr("jarvis.runtime.audio_recorder._normalize_audio", lambda p: None)
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

    def test_device_open_error_is_human_readable(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        output = tmp_path / "ptt.wav"

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, "", "Error opening input file :device\nInput/output error")

        monkeypatch.setattr(subprocess, "run", fake_run)
        recorder = AudioRecorder(binary_path="/opt/homebrew/bin/ffmpeg", input_device="bad-device")

        with pytest.raises(RuntimeError, match="마이크 장치.*찾을 수 없습니다"):
            recorder.record_once(output)

    def test_builds_ffmpeg_command_with_selected_input_device(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        output = tmp_path / "ptt.wav"
        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.append(cmd)
            if "-list_devices" in cmd:
                stderr = """
                [AVFoundation indev @ 0x123] AVFoundation audio devices:
                [AVFoundation indev @ 0x123] [0] MacBook Pro Microphone
                [AVFoundation indev @ 0x123] [1] USB Audio Device
                """
                return subprocess.CompletedProcess(cmd, 0, "", stderr)
            # Create the output file referenced in the command
            for arg in cmd:
                if arg.endswith(".wav"):
                    Path(arg).write_bytes(b"RIFF")
            output.write_bytes(b"RIFF")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr("jarvis.runtime.audio_recorder._normalize_audio", lambda p: None)
        recorder = AudioRecorder(
            binary_path="/opt/homebrew/bin/ffmpeg",
            input_device="USB Audio Device",
            duration_seconds=3,
        )

        result = recorder.record_once(output)

        assert result == output
        # Find the recording command (has avfoundation -i)
        record_cmd = [c for c in captured if "-f" in c and "avfoundation" in c and "-list_devices" not in c][0]
        assert ":1" in record_cmd        # correct device index
        assert "-t" in record_cmd
        assert "-ac" in record_cmd
        # Duration is extended by 3s for warmup: 3 + 3 = 6
        t_idx = record_cmd.index("-t")
        assert record_cmd[t_idx + 1] == "6"

    def test_parse_avfoundation_audio_devices(self) -> None:
        stderr = """
        [AVFoundation indev @ 0x123] AVFoundation video devices:
        [AVFoundation indev @ 0x123] [0] FaceTime HD Camera
        [AVFoundation indev @ 0x123] AVFoundation audio devices:
        [AVFoundation indev @ 0x123] [0] MacBook Pro Microphone
        [AVFoundation indev @ 0x123] [1] USB Audio Device
        """

        assert _parse_avfoundation_audio_devices(stderr) == {
            "MacBook Pro Microphone": "0",
            "USB Audio Device": "1",
        }

    def test_partial_match_prefers_longest_device_name(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When 'Revelator통합' is requested, should match index 13 (not 'Revelator' at 6)."""
        output = tmp_path / "ptt.wav"
        captured: list[list[str]] = []

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.append(cmd)
            if "-list_devices" in cmd:
                stderr = (
                    "[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
                    "[AVFoundation indev @ 0x1] [6] Revelator\n"
                    "[AVFoundation indev @ 0x1] [11] Revelator Stream Mix B\n"
                    "[AVFoundation indev @ 0x1] [13] Revelator통합\n"
                    "[AVFoundation indev @ 0x1] [16] Revelator Stream Mix A\n"
                )
                return subprocess.CompletedProcess(cmd, 0, "", stderr)
            output.write_bytes(b"RIFF")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr("jarvis.runtime.audio_recorder._normalize_audio", lambda p: None)
        recorder = AudioRecorder(
            binary_path="/opt/homebrew/bin/ffmpeg",
            input_device="Revelator통합",
            duration_seconds=3,
        )

        recorder.record_once(output)

        # Should use index 13 (Revelator통합), NOT 6 (Revelator)
        assert ":13" in captured[-1]

    def test_unicode_nfd_nfc_mismatch_resolves_correctly(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Device name in NFD (from Swift) must match NFC (from ffmpeg)."""
        output = tmp_path / "ptt.wav"
        captured: list[list[str]] = []
        # Swift sends NFD-encoded Korean
        nfd_name = unicodedata.normalize("NFD", "Revelator통합")
        # ffmpeg returns NFC-encoded Korean
        nfc_name = unicodedata.normalize("NFC", "Revelator통합")

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured.append(cmd)
            if "-list_devices" in cmd:
                stderr = (
                    f"[AVFoundation indev @ 0x1] AVFoundation audio devices:\n"
                    f"[AVFoundation indev @ 0x1] [6] Revelator\n"
                    f"[AVFoundation indev @ 0x1] [13] {nfc_name}\n"
                )
                return subprocess.CompletedProcess(cmd, 0, "", stderr)
            output.write_bytes(b"RIFF")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr("jarvis.runtime.audio_recorder._normalize_audio", lambda p: None)
        recorder = AudioRecorder(
            binary_path="/opt/homebrew/bin/ffmpeg",
            input_device=nfd_name,  # NFD from Swift
            duration_seconds=3,
        )

        recorder.record_once(output)

        assert ":13" in captured[-1]

    def test_device_resolution_timeout_raises_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When device is specified but resolution times out, raise error."""
        output = tmp_path / "ptt.wav"

        def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "-list_devices" in cmd:
                raise subprocess.TimeoutExpired(cmd, 30)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        recorder = AudioRecorder(
            binary_path="/opt/homebrew/bin/ffmpeg",
            input_device="SomeDevice",
            duration_seconds=3,
        )

        with pytest.raises(RuntimeError, match="마이크 장치.*찾을 수 없습니다"):
            recorder.record_once(output)

    def test_named_device_requires_ffmpeg_for_afrecord(self, tmp_path: Path) -> None:
        recorder = AudioRecorder(
            binary_path="/usr/bin/afrecord",
            input_device="BuiltInMicrophoneDevice",
        )

        with pytest.raises(RuntimeError, match="requires the `ffmpeg` recorder"):
            recorder.record_once(tmp_path / "ptt.wav")

    def test_named_device_requires_ffmpeg_for_rec(self, tmp_path: Path) -> None:
        recorder = AudioRecorder(
            binary_path="/opt/homebrew/bin/rec",
            input_device="BuiltInMicrophoneDevice",
        )

        with pytest.raises(RuntimeError, match="requires the `ffmpeg` recorder"):
            recorder.record_once(tmp_path / "ptt.wav")


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
