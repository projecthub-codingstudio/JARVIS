"""Tests for the 50-query benchmark harness."""
from __future__ import annotations

from pathlib import Path

from jarvis.perf.benchmark import PerfReport, run_query_latency_bench


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
CORPUS_DIR = FIXTURES_DIR / "corpus"
QUERIES_PATH = FIXTURES_DIR / "eval_queries.json"


class TestQueryLatencyBench:
    def test_returns_perf_report(self) -> None:
        report = run_query_latency_bench(CORPUS_DIR, QUERIES_PATH)
        assert isinstance(report, PerfReport)

    def test_runs_all_50_queries(self) -> None:
        report = run_query_latency_bench(CORPUS_DIR, QUERIES_PATH)
        assert report.query_count == 50
        assert len(report.results) == 50

    def test_reports_latency_and_accuracy(self) -> None:
        report = run_query_latency_bench(CORPUS_DIR, QUERIES_PATH)
        assert report.avg_latency_ms >= 0.0
        assert report.p95_latency_ms >= 0.0
        assert 0.0 <= report.top5_accuracy <= 1.0

    def test_includes_category_accuracy(self) -> None:
        report = run_query_latency_bench(CORPUS_DIR, QUERIES_PATH)
        assert "factual" in report.category_accuracy
        assert "code" in report.category_accuracy
        assert "mixed" in report.category_accuracy

    def test_has_at_least_one_hit(self) -> None:
        report = run_query_latency_bench(CORPUS_DIR, QUERIES_PATH)
        assert any(result.top5_hit for result in report.results)
