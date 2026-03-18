"""FileWatcher — monitors watched folders for file changes via watchdog.

Detects creates, updates, deletes, and moves and feeds them into the
indexing pipeline.

Handles:
  - File create/modify/delete
  - File rename/move (on_moved → delete old + create new)
  - Directory delete/rename (on_deleted/on_moved for dirs →
    emits "dir_deleted"/"dir_moved" so the handler can clean up children)
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer


class _Handler(FileSystemEventHandler):
    """Internal event handler that forwards to the on_change callback."""

    def __init__(self, on_change: Callable[[Path, str, Path | None], None]) -> None:
        self._on_change = on_change

    def _should_ignore(self, path: str) -> bool:
        name = Path(path).name
        return name.startswith(".")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "created", None)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        self._on_change(Path(event.src_path), "modified", None)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if self._should_ignore(event.src_path):
            return
        if event.is_directory:
            self._on_change(Path(event.src_path), "dir_deleted", None)
        else:
            self._on_change(Path(event.src_path), "deleted", None)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file/directory rename or move."""
        if self._should_ignore(event.src_path):
            return
        dest_path = Path(event.dest_path) if hasattr(event, "dest_path") else None
        if event.is_directory:
            self._on_change(Path(event.src_path), "dir_moved", dest_path)
        else:
            self._on_change(Path(event.src_path), "moved", dest_path)


class FileWatcher:
    """Watches directories for file system changes using watchdog."""

    def __init__(
        self,
        *,
        watched_folders: list[Path],
        on_change: Callable[[Path, str, Path | None], None] | None = None,
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
