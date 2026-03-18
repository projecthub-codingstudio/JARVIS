"""Runtime error thresholds and safe mode management."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ErrorEvent:
    """A recorded error event with category and timestamp."""

    code: str
    category: str
    occurred_at: datetime


class ErrorMonitor:
    """Tracks recent errors and derives tool blocking / safe mode state.

    Spec-aligned thresholds:
      - same error code 5 times within 5 minutes => block tool execution
      - model failure + index failure within 10 minutes => safe mode
    """

    _TOOL_BLOCK_WINDOW = timedelta(minutes=5)
    _SAFE_MODE_WINDOW = timedelta(minutes=10)

    def __init__(self) -> None:
        self._by_code: dict[str, deque[datetime]] = defaultdict(deque)
        self._category_events: dict[str, deque[datetime]] = defaultdict(deque)
        self._safe_mode = False
        self._last_code: str | None = None
        self._consecutive_count = 0
        self._degraded_mode = False
        self._generation_blocked = False
        self._write_blocked = False
        self._rebuild_index_required = False

    def record_error(
        self,
        code: str,
        *,
        category: str,
        occurred_at: datetime | None = None,
    ) -> None:
        """Record an error occurrence for threshold tracking."""
        now = occurred_at or datetime.now()

        code_events = self._by_code[code]
        code_events.append(now)
        self._trim(code_events, self._TOOL_BLOCK_WINDOW, now)

        if code == self._last_code:
            self._consecutive_count += 1
        else:
            self._last_code = code
            self._consecutive_count = 1

        if code == "MODEL_LOAD_FAILED":
            if self._consecutive_count >= 2:
                self._degraded_mode = True
            if self._consecutive_count >= 3:
                self._generation_blocked = True

        if code == "SQLITE_LOCK":
            if self._consecutive_count >= 3:
                self._write_blocked = True
                self._rebuild_index_required = True

        category_events = self._category_events[category]
        category_events.append(now)
        self._trim(category_events, self._SAFE_MODE_WINDOW, now)

        model_active = bool(self._category_events.get("model"))
        index_active = bool(self._category_events.get("index"))
        if model_active and index_active:
            self._safe_mode = True

    def should_block_tools(self, *, occurred_at: datetime | None = None) -> bool:
        """Return True if any error code crossed the repeated-error threshold."""
        now = occurred_at or datetime.now()
        for events in self._by_code.values():
            self._trim(events, self._TOOL_BLOCK_WINDOW, now)
            if len(events) >= 5:
                return True
        return False

    def safe_mode_active(self, *, occurred_at: datetime | None = None) -> bool:
        """Return True if safe mode should remain enabled."""
        if not self._safe_mode:
            return False

        now = occurred_at or datetime.now()
        model_events = self._category_events.get("model", deque())
        index_events = self._category_events.get("index", deque())
        self._trim(model_events, self._SAFE_MODE_WINDOW, now)
        self._trim(index_events, self._SAFE_MODE_WINDOW, now)

        if not model_events or not index_events:
            self._safe_mode = False
            return False
        return True

    def clear_safe_mode(self) -> None:
        """Explicitly clear safe mode."""
        self._safe_mode = False

    @property
    def degraded_mode(self) -> bool:
        """Return True if runtime should operate in degraded mode."""
        return self._degraded_mode

    @property
    def generation_blocked(self) -> bool:
        """Return True if generation should be disabled."""
        return self._generation_blocked

    @property
    def write_blocked(self) -> bool:
        """Return True if write operations should be held."""
        return self._write_blocked

    @property
    def rebuild_index_required(self) -> bool:
        """Return True if operator/user should rebuild the index."""
        return self._rebuild_index_required

    @staticmethod
    def _trim(events: deque[datetime], window: timedelta, now: datetime) -> None:
        cutoff = now - window
        while events and events[0] < cutoff:
            events.popleft()
