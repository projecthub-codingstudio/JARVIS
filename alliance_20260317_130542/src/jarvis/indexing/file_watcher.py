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

import inspect
from pathlib import Path
from typing import Callable

from watchdog.events import FileMovedEvent, FileSystemEvent, FileSystemEventHandler
from watchdog.observers.polling import PollingObserver


class _Handler(FileSystemEventHandler):
    """Internal event handler that forwards to the on_change callback."""

    def __init__(
        self,
        on_change: Callable[[Path, str, Path | None], None],
        known_paths: set[Path],
    ) -> None:
        self._on_change = on_change
        self._callback_arity = len(inspect.signature(on_change).parameters)
        self._known_paths = known_paths

    def _emit(self, path: Path, event_type: str, dest_path: Path | None = None) -> None:
        if self._callback_arity >= 3:
            self._on_change(path, event_type, dest_path)
            return
        self._on_change(path, event_type)  # type: ignore[misc]

    def _should_ignore(self, path: str) -> bool:
        name = Path(path).name
        return name.startswith(".")

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        path = Path(event.src_path)
        self._known_paths.add(path)
        self._emit(path, "created", None)

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory or self._should_ignore(event.src_path):
            return
        path = Path(event.src_path)
        if path not in self._known_paths:
            self._known_paths.add(path)
            self._emit(path, "created", None)
        self._emit(path, "modified", None)

    def on_deleted(self, event: FileSystemEvent) -> None:
        if self._should_ignore(event.src_path):
            return
        path = Path(event.src_path)
        self._known_paths.discard(path)
        if event.is_directory:
            self._emit(path, "dir_deleted", None)
        else:
            self._emit(path, "deleted", None)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file/directory rename or move."""
        if self._should_ignore(event.src_path):
            return
        src_path = Path(event.src_path)
        self._known_paths.discard(src_path)
        dest_path = Path(event.dest_path) if hasattr(event, "dest_path") else None
        if dest_path is not None:
            self._known_paths.add(dest_path)
        if event.is_directory:
            self._emit(src_path, "dir_moved", dest_path)
        else:
            self._emit(src_path, "moved", dest_path)


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
        self._observer: PollingObserver | None = None
        self._running = False
        self._known_paths: set[Path] = set()

    def start(self) -> None:
        self._running = True
        if self._on_change is None:
            return
        # Polling is slower than platform-native backends, but it is
        # reliable in sandboxed/test environments where FSEvents may fail.
        self._observer = PollingObserver(timeout=0.2)
        self._known_paths = {
            path
            for folder in self._watched_folders
            for path in folder.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        }
        handler = _Handler(self._on_change, self._known_paths)
        for folder in self._watched_folders:
            self._observer.schedule(handler, str(folder), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._running = False
