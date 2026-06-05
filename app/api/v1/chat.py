"""POST /v1/chat — 同步对话端点。

请求：
    POST /v1/chat
    {"message": "你好", "thread_id": "default", "system_prompt": null}

响应：
    {"message": "...", "tick_count": 5, "tool_calls": 0, "stages": 10}
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.deps import get_agent
from cogcore.agent import CogCoreAgent

router = APIRouter(prefix="/v1", tags=["chat"])


class ChatRequest(BaseModel):
    """对话请求体。"""

    message: str = Field(..., min_length=1, description="用户消息")
    thread_id: str = Field(default="default", description="会话 ID（多轮共享）")
    system_prompt: Optional[str] = Field(default=None, description="可选系统提示")
    max_tool_turns: int = Field(default=3, ge=1, le=10)


class ChatResponse(BaseModel):
    """对话响应体。"""

    message: str
    thread_id: str
    tick_count: int
    tool_calls: int
    stages: int


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, agent: CogCoreAgent = Depends(get_agent)) -> ChatResponse:
    """处理一条用户消息，返回 Agent 回复。"""
    resp = agent.process_message(
        message=req.message,
        thread_id=req.thread_id,
        system_prompt=req.system_prompt,
        max_tool_turns=req.max_tool_turns,
    )
    return ChatResponse(
        message=resp.message,
        thread_id=req.thread_id,
        tick_count=resp.tick_count,
        tool_calls=resp.tool_calls,
        stages=resp.stages,
    )
