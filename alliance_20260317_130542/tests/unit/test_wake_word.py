"""Tests for wake word detector."""
from __future__ import annotations

from jarvis.runtime.wake_word import WakeWordDetector, is_available


class TestWakeWordDetector:
    def test_creates_with_defaults(self) -> None:
        detector = WakeWordDetector(on_wake=lambda: None)
        assert not detector.is_running

    def test_stop_when_not_running_is_safe(self) -> None:
        detector = WakeWordDetector(on_wake=lambda: None)
        detector.stop()  # Should not raise
        assert not detector.is_running

    def test_is_available_returns_bool(self) -> None:
        result = is_available()
        assert isinstance(result, bool)
