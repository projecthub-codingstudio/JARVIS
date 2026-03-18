"""Observability metrics event contracts for the JARVIS system.

Defines 11 required metric event types and a lightweight metrics collector.
All critical flows must emit metrics through this interface.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, unique
from typing import TYPE_CHECKING, Generator


def _now() -> datetime:
    return datetime.now()


@unique
class MetricName(str, Enum):
    """11 required metric event families."""

    QUERY_LATENCY_MS = "query_latency_ms"
    TTFT_MS = "ttft_ms"
    RETRIEVAL_TOP5_HIT = "retrieval_top5_hit"
    CITATION_MISSING_RATE = "citation_missing_rate"
    CITATION_STALE_RATE = "citation_stale_rate"
    TRUST_RECOVERY_TIME_MS = "trust_recovery_time_ms"
    INDEX_LAG_MS = "index_lag_ms"
    SWAP_DETECTED_COUNT = "swap_detected_count"
    MODEL_LOAD_FAILURE_COUNT = "model_load_failure_count"
    SQLITE_LOCK_COUNT = "sqlite_lock_count"
    DRAFT_EXPORT_APPROVAL_RATE = "draft_export_approval_rate"


@dataclass
class MetricEvent:
    """A single metric event recording."""

    name: MetricName
    value: float
    unit: str = "ms"
    tags: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_now)


class MetricsCollector:
    """In-process metrics collector.

    Phase 0: stores events in memory. Phase 2+: can be extended to
    export to external systems.
    """

    def __init__(self) -> None:
        self._events: list[MetricEvent] = []

    def record(self, name: MetricName, value: float, unit: str = "ms",
               tags: dict[str, str] | None = None) -> None:
        """Record a metric event."""
        self._events.append(MetricEvent(
            name=name,
            value=value,
            unit=unit,
            tags=tags or {},
        ))

    def increment(self, name: MetricName, tags: dict[str, str] | None = None) -> None:
        """Increment a counter metric by 1."""
        self.record(name, 1.0, unit="count", tags=tags)

    @contextmanager
    def measure(self, name: MetricName,
                tags: dict[str, str] | None = None) -> Generator[None, None, None]:
        """Context manager to measure duration of an operation in milliseconds."""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.record(name, elapsed_ms, unit="ms", tags=tags)

    def get_events(self, name: MetricName | None = None) -> list[MetricEvent]:
        """Retrieve recorded events, optionally filtered by name."""
        if name is None:
            return list(self._events)
        return [e for e in self._events if e.name == name]

    def get_last(self, name: MetricName) -> MetricEvent | None:
        """Get the most recent event for a given metric name."""
        for event in reversed(self._events):
            if event.name == name:
                return event
        return None

    def clear(self) -> None:
        """Clear all recorded events."""
        self._events.clear()

    @property
    def count(self) -> int:
        return len(self._events)
