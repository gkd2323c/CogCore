"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
或：
    python -m app.main
或：
    python -m cogcore serve
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1 import chat, diary, hitl, multi_agent, scheduler, status, ws
from app.middleware.logging import StructuredLoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware, limiter

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """构造 FastAPI 应用。"""
    app = FastAPI(
        title="CogCore API",
        description=(
            "CogCore 通用认知内核 HTTP/WebSocket 接口。\n\n"
            "M5.2 阶段：serve CLI + JWT + slowapi + 结构化日志 + 5 个端点。"
        ),
        version="0.5.0",
    )
    # slowapi limiter 注册到 app.state
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 中间件（注意：先注册的后执行，所以顺序是 结构化日志 → 速率限制）
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(StructuredLoggingMiddleware)

    app.include_router(chat.router)
    app.include_router(diary.router)
    app.include_router(hitl.router)
    app.include_router(multi_agent.router)
    app.include_router(scheduler.router)
    app.include_router(status.router)
    app.include_router(ws.router)
    return app


app = create_app()


def main() -> None:
    """CLI 入口。"""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()
