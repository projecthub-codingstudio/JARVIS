"""Lightweight in-process tracing for JARVIS observability."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SpanRecord:
    """Completed span metadata stored in memory."""

    name: str
    started_at: float
    ended_at: float | None = None
    attributes: dict[str, str] = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        if self.ended_at is None:
            return 0.0
        return (self.ended_at - self.started_at) * 1000


class Tracer:
    """Small in-memory tracer suitable for tests and local debugging."""

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []

    def start_span(self, name: str) -> SpanContext:
        span = SpanRecord(name=name, started_at=time.perf_counter())
        return SpanContext(span, self._spans)

    @property
    def spans(self) -> list[SpanRecord]:
        return list(self._spans)


class SpanContext:
    """A trace span context manager."""

    def __init__(self, span: SpanRecord, sink: list[SpanRecord]) -> None:
        self._span = span
        self._sink = sink

    def end(self) -> None:
        if self._span.ended_at is None:
            self._span.ended_at = time.perf_counter()
            self._sink.append(self._span)

    def set_attribute(self, key: str, value: str) -> None:
        self._span.attributes[key] = value

    def __enter__(self) -> SpanContext:
        return self

    def __exit__(self, *args: object) -> None:
        self.end()
