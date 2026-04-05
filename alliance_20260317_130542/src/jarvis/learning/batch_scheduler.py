"""BatchScheduler — runs analyze_unanalyzed + refresh_index on a timer."""
from __future__ import annotations

import logging
import threading
import time
from typing import Protocol


logger = logging.getLogger(__name__)


class _CoordinatorLike(Protocol):
    def analyze_unanalyzed(self, *, before: int) -> int: ...
    def refresh_index(self) -> None: ...


class BatchScheduler:
    def __init__(
        self,
        *,
        coordinator: _CoordinatorLike,
        interval_seconds: float = 600.0,
        lookback_seconds: int = 300,
    ) -> None:
        self._coordinator = coordinator
        self._interval = interval_seconds
        self._lookback = lookback_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                before = int(time.time()) - self._lookback
                created = self._coordinator.analyze_unanalyzed(before=before)
                self._coordinator.refresh_index()
                if created > 0:
                    logger.info("Batch analysis created %d new learned patterns", created)
            except Exception as exc:
                logger.warning("Batch analysis failed: %s", exc)
            self._stop.wait(self._interval)
