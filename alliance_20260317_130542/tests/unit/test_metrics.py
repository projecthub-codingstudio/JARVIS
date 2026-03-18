"""Unit tests for the metrics collector."""

from __future__ import annotations

import time

from jarvis.observability.metrics import MetricEvent, MetricName, MetricsCollector


class TestMetricsCollector:
    def test_record_event(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricName.QUERY_LATENCY_MS, 150.0)
        events = collector.get_events(MetricName.QUERY_LATENCY_MS)
        assert len(events) == 1
        assert events[0].value == 150.0
        assert events[0].unit == "ms"

    def test_increment(self) -> None:
        collector = MetricsCollector()
        collector.increment(MetricName.DRAFT_EXPORT_APPROVAL_RATE)
        collector.increment(MetricName.DRAFT_EXPORT_APPROVAL_RATE)
        events = collector.get_events(MetricName.DRAFT_EXPORT_APPROVAL_RATE)
        assert len(events) == 2
        assert all(e.value == 1.0 for e in events)
        assert all(e.unit == "count" for e in events)

    def test_measure_context_manager(self) -> None:
        collector = MetricsCollector()
        with collector.measure(MetricName.QUERY_LATENCY_MS):
            time.sleep(0.01)  # ~10ms
        events = collector.get_events(MetricName.QUERY_LATENCY_MS)
        assert len(events) == 1
        assert events[0].value >= 5.0  # at least 5ms

    def test_get_last(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricName.TTFT_MS, 100.0)
        collector.record(MetricName.TTFT_MS, 200.0)
        last = collector.get_last(MetricName.TTFT_MS)
        assert last is not None
        assert last.value == 200.0

    def test_get_last_nonexistent(self) -> None:
        collector = MetricsCollector()
        assert collector.get_last(MetricName.TTFT_MS) is None

    def test_get_all_events(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricName.QUERY_LATENCY_MS, 100.0)
        collector.record(MetricName.TTFT_MS, 200.0)
        all_events = collector.get_events()
        assert len(all_events) == 2

    def test_clear(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricName.QUERY_LATENCY_MS, 100.0)
        collector.clear()
        assert collector.count == 0

    def test_tags(self) -> None:
        collector = MetricsCollector()
        collector.record(MetricName.RETRIEVAL_TOP5_HIT, 1.0, tags={"query_type": "keyword"})
        event = collector.get_events(MetricName.RETRIEVAL_TOP5_HIT)[0]
        assert event.tags["query_type"] == "keyword"

    def test_all_11_metric_names_exist(self) -> None:
        """Verify all 11 required metric families are defined."""
        expected = {
            "query_latency_ms", "ttft_ms", "retrieval_top5_hit",
            "citation_missing_rate", "citation_stale_rate",
            "trust_recovery_time_ms", "index_lag_ms",
            "swap_detected_count", "model_load_failure_count",
            "sqlite_lock_count", "draft_export_approval_rate",
        }
        actual = {m.value for m in MetricName}
        assert expected == actual


class TestMetricEvent:
    def test_default_unit(self) -> None:
        event = MetricEvent(name=MetricName.QUERY_LATENCY_MS, value=100.0)
        assert event.unit == "ms"

    def test_timestamp_populated(self) -> None:
        event = MetricEvent(name=MetricName.TTFT_MS, value=50.0)
        assert event.timestamp is not None
