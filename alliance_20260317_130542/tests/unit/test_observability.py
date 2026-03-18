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
        assert all(status.checks.values())
        assert status.message == "OK"

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
