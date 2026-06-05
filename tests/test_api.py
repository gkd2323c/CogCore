"""FastAPI 端点集成测试。

使用 FastAPI TestClient（基于 httpx），不启动真实 uvicorn。
"""
from __future__ import annotations

import os
import shutil

# 用临时数据目录跑测试，避免污染真实 cogcore_data
TEST_DATA_DIR = "cogcore_data_api_test"
os.environ["COGCORE_SERVICE_DATA_DIR"] = TEST_DATA_DIR

import pytest
from fastapi.testclient import TestClient

# 在导入 app 前先清空测试数据
if os.path.exists(TEST_DATA_DIR):
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)

from app.deps import get_bridge, reset_singletons  # noqa: E402
from app.main import app  # noqa: E402
from cogcore.llm_bridge import LLMBridge  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402


def _mock_llm_bridge() -> LLMBridge:
    """构造一个 mock LLMBridge，固定返回 'Mocked response'。"""
    mock_client = MagicMock()
    mr = MagicMock()
    mc = MagicMock()
    mc.content = "Mocked response"
    mr.choices = [type("c", (), {"message": mc})()]
    mock_client.chat.completions.create.return_value = mr
    return LLMBridge(client=mock_client)


@pytest.fixture(autouse=True)
def reset_and_mock():
    """每个测试前清空单例并 mock LLM。"""
    import gc
    gc.collect()
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    reset_singletons()
    monkey = pytest.MonkeyPatch()
    mock = _mock_llm_bridge()
    import app.deps as deps_module
    monkey.setattr(deps_module, "get_bridge", lambda: mock)
    yield monkey
    monkey.undo()
    reset_singletons()
    gc.collect()
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)


@pytest.fixture
def client():
    return TestClient(app)


# ============================================================
# 健康检查 & 状态
# ============================================================


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status(client):
    r = client.get("/v1/status")
    assert r.status_code == 200
    body = r.json()
    assert "running" in body
    assert "tick_count" in body
    assert "pool" in body


# ============================================================
# Chat
# ============================================================


def test_chat_basic(client):
    r = client.post(
        "/v1/chat",
        json={"message": "hello"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "message" in body
    assert body["thread_id"] == "default"
    assert body["tick_count"] >= 0


def test_chat_with_thread_id(client):
    r = client.post(
        "/v1/chat",
        json={"message": "hi", "thread_id": "session-1"},
    )
    assert r.status_code == 200
    assert r.json()["thread_id"] == "session-1"


def test_chat_empty_message_rejected(client):
    r = client.post("/v1/chat", json={"message": ""})
    assert r.status_code == 422  # Pydantic validation


# ============================================================
# Diary
# ============================================================


def test_write_diary(client):
    r = client.post(
        "/v1/diary",
        json={
            "title": "Test Entry",
            "content": "Test content",
            "importance": 0.7,
            "tags": ["test"],
        },
    )
    assert r.status_code == 200
    assert "diary_id" in r.json()


def test_read_diary_empty(client):
    r = client.get("/v1/diary")
    assert r.status_code == 200
    assert r.json() == []


def test_read_diary_after_write(client):
    client.post(
        "/v1/diary",
        json={"title": "Alice", "content": "First meet"},
    )
    r = client.get("/v1/diary")
    assert r.status_code == 200
    entries = r.json()
    assert len(entries) == 1
    assert entries[0]["title"] == "Alice"


def test_read_diary_search(client):
    client.post(
        "/v1/diary",
        json={"title": "Alice", "content": "She likes tea"},
    )
    client.post(
        "/v1/diary",
        json={"title": "Bob", "content": "He likes coffee"},
    )
    r = client.get("/v1/diary?query=Alice")
    assert r.status_code == 200
    entries = r.json()
    assert any("Alice" in e["title"] for e in entries)


def test_read_diary_k_validation(client):
    r = client.get("/v1/diary?k=200")
    assert r.status_code == 400


# ============================================================
# WebSocket
# ============================================================


def test_ws_send(client):
    with client.websocket_connect("/v1/ws/test-thread") as ws:
        ws.send_json({"action": "send", "message": "hi"})
        # Receive tick_start
        first = ws.receive_json()
        assert first["type"] == "tick_start"
        assert first["thread_id"] == "test-thread"
        # Receive done
        done = ws.receive_json()
        assert done["type"] == "done"
        assert "message" in done
        assert done["thread_id"] == "test-thread"


def test_ws_invalid_json(client):
    with client.websocket_connect("/v1/ws/test-thread") as ws:
        ws.send_text("not json")
        err = ws.receive_json()
        assert err["type"] == "error"


def test_ws_empty_message(client):
    with client.websocket_connect("/v1/ws/test-thread") as ws:
        ws.send_json({"action": "send", "message": "  "})
        err = ws.receive_json()
        assert err["type"] == "error"
