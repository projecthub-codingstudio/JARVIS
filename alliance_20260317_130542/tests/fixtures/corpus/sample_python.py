"""작업 스케줄러 모듈.

주기적 작업과 일회성 작업을 관리하는 경량 스케줄러입니다.
우선순위 큐를 사용하여 작업 실행 순서를 결정하며,
최대 동시 실행 작업 수를 제한하여 리소스를 보호합니다.
"""

import heapq
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Callable


class Priority(IntEnum):
    """작업 우선순위 열거형.

    낮은 숫자가 높은 우선순위를 나타냅니다.
    CRITICAL 작업은 다른 모든 작업보다 먼저 실행됩니다.
    """

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass(order=True)
class ScheduledTask:
    """스케줄링된 작업을 나타내는 데이터 클래스.

    Attributes:
        scheduled_time: 예약된 실행 시각
        priority: 작업 우선순위
        task_id: 고유 작업 식별자
        func: 실행할 콜백 함수
        interval: 반복 주기 (None이면 일회성 작업)
        retry_count: 실패 시 재시도 횟수 (기본 3회)
    """

    scheduled_time: float
    priority: Priority = field(compare=True)
    task_id: str = field(compare=False)
    func: Callable = field(compare=False, repr=False)
    interval: float | None = field(default=None, compare=False)
    retry_count: int = field(default=3, compare=False)


class TaskScheduler:
    """우선순위 기반 작업 스케줄러.

    힙 큐를 사용하여 다음에 실행할 작업을 O(log n) 시간에 결정합니다.
    스레드 안전하며, 최대 동시 실행 제한을 지원합니다.
    """

    MAX_CONCURRENT = 4  # 최대 동시 실행 작업 수

    def __init__(self):
        self._queue: list[ScheduledTask] = []
        self._lock = threading.Lock()
        self._running = False
        self._active_count = 0

    def add_task(
        self,
        task_id: str,
        func: Callable,
        delay: float = 0.0,
        priority: Priority = Priority.NORMAL,
        interval: float | None = None,
    ) -> None:
        """새 작업을 스케줄러에 등록합니다.

        Args:
            task_id: 고유 작업 식별자
            func: 실행할 함수
            delay: 첫 실행까지 대기 시간 (초)
            priority: 작업 우선순위 (기본 NORMAL)
            interval: 반복 주기 (초). None이면 일회성 작업
        """
        task = ScheduledTask(
            scheduled_time=time.time() + delay,
            priority=priority,
            task_id=task_id,
            func=func,
            interval=interval,
        )
        with self._lock:
            heapq.heappush(self._queue, task)

    def cancel_task(self, task_id: str) -> bool:
        """등록된 작업을 취소합니다.

        Returns:
            작업이 존재하여 취소되었으면 True, 아니면 False
        """
        with self._lock:
            original_len = len(self._queue)
            self._queue = [t for t in self._queue if t.task_id != task_id]
            heapq.heapify(self._queue)
            return len(self._queue) < original_len

    def get_pending_count(self) -> int:
        """대기 중인 작업 수를 반환합니다."""
        with self._lock:
            return len(self._queue)

    def run(self) -> None:
        """스케줄러 메인 루프를 시작합니다.

        등록된 작업을 예약 시간에 맞춰 실행하며,
        반복 작업은 실행 후 다시 큐에 등록됩니다.
        stop() 호출 시 루프가 종료됩니다.
        """
        self._running = True
        while self._running:
            with self._lock:
                if not self._queue:
                    continue
                if self._active_count >= self.MAX_CONCURRENT:
                    continue
                next_task = self._queue[0]
                if next_task.scheduled_time > time.time():
                    continue
                task = heapq.heappop(self._queue)

            self._active_count += 1
            try:
                task.func()
                if task.interval is not None:
                    self.add_task(
                        task_id=task.task_id,
                        func=task.func,
                        delay=task.interval,
                        priority=task.priority,
                        interval=task.interval,
                    )
            except Exception:
                if task.retry_count > 0:
                    task.retry_count -= 1
                    task.scheduled_time = time.time() + 5.0  # 5초 후 재시도
                    with self._lock:
                        heapq.heappush(self._queue, task)
            finally:
                self._active_count -= 1

            time.sleep(0.01)

    def stop(self) -> None:
        """스케줄러를 정지합니다."""
        self._running = False
