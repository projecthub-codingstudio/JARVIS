"""Tests for governor resource sampling fallbacks."""

from __future__ import annotations

from jarvis.core.governor import Governor


class TestGovernor:
    def test_select_runtime_tolerates_psutil_oserror(self, monkeypatch) -> None:
        import psutil

        monkeypatch.setattr(psutil, "virtual_memory", lambda: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "swap_memory", lambda: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=0.1: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "sensors_battery", lambda: (_ for _ in ()).throw(OSError()))

        decision = Governor().select_runtime("balanced")

        assert decision.tier == "balanced"
        assert decision.model_id == "qwen3:30b-a3b"
