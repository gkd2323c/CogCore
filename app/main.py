"""FastAPI 应用入口。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
或：
    python -m app.main
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

from app.api.v1 import chat, diary, status, ws

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """构造 FastAPI 应用。"""
    app = FastAPI(
        title="CogCore API",
        description=(
            "CogCore 通用认知内核 HTTP/WebSocket 接口。\n\n"
            "M3.1 阶段：5 个端点（chat / ws / status / diary / health）。"
        ),
        version="0.3.0",
    )
    app.include_router(chat.router)
    app.include_router(diary.router)
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
