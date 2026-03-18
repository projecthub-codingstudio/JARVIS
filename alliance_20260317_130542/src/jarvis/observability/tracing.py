"""Tracing stubs for JARVIS observability. Phase 0: no-op."""

from __future__ import annotations


class Tracer:
    """Placeholder tracer for Phase 0. Will be extended in Phase 2."""

    def start_span(self, name: str) -> SpanContext:
        return SpanContext(name)


class SpanContext:
    """A no-op span context."""

    def __init__(self, name: str) -> None:
        self.name = name

    def end(self) -> None:
        pass

    def __enter__(self) -> SpanContext:
        return self

    def __exit__(self, *args: object) -> None:
        self.end()
