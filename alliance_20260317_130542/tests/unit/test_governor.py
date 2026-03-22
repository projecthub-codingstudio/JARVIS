"""Tests for governor resource sampling fallbacks."""

from __future__ import annotations

from datetime import datetime

from jarvis.contracts import SystemStateSnapshot
from jarvis.core.governor import Governor
from jarvis.observability.metrics import MetricName, MetricsCollector


class TestGovernor:
    def test_select_runtime_tolerates_psutil_oserror(self, monkeypatch) -> None:
        import psutil

        monkeypatch.setattr(psutil, "virtual_memory", lambda: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "swap_memory", lambda: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "cpu_percent", lambda interval=0.1: (_ for _ in ()).throw(OSError()))
        monkeypatch.setattr(psutil, "sensors_battery", lambda: (_ for _ in ()).throw(OSError()))

        decision = Governor().select_runtime("balanced")

        assert decision.tier == "balanced"
        assert decision.model_id == "exaone3.5:7.8b"

    def test_idle_ac_power_can_request_deep_tier(self, monkeypatch) -> None:
        from jarvis.core import governor as governor_module

        monkeypatch.setattr(
            governor_module,
            "_sample_system_state",
            lambda: SystemStateSnapshot(
                timestamp=datetime.now(),
                memory_pressure_pct=20.0,
                swap_used_mb=0,
                cpu_pct=10.0,
                thermal_state="nominal",
                on_ac_power=True,
                battery_pct=100,
                indexing_queue_depth=0,
            ),
        )

        governor = Governor()
        decision = governor.select_runtime(governor.suggest_idle_requested_tier())

        assert decision.tier == "deep"
        assert decision.max_retrieved_chunks == 10

    def test_high_ttft_reduces_context_and_chunk_budget(self, monkeypatch) -> None:
        from jarvis.core import governor as governor_module

        monkeypatch.setattr(
            governor_module,
            "_sample_system_state",
            lambda: SystemStateSnapshot(
                timestamp=datetime.now(),
                memory_pressure_pct=25.0,
                swap_used_mb=0,
                cpu_pct=15.0,
                thermal_state="nominal",
                on_ac_power=True,
                battery_pct=100,
                indexing_queue_depth=0,
            ),
        )
        metrics = MetricsCollector()
        metrics.record(MetricName.TTFT_MS, 5000.0)

        decision = Governor(metrics=metrics).select_runtime("balanced")

        assert decision.context_window == 4096
        assert decision.max_retrieved_chunks == 6
