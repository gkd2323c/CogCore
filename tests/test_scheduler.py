"""M5.3 场景 5 — 定时任务调度器测试。"""
from __future__ import annotations

import time

from cogcore.scheduler import TaskScheduler


# ============================================================
# 任务管理
# ============================================================


def test_add_task():
    sched = TaskScheduler()
    task = sched.add_task("daily_digest", 3600, "diary_digest")
    assert task.name == "daily_digest"
    assert task.interval_seconds == 3600
    assert task.action == "diary_digest"
    assert task.enabled is True


def test_list_tasks():
    sched = TaskScheduler()
    sched.add_task("t1", 60, "action1")
    sched.add_task("t2", 120, "action2")
    assert len(sched.list_tasks()) == 2


def test_remove_task():
    sched = TaskScheduler()
    task = sched.add_task("toremove", 60, "action")
    assert sched.remove_task(task.id) is True
    assert len(sched.list_tasks()) == 0
    assert sched.remove_task("missing") is False


# ============================================================
# 任务执行
# ============================================================


def test_task_execution():
    """任务到期后被执行。"""
    sched = TaskScheduler()
    executed = []

    def handler():
        executed.append("x")

    sched.register_handler("test_action", handler)
    sched.add_task("test", 1, "test_action")

    # 手动触发检查
    time.sleep(1.1)
    count = sched.force_tick()
    assert count >= 1
    assert "x" in executed


def test_task_not_executed_before_due():
    """未到期任务不被执行。"""
    sched = TaskScheduler()
    executed = []

    def handler():
        executed.append("x")

    sched.register_handler("late_action", handler)
    sched.add_task("late", 3600, "late_action")
    count = sched.force_tick()
    assert count == 0
    assert executed == []
