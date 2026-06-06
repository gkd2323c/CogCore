"""M5.3 场景 5 — 定时任务 API 端点。

GET  /scheduler/tasks       — 查看任务列表
POST /scheduler/tasks       — 添加定时任务
DELETE /scheduler/tasks/{id} — 删除
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cogcore.scheduler import TaskScheduler

router = APIRouter(prefix="/v1", tags=["scheduler"])

# 进程内单例
_scheduler: TaskScheduler | None = None


def _get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler


class TaskCreate(BaseModel):
    name: str
    interval_seconds: int
    action: str
    metadata: dict | None = None


@router.get("/scheduler/tasks")
def list_tasks():
    """查看任务列表。"""
    sched = _get_scheduler()
    return [t.to_dict() for t in sched.list_tasks()]


@router.post("/scheduler/tasks")
def create_task(body: TaskCreate):
    """添加定时任务。"""
    sched = _get_scheduler()
    task = sched.add_task(
        name=body.name,
        interval_seconds=body.interval_seconds,
        action=body.action,
        metadata=body.metadata or {},
    )
    return task.to_dict()


@router.delete("/scheduler/tasks/{task_id}")
def delete_task(task_id: str):
    """删除定时任务。"""
    sched = _get_scheduler()
    if not sched.remove_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}
