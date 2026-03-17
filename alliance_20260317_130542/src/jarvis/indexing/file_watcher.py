"""FileWatcher — monitors watched folders for file changes via watchdog.

Detects creates, updates, and deletes and feeds them into the
indexing pipeline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _Handler(FileSystemEventHandler):
    """Internal event handler that forwards to the on_change callback."""

    def __init__(self, on_change: Callable[[Path, str], None]) -> None:
        self._on_change = on_change

    def _should_ignore(self, path: str) -> bool:
        name = Path(path).name
        return name.startswith(".")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "deleted")


class FileWatcher:
    """Watches directories for file system changes using watchdog."""

    def __init__(
        self,
        *,
        watched_folders: list[Path],
        on_change: Callable[[Path, str], None] | None = None,
    ) -> None:
        self._watched_folders = watched_folders
        self._on_change = on_change
        self._observer: Observer | None = None
        self._running = False

    def start(self) -> None:
        self._running = True
        if self._on_change is None:
            return
        self._observer = Observer()
        handler = _Handler(self._on_change)
        for folder in self._watched_folders:
            self._observer.schedule(handler, str(folder), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._running = False
