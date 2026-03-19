"""Tests for health checks and structured logging."""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from jarvis.app.config import JarvisConfig
from jarvis.observability.health import check_health
from jarvis.observability.logging import JsonLogFormatter
from jarvis.observability.metrics import MetricsCollector


class TestHealthCheck:
    def test_reports_healthy_with_valid_dependencies(self, tmp_path: Path) -> None:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")
        status = check_health({
            "db": sqlite3.connect(":memory:"),
            "metrics": MetricsCollector(),
            "config": config,
        })

        assert status.healthy is True
        # Core checks pass; runtime checks are "not configured" (False but not degraded)
        core_keys = {"database", "metrics", "watched_folders", "export_dir"}
        assert all(status.checks[k] for k in core_keys if k in status.checks)
        assert status.message == "OK"
        assert status.failed_checks == []

    def test_reports_healthy_with_full_runtime(self, tmp_path: Path) -> None:
        """All checks pass when runtime deps are provided."""
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")

        class FakeLLM:
            model_id = "test-model"

        class FakeEmbedding:
            model_loaded = True

        class FakeVector:
            _table = object()

        class FakeWatcher:
            def is_alive(self) -> bool:
                return True

        status = check_health({
            "db": sqlite3.connect(":memory:"),
            "metrics": MetricsCollector(),
            "config": config,
            "llm_generator": FakeLLM(),
            "embedding_runtime": FakeEmbedding(),
            "vector_index": FakeVector(),
            "file_watcher": FakeWatcher(),
        })

        assert status.healthy is True
        assert all(status.checks.values())
        assert status.message == "OK"

    def test_reports_healthy_when_vector_index_uses_get_table(self, tmp_path: Path) -> None:
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")

        class FakeVector:
            def _get_table(self) -> object:
                return object()

        status = check_health({
            "db": sqlite3.connect(":memory:"),
            "metrics": MetricsCollector(),
            "config": config,
            "vector_index": FakeVector(),
        })

        assert status.healthy is True
        assert status.checks["vector_db"] is True
        assert status.details["vector_db"] == "OK"

    def test_reports_missing_dependencies(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing-folder"
        config = JarvisConfig(watched_folders=[missing], data_dir=tmp_path / ".jarvis")
        status = check_health({
            "db": None,
            "metrics": None,
            "config": config,
        })

        assert status.healthy is False
        assert status.checks["database"] is False
        assert status.checks["metrics"] is False
        assert status.checks["watched_folders"] is False
        assert "Degraded" in status.message
        assert "database" in status.failed_checks
        assert "metrics" in status.failed_checks

    def test_reports_degraded_when_runtime_dep_broken(self, tmp_path: Path) -> None:
        """If a runtime dep is provided but broken, health degrades."""
        config = JarvisConfig(watched_folders=[tmp_path], data_dir=tmp_path / ".jarvis")

        class BrokenLLM:
            model_id = "stub"

        status = check_health({
            "db": sqlite3.connect(":memory:"),
            "metrics": MetricsCollector(),
            "config": config,
            "llm_generator": BrokenLLM(),
        })

        assert status.healthy is False
        assert status.checks["model"] is False
        assert "model" in status.message
        assert status.failed_checks == ["model"]


class TestJsonLogFormatter:
    def test_formats_record_as_json(self) -> None:
        formatter = JsonLogFormatter()
        record = logging.LogRecord(
            name="jarvis.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )

        payload = json.loads(formatter.format(record))
        assert payload["level"] == "INFO"
        assert payload["logger"] == "jarvis.test"
        assert payload["message"] == "hello world"
        assert "timestamp" in payload
