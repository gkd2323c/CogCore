"""M5.2 slowapi 速率限制中间件。

全局 100 req/min，/chat 单独 30 req/min。
超限返回 429 + Retry-After 头。
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 基于客户端 IP 的限速
limiter = Limiter(key_func=get_remote_address)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """全局速率限制中间件（slowapi 备用方案）。

    实际限速由 slowapi 装饰器在路由层处理；
    本中间件负责在超限响应中补 Retry-After 头。
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.status_code == 429:
            # 补 Retry-After 头（秒）
            if "retry-after" not in response.headers:
                response.headers["Retry-After"] = "60"
        return response
