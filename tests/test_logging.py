"""M5.2 结构化日志测试。"""
from __future__ import annotations

import json
import logging

from app.middleware.logging import StructuredLoggingMiddleware


class FakeRequest:
    def __init__(self, method="GET", path="/test", client_host="127.0.0.1"):
        self.method = method
        self.url = type("U", (), {"path": path})()
        self.client = type("C", (), {"host": client_host})()


class FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


def test_structured_log_format(caplog):
    """输出为合法 JSON。"""
    caplog.set_level(logging.INFO, logger="cogcore.access")
    middleware = StructuredLoggingMiddleware(None)

    async def call_next(request):
        return FakeResponse(200)

    import asyncio
    asyncio.run(middleware.dispatch(FakeRequest(), call_next))

    records = [r for r in caplog.records if r.name == "cogcore.access"]
    assert len(records) == 1
    log_line = records[0].message
    parsed = json.loads(log_line)
    assert isinstance(parsed, dict)


def test_structured_log_fields(caplog):
    """含 method, path, status, duration_ms, client_ip。"""
    caplog.set_level(logging.INFO, logger="cogcore.access")
    middleware = StructuredLoggingMiddleware(None)

    async def call_next(request):
        return FakeResponse(201)

    import asyncio
    asyncio.run(middleware.dispatch(FakeRequest(method="POST", path="/chat", client_host="192.168.1.1"), call_next))

    records = [r for r in caplog.records if r.name == "cogcore.access"]
    assert len(records) == 1
    parsed = json.loads(records[0].message)
    assert parsed["method"] == "POST"
    assert parsed["path"] == "/chat"
    assert parsed["status"] == 201
    assert "duration_ms" in parsed
    assert parsed["client_ip"] == "192.168.1.1"
