"""M5.3 场景 5 — 轻量定时任务调度器。

不引入 APScheduler，用 threading.Timer 轮询。
每分钟检查一次，触发到期任务。
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class ScheduledTask:
    """定时任务定义。"""

    id: str
    name: str
    interval_seconds: int
    action: str
    last_run: float = 0.0
    next_run: float = 0.0
    enabled: bool = True
    metadata: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class TaskScheduler:
    """轻量定时任务调度器。"""

    def __init__(self, check_interval: int = 60) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._check_interval = check_interval
        self._handlers: dict[str, Callable[[], None]] = {}
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._running = False

    def register_handler(self, action: str, handler: Callable[[], None]) -> None:
        """注册任务动作处理器。"""
        self._handlers[action] = handler

    def add_task(
        self,
        name: str,
        interval_seconds: int,
        action: str,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        """添加定时任务。"""
        now = time.time()
        task = ScheduledTask(
            id=str(hash(f"{name}:{now}")),
            name=name,
            interval_seconds=interval_seconds,
            action=action,
            last_run=0,
            next_run=now + interval_seconds,
            enabled=True,
            metadata=metadata or {},
        )
        with self._lock:
            self._tasks[task.id] = task
        return task

    def remove_task(self, task_id: str) -> bool:
        """删除定时任务。"""
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def list_tasks(self) -> list[ScheduledTask]:
        """列出所有任务。"""
        with self._lock:
            return list(self._tasks.values())

    def start(self) -> None:
        """启动调度器。"""
        self._running = True
        self._schedule_next()

    def stop(self) -> None:
        """停止调度器。"""
        self._running = False
        if self._timer is not None:
            self._timer.cancel()

    def _schedule_next(self) -> None:
        """安排下一次检查。"""
        if not self._running:
            return
        self._timer = threading.Timer(self._check_interval, self._tick)
        self._timer.daemon = True
        self._timer.start()

    def _tick(self) -> None:
        """执行一次检查，触发到期任务。"""
        now = time.time()
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if not task.enabled:
                continue
            if task.next_run <= now:
                self._run_task(task)
                task.last_run = now
                task.next_run = now + task.interval_seconds
        self._schedule_next()

    def _run_task(self, task: ScheduledTask) -> None:
        """执行单个任务。"""
        handler = self._handlers.get(task.action)
        if handler is None:
            logger.warning(f"No handler for task action: {task.action}")
            return
        try:
            handler()
            logger.info(f"Task executed: {task.name} ({task.action})")
        except Exception as e:
            logger.error(f"Task failed: {task.name}: {e}")

    def force_tick(self) -> int:
        """手动触发一次检查（用于测试）。"""
        now = time.time()
        executed = 0
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            if not task.enabled:
                continue
            if task.next_run <= now:
                self._run_task(task)
                task.last_run = now
                task.next_run = now + task.interval_seconds
                executed += 1
        return executed
