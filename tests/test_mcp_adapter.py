"""MCPAdapter 集成测试 (M3.3)。

启动一个 mock MCP server 子进程, 验证:
- 连接 + initialize 握手
- list_tools 正确
- call_tool 转发
- 注册到 ToolRegistry 后能正常用
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cogcore.mcp_adapter import MCPAdapter, MCPClient, MCPServerConfig
from cogcore.tools import ToolRegistry


HERE = Path(__file__).parent
MOCK_SERVER = HERE / "mock_mcp_server.py"


def _make_mock_config(name: str = "mock") -> MCPServerConfig:
    return MCPServerConfig(
        name=name,
        command=sys.executable,
        args=[str(MOCK_SERVER)],
        enabled=True,
    )


# ============================================================
# 单 server 客户端
# ============================================================


def test_client_start_and_initialize():
    client = MCPClient(_make_mock_config())
    client.start()
    try:
        assert client.is_running
        assert client._server_info.get("serverInfo", {}).get("name") == "mock-mcp"
    finally:
        client.stop()


def test_client_list_tools():
    client = MCPClient(_make_mock_config())
    client.start()
    try:
        tools = client.list_tools()
        assert len(tools) == 2
        names = {t["name"] for t in tools}
        assert names == {"echo", "add"}
    finally:
        client.stop()


def test_client_call_echo():
    client = MCPClient(_make_mock_config())
    client.start()
    try:
        result = client.call_tool("echo", {"text": "hello"})
        assert result == "hello"
    finally:
        client.stop()


def test_client_call_add():
    client = MCPClient(_make_mock_config())
    client.start()
    try:
        result = client.call_tool("add", {"a": 3, "b": 4})
        assert result == "7"
    finally:
        client.stop()


def test_client_call_unknown_tool():
    client = MCPClient(_make_mock_config())
    client.start()
    try:
        with pytest.raises(RuntimeError) as exc_info:
            client.call_tool("nonexistent", {})
        assert "unknown tool" in str(exc_info.value) or "error" in str(exc_info.value).lower()
    finally:
        client.stop()


def test_client_stop_is_idempotent():
    client = MCPClient(_make_mock_config())
    client.start()
    client.stop()
    client.stop()  # 不应崩


# ============================================================
# Adapter 多 server 管理
# ============================================================


def test_adapter_add_server_requires_name():
    adapter = MCPAdapter()
    with pytest.raises(ValueError):
        adapter.add_server(MCPServerConfig(name="", command="x"))


def test_adapter_connect_all_returns_counts():
    adapter = MCPAdapter()
    adapter.add_server(_make_mock_config("srv1"))
    results = adapter.connect_all()
    try:
        assert results == {"srv1": 2}
        assert "srv1" in adapter.server_names()
    finally:
        adapter.disconnect_all()


def test_adapter_skips_disabled_servers():
    adapter = MCPAdapter()
    adapter.add_server(MCPServerConfig(
        name="disabled", command=sys.executable,
        args=[str(MOCK_SERVER)], enabled=False,
    ))
    results = adapter.connect_all()
    try:
        assert results == {}  # 没连
    finally:
        adapter.disconnect_all()


def test_adapter_handles_failed_server():
    adapter = MCPAdapter()
    # 启动一个不存在的命令
    adapter.add_server(MCPServerConfig(
        name="bad", command="/nonexistent/command", args=[]
    ))
    results = adapter.connect_all()
    try:
        assert results == {"bad": -1}
    finally:
        adapter.disconnect_all()


# ============================================================
# Adapter → ToolRegistry 注册
# ============================================================


def test_adapter_register_all_into_registry():
    adapter = MCPAdapter()
    adapter.add_server(_make_mock_config("mock"))
    adapter.connect_all()
    try:
        reg = ToolRegistry()
        count = adapter.register_all(reg)
        assert count == 2
        # 工具名加 server 前缀
        names = reg.get_available_tools()
        assert "mcp__mock__echo" in names
        assert "mcp__mock__add" in names
    finally:
        adapter.disconnect_all()


def test_registry_call_mcp_tool():
    adapter = MCPAdapter()
    adapter.add_server(_make_mock_config("mock"))
    adapter.connect_all()
    try:
        reg = ToolRegistry()
        adapter.register_all(reg)
        result = reg.execute_tool("mcp__mock__echo", {"text": "hi"})
        assert result == "hi"
    finally:
        adapter.disconnect_all()


def test_registry_call_mcp_tool_missing_required():
    adapter = MCPAdapter()
    adapter.add_server(_make_mock_config("mock"))
    adapter.connect_all()
    try:
        reg = ToolRegistry()
        adapter.register_all(reg)
        result = reg.execute_tool("mcp__mock__add", {"a": 1})  # 缺 b
        assert "Error" in result or "missing" in result.lower()
    finally:
        adapter.disconnect_all()


# ============================================================
# Context manager
# ============================================================


def test_adapter_context_manager():
    with MCPAdapter() as adapter:
        adapter.add_server(_make_mock_config("mock"))
        # 重新连接 (context manager 入口已调过 connect_all)
        results = adapter.connect_all()
        assert "mock" in results
    # 退出 context manager 后应该 disconnect
    assert adapter.server_names() == []


def test_adapter_multiple_servers():
    adapter = MCPAdapter()
    adapter.add_server(_make_mock_config("alpha"))
    adapter.add_server(_make_mock_config("beta"))
    results = adapter.connect_all()
    try:
        assert set(results.keys()) == {"alpha", "beta"}
        reg = ToolRegistry()
        adapter.register_all(reg)
        names = reg.get_available_tools()
        assert "mcp__alpha__echo" in names
        assert "mcp__beta__echo" in names
        assert "mcp__alpha__add" in names
        assert "mcp__beta__add" in names
    finally:
        adapter.disconnect_all()
