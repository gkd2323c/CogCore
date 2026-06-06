"""M5.3 场景 4 — 多 Agent 协作 API 端点。

POST /agents/spawn        — 创建新 Agent 实例
POST /agents/{id}/delegate — 委派任务
GET  /agents/{id}/status   — 查看状态
GET  /agents               — 列出所有 Agent
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cogcore.multi_agent import AgentPool

router = APIRouter(prefix="/v1", tags=["multi_agent"])

# 进程内单例 AgentPool
_agent_pool: AgentPool | None = None


def _get_pool() -> AgentPool:
    global _agent_pool
    if _agent_pool is None:
        _agent_pool = AgentPool()
    return _agent_pool


class SpawnRequest(BaseModel):
    name: str = ""
    metadata: dict | None = None


class DelegateRequest(BaseModel):
    from_agent_id: str
    task: dict


@router.post("/agents/spawn")
def spawn_agent(body: SpawnRequest):
    """创建新 Agent 实例。"""
    pool = _get_pool()
    agent = pool.spawn(name=body.name, metadata=body.metadata or {})
    return {
        "id": agent.id,
        "name": agent.name,
        "created_ts": agent.created_ts,
    }


@router.get("/agents")
def list_agents():
    """列出所有 Agent。"""
    pool = _get_pool()
    return [
        {"id": a.id, "name": a.name, "created_ts": a.created_ts}
        for a in pool.list_agents()
    ]


@router.get("/agents/{agent_id}/status")
def agent_status(agent_id: str):
    """查看 Agent 状态。"""
    pool = _get_pool()
    agent = pool.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {
        "id": agent.id,
        "name": agent.name,
        "status": agent.service.get_status(),
    }


@router.post("/agents/{agent_id}/delegate")
def delegate_task(agent_id: str, body: DelegateRequest):
    """向指定 Agent 委派任务。"""
    pool = _get_pool()
    result = pool.delegate(
        task=body.task,
        from_agent_id=body.from_agent_id,
        to_agent_id=agent_id,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
