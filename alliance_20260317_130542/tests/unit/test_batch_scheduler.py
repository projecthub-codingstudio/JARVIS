from __future__ import annotations

import time

from jarvis.learning.batch_scheduler import BatchScheduler


class _FakeCoordinator:
    def __init__(self) -> None:
        self.analyze_count = 0
        self.refresh_count = 0

    def analyze_unanalyzed(self, *, before: int) -> int:
        self.analyze_count += 1
        return 0

    def refresh_index(self) -> None:
        self.refresh_count += 1


def test_scheduler_runs_analysis_at_interval() -> None:
    fake = _FakeCoordinator()
    scheduler = BatchScheduler(
        coordinator=fake,
        interval_seconds=0.1,
        lookback_seconds=60,
    )
    scheduler.start()
    time.sleep(0.35)
    scheduler.stop()
    assert fake.analyze_count >= 2
    assert fake.refresh_count >= 2


def test_scheduler_stop_is_idempotent() -> None:
    scheduler = BatchScheduler(
        coordinator=_FakeCoordinator(),
        interval_seconds=0.1,
        lookback_seconds=60,
    )
    scheduler.start()
    scheduler.stop()
    scheduler.stop()
