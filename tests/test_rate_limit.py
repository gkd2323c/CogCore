"""M5.2 速率限制测试。"""
from __future__ import annotations

from unittest.mock import patch

from app.middleware.rate_limit import RateLimitMiddleware


class FakeRequest:
    def __init__(self):
        self.headers = {}


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.headers = {}


def test_rate_limit_middleware_adds_retry_after():
    """429 响应补 Retry-After 头。"""
    middleware = RateLimitMiddleware(None)

    async def call_next(request):
        return FakeResponse(429)

    import asyncio
    response = asyncio.run(middleware.dispatch(FakeRequest(), call_next))
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "60"


def test_rate_limit_middleware_skips_non_429():
    """非 429 不补头。"""
    middleware = RateLimitMiddleware(None)

    async def call_next(request):
        return FakeResponse(200)

    import asyncio
    response = asyncio.run(middleware.dispatch(FakeRequest(), call_next))
    assert response.status_code == 200
    assert "Retry-After" not in response.headers
