"""M5.3 场景 3 — HITL API 端点。

POST /hitl/request   — 提交人工干预请求（挂起 Agent）
GET  /hitl/pending   — 查看待处理请求列表
POST /hitl/respond/{request_id} — 人工回复，恢复 Agent
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.deps import get_service
from cogcore.hitl import HITLManager

router = APIRouter(prefix="/v1", tags=["hitl"])

# 进程内单例 HITLManager（与 service 绑定）
_hitl_manager: HITLManager | None = None


def _get_hitl() -> HITLManager:
    """获取或创建 HITLManager（绑定到 service）。"""
    global _hitl_manager
    if _hitl_manager is None:
        _hitl_manager = HITLManager()
        # 将 teacher_gate 注入 service 的 wake_controller
        svc = get_service()
        if hasattr(svc, "_wake_controller"):
            svc._wake_controller.teacher_gate = _hitl_manager.teacher_gate_with_auto_create
    return _hitl_manager


class HITLRequestCreate(BaseModel):
    prompt: str
    metadata: dict | None = None


class HITLResponseCreate(BaseModel):
    response: str
    action: str = "approve"  # approve | reject


@router.post("/hitl/request")
def create_hitl_request(body: HITLRequestCreate):
    """提交人工干预请求。"""
    mgr = _get_hitl()
    req = mgr.create_request(body.prompt, metadata=body.metadata or {})
    return req.to_dict()


@router.get("/hitl/pending")
def list_pending():
    """查看待处理请求列表。"""
    mgr = _get_hitl()
    return [r.to_dict() for r in mgr.list_pending()]


@router.post("/hitl/respond/{request_id}")
def respond_hitl(request_id: str, body: HITLResponseCreate):
    """人工回复，恢复或终止 Agent。"""
    mgr = _get_hitl()
    if body.action == "approve":
        req = mgr.approve(request_id, body.response)
    else:
        req = mgr.reject(request_id, body.response)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req.to_dict()


@router.get("/hitl/stats")
def hitl_stats():
    """HITL 统计。"""
    mgr = _get_hitl()
    return mgr.stats()
