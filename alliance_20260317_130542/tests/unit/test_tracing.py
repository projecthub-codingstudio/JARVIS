"""Tests for in-process tracing."""

from __future__ import annotations

from jarvis.observability.tracing import Tracer


class TestTracer:
    def test_records_completed_span(self) -> None:
        tracer = Tracer()

        with tracer.start_span("retrieve") as span:
            span.set_attribute("stage", "fts")

        assert len(tracer.spans) == 1
        assert tracer.spans[0].name == "retrieve"
        assert tracer.spans[0].attributes["stage"] == "fts"
        assert tracer.spans[0].duration_ms >= 0.0
