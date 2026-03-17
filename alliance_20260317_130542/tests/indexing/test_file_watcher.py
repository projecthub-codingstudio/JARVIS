"""Tests for FileWatcher."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jarvis.indexing.file_watcher import FileWatcher


class TestFileWatcherInit:
    def test_creates_with_folders(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        assert watcher._watched_folders == [tmp_path]

    def test_creates_with_callback(self, tmp_path: Path) -> None:
        cb = MagicMock()
        watcher = FileWatcher(watched_folders=[tmp_path], on_change=cb)
        assert watcher._on_change is cb


class TestFileWatcherStartStop:
    def test_start_and_stop(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        watcher.start()
        assert watcher._running
        watcher.stop()
        assert not watcher._running

    def test_stop_without_start_is_safe(self, tmp_path: Path) -> None:
        watcher = FileWatcher(watched_folders=[tmp_path])
        watcher.stop()  # Should not raise


class TestFileWatcherEvents:
    def test_detects_file_creation(self, tmp_path: Path) -> None:
        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            (tmp_path / "new.md").write_text("hello")
            time.sleep(1.0)
        finally:
            watcher.stop()

        created = [e for e in events if e[1] == "created"]
        assert len(created) >= 1
        assert any("new.md" in str(e[0]) for e in created)

    def test_detects_file_modification(self, tmp_path: Path) -> None:
        f = tmp_path / "existing.md"
        f.write_text("original")
        time.sleep(0.1)

        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            f.write_text("modified")
            time.sleep(1.0)
        finally:
            watcher.stop()

        modified = [e for e in events if e[1] == "modified"]
        assert len(modified) >= 1

    def test_detects_file_deletion(self, tmp_path: Path) -> None:
        f = tmp_path / "deleteme.md"
        f.write_text("to delete")
        time.sleep(0.1)

        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            f.unlink()
            time.sleep(1.0)
        finally:
            watcher.stop()

        deleted = [e for e in events if e[1] == "deleted"]
        assert len(deleted) >= 1

    def test_ignores_hidden_files(self, tmp_path: Path) -> None:
        events: list[tuple[Path, str]] = []

        def on_change(path: Path, event_type: str) -> None:
            events.append((path, event_type))

        watcher = FileWatcher(watched_folders=[tmp_path], on_change=on_change)
        watcher.start()

        try:
            (tmp_path / ".hidden").write_text("should ignore")
            time.sleep(1.0)
        finally:
            watcher.stop()

        assert all(".hidden" not in str(e[0]) for e in events)
