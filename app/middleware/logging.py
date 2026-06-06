"""M5.2 结构化请求日志中间件。

每请求记录 JSON Lines 到 stdout：
  {"ts": "...", "method": "POST", "path": "/chat", "status": 200, "duration_ms": 45, "client_ip": "127.0.0.1"}

systemd/journald 负责收集，不引入文件日志轮转。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("cogcore.access")


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """结构化请求日志中间件。"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration_ms = round((time.time() - start) * 1000, 2)

        record: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client_ip": request.client.host if request.client else None,
        }
        logger.info(json.dumps(record, ensure_ascii=False, default=str))
        return response
