"""Governor — resource and safety governor.

Per Spec Task 0.2: samples system state via psutil and applies
threshold mapping to determine runtime tier.

Thresholds (Spec Section 4.2):
  - balanced -> fast if memory_pressure_pct >= 70
  - deep -> balanced if memory_pressure_pct >= 60
  - any tier -> fast if swap_used_mb >= 2048
  - any tier -> unloaded if swap_used_mb >= 4096
  - any tier -> fast if thermal_state == "serious"
  - any tier -> unloaded if thermal_state == "critical"
  - forbid deep if battery_pct < 30
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from jarvis.contracts import (
    GovernorMode,
    GovernorProtocol,
    RuntimeDecision,
    RuntimeTier,
    SystemStateSnapshot,
    ThermalState,
)
from jarvis.observability.metrics import MetricName, MetricsCollector

logger = logging.getLogger(__name__)

_TTFT_DEGRADE_THRESHOLD_MS = 4000.0
_INDEX_QUEUE_RESTRICT_THRESHOLD = 8
_INDEX_QUEUE_DEGRADED_THRESHOLD = 20


def _sample_system_state() -> SystemStateSnapshot:
    """Sample current system state using psutil and macOS APIs."""
    import psutil
    from datetime import datetime

    try:
        mem = psutil.virtual_memory()
        memory_pressure_pct = mem.percent
    except (OSError, PermissionError):
        memory_pressure_pct = 0.0

    try:
        swap = psutil.swap_memory()
        swap_used_mb = int(swap.used / (1024 * 1024))
    except (OSError, PermissionError):
        swap_used_mb = 0

    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
    except (OSError, PermissionError):
        cpu_pct = 0.0

    # Battery
    on_ac = True
    battery_pct = 100
    try:
        battery = psutil.sensors_battery()
        if battery is not None:
            on_ac = battery.power_plugged or False
            battery_pct = int(battery.percent)
    except (OSError, PermissionError):
        pass

    # Thermal state (macOS)
    thermal: ThermalState = "nominal"
    try:
        result = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True, text=True, timeout=5,
        )
        output = result.stdout.lower()
        if "critical" in output:
            thermal = "critical"
        elif "serious" in output:
            thermal = "serious"
        elif "fair" in output:
            thermal = "fair"
    except Exception:
        pass

    return SystemStateSnapshot(
        timestamp=datetime.now(),
        memory_pressure_pct=memory_pressure_pct,
        swap_used_mb=swap_used_mb,
        cpu_pct=cpu_pct,
        gpu_pct=0.0,  # No portable GPU util on macOS
        thermal_state=thermal,
        on_ac_power=on_ac,
        battery_pct=battery_pct,
        indexing_queue_depth=0,
    )


def _select_tier(state: SystemStateSnapshot, requested: RuntimeTier) -> RuntimeTier:
    """Apply threshold mapping per Spec Task 0.2."""
    tier = requested

    # Swap thresholds (highest priority)
    if state.swap_used_mb >= 4096:
        return "unloaded"
    if state.swap_used_mb >= 2048:
        return "fast"

    # Thermal thresholds
    if state.thermal_state == "critical":
        return "unloaded"
    if state.thermal_state == "serious":
        return "fast"

    # Memory pressure thresholds
    if tier == "deep" and state.memory_pressure_pct >= 60:
        tier = "balanced"
    if tier in ("balanced", "deep") and state.memory_pressure_pct >= 70:
        tier = "fast"

    # Battery constraint
    if tier == "deep" and state.battery_pct < 30:
        tier = "balanced"

    return tier


class Governor:
    """Production governor with real system state sampling.

    Implements GovernorProtocol with actual telemetry.
    """

    def __init__(
        self,
        *,
        memory_limit_gb: float = 16.0,
        metrics: MetricsCollector | None = None,
        indexing_queue_depth_provider: Callable[[], int] | None = None,
    ) -> None:
        self._memory_limit_gb = memory_limit_gb
        self._metrics = metrics
        self._indexing_queue_depth_provider = indexing_queue_depth_provider
        self._last_state: SystemStateSnapshot | None = None

    @property
    def mode(self) -> GovernorMode:
        state = self.sample()
        if state.swap_used_mb >= 4096 or state.thermal_state == "critical":
            return GovernorMode.SHUTDOWN
        if state.memory_pressure_pct >= 70 or state.thermal_state == "serious":
            return GovernorMode.DEGRADED
        if state.memory_pressure_pct >= 60:
            return GovernorMode.RESTRICTED
        return GovernorMode.NORMAL

    def check_resource_budget(self) -> bool:
        state = self.sample()
        return state.memory_pressure_pct < 90 and state.swap_used_mb < 4096

    def should_degrade(self) -> bool:
        state = self.sample()
        return state.memory_pressure_pct >= 70 or state.thermal_state in ("serious", "critical")

    def report_memory_pressure(self) -> float:
        state = self.sample()
        return state.memory_pressure_pct / 100.0

    def sample(self) -> SystemStateSnapshot:
        """Sample current system state."""
        state = _sample_system_state()
        if self._indexing_queue_depth_provider is not None:
            try:
                queue_depth = max(0, int(self._indexing_queue_depth_provider()))
            except Exception:
                queue_depth = 0
            state = SystemStateSnapshot(
                timestamp=state.timestamp,
                memory_pressure_pct=state.memory_pressure_pct,
                swap_used_mb=state.swap_used_mb,
                cpu_pct=state.cpu_pct,
                gpu_pct=state.gpu_pct,
                thermal_state=state.thermal_state,
                on_ac_power=state.on_ac_power,
                battery_pct=state.battery_pct,
                indexing_queue_depth=queue_depth,
            )
        self._last_state = state
        if self._metrics is not None and self._last_state.swap_used_mb > 0:
            self._metrics.increment(MetricName.SWAP_DETECTED_COUNT)
        return self._last_state

    def should_pause_indexing(self) -> bool:
        """Return True when background indexing should pause entirely."""
        state = self.sample()
        if state.thermal_state in ("serious", "critical"):
            return True
        return not state.on_ac_power and state.battery_pct < 30

    def should_backoff_indexing(self) -> bool:
        """Return True when indexing should slow down/back off."""
        state = self.sample()
        if state.thermal_state == "fair":
            return True
        return state.indexing_queue_depth >= _INDEX_QUEUE_RESTRICT_THRESHOLD

    def suggest_idle_requested_tier(self) -> RuntimeTier:
        """Choose the optimistic requested tier before safety downgrades."""
        state = self.sample()
        if (
            state.on_ac_power
            and state.cpu_pct <= 20
            and state.memory_pressure_pct < 60
            and state.swap_used_mb < 1024
            and state.thermal_state in ("nominal", "fair")
            and state.indexing_queue_depth < _INDEX_QUEUE_RESTRICT_THRESHOLD
        ):
            return "deep"
        if not state.on_ac_power and state.battery_pct < 30:
            return "fast"
        return "balanced"

    def select_runtime(self, requested_tier: RuntimeTier = "balanced") -> RuntimeDecision:
        """Select runtime tier based on system state. Per Spec Task 0.2."""
        state = self.sample()
        tier = _select_tier(state, requested_tier)

        if state.indexing_queue_depth >= _INDEX_QUEUE_DEGRADED_THRESHOLD and tier == "deep":
            tier = "balanced"
        if state.indexing_queue_depth >= _INDEX_QUEUE_RESTRICT_THRESHOLD and tier in ("balanced", "deep"):
            tier = "fast"

        if tier != requested_tier:
            logger.info(
                "Governor downgraded %s → %s (mem=%.0f%%, swap=%dMB, thermal=%s)",
                requested_tier, tier,
                state.memory_pressure_pct, state.swap_used_mb, state.thermal_state,
            )

        model_map: dict[RuntimeTier, str] = {
            "fast": "qwen3.5:9b",
            "balanced": "qwen3.5:9b",
            "deep": "exaone4.0:32b",
            "unloaded": "",
        }

        context_window_map: dict[RuntimeTier, int] = {
            "fast": 4096,
            "balanced": 8192,
            "deep": 16384,
            "unloaded": 2048,
        }
        chunk_map: dict[RuntimeTier, int] = {
            "fast": 4,
            "balanced": 8,
            "deep": 10,
            "unloaded": 2,
        }
        timeout_map: dict[RuntimeTier, int] = {
            "fast": 15000,
            "balanced": 30000,
            "deep": 45000,
            "unloaded": 8000,
        }

        if self._metrics is not None:
            last_ttft = self._metrics.get_last(MetricName.TTFT_MS)
            if last_ttft is not None and last_ttft.value >= _TTFT_DEGRADE_THRESHOLD_MS:
                chunk_map[tier] = max(2, chunk_map[tier] - 2)
                context_window_map[tier] = max(2048, context_window_map[tier] // 2)

        return RuntimeDecision(
            tier=tier,
            backend="mlx" if tier != "unloaded" else "llamacpp",
            model_id=model_map.get(tier, ""),
            context_window=context_window_map[tier],
            max_retrieved_chunks=chunk_map[tier],
            generation_timeout_ms=timeout_map[tier],
            reasoning_enabled=tier == "deep",
        )


class GovernorStub:
    """Stub governor for testing. Always reports healthy/safe defaults."""

    @property
    def mode(self) -> GovernorMode:
        return GovernorMode.NORMAL

    def check_resource_budget(self) -> bool:
        return True

    def should_degrade(self) -> bool:
        return False

    def report_memory_pressure(self) -> float:
        return 0.0


# Avoid import-time protocol checks here. `GovernorProtocol` includes a
# `mode` property, and `isinstance(..., GovernorProtocol)` may evaluate that
# property during module import, which in turn triggers system sampling.
# That creates test and sandbox failures before the application even starts.
