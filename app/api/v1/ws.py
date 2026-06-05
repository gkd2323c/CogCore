"""/v1/ws/{thread_id} — WebSocket 流式对话端点。

协议：
    客户端发送: {"action": "send", "message": "..."}
    服务端流式返回: {"type": "tick_start"} → {"type": "chunk", "delta": "..."} → {"type": "done", "tick_count": N}
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.deps import get_agent
from cogcore.agent import CogCoreAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/ws", tags=["ws"])


@router.websocket("/{thread_id}")
async def chat_ws(websocket: WebSocket, thread_id: str, agent: CogCoreAgent = Depends(get_agent)):
    """WebSocket 流式对话。

    注意：当前实现是单条消息 → 完整回复（非流式 LLM）。
    M3.1 简化版：客户端发一条，服务端返回完整 AgentResponse。
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "detail": "invalid JSON"})
                continue

            action = payload.get("action")
            if action != "send":
                await websocket.send_json(
                    {"type": "error", "detail": f"unknown action: {action}"}
                )
                continue

            message = payload.get("message", "").strip()
            if not message:
                await websocket.send_json({"type": "error", "detail": "empty message"})
                continue

            await websocket.send_json({"type": "tick_start", "thread_id": thread_id})

            # Run in thread pool to avoid blocking the event loop.
            resp = await asyncio.to_thread(
                agent.process_message,
                message=message,
                thread_id=thread_id,
            )

            await websocket.send_json(
                {
                    "type": "done",
                    "thread_id": thread_id,
                    "message": resp.message,
                    "tick_count": resp.tick_count,
                    "tool_calls": resp.tool_calls,
                    "stages": resp.stages,
                }
            )
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: thread_id={thread_id}")
