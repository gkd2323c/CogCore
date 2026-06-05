"""ToolExecutor 单元测试。"""
from __future__ import annotations

import pytest

from cogcore.tool_executor import ToolExecutor
from cogcore.tools import ToolRegistry


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register_tool("greet", lambda name: f"Hello {name}!", {"name": "string"})
    r.register_tool("add", lambda a, b: a + b, {"a": "int", "b": "int"})
    r.register_tool("ping", lambda: "pong", {})
    r.add_to_allowlist("greet")
    r.add_to_allowlist("add")
    r.add_to_allowlist("ping")
    return r


@pytest.fixture
def executor(registry):
    return ToolExecutor(registry)


def test_parse_xml_simple(executor):
    results = executor.parse_and_execute('<tool>ping()</tool>')
    assert len(results) == 1
    assert results[0]["name"] == "ping"
    assert results[0]["result"] == "pong"


def test_parse_xml_with_args(executor):
    results = executor.parse_and_execute(
        '<tool>greet({"name": "CogCore"})</tool>'
    )
    assert len(results) == 1
    assert results[0]["name"] == "greet"
    assert results[0]["result"] == "Hello CogCore!"


def test_parse_xml_multiple(executor):
    text = """
    First tool: <tool>ping()</tool>
    Second tool: <tool>add({"a": 3, "b": 4})</tool>
    """
    results = executor.parse_and_execute(text)
    assert len(results) == 2
    assert results[1]["result"] == 7


def test_parse_xml_with_llm_text(executor):
    """工具调用夹在 LLM 文本中也能被正确提取。"""
    text = (
        "I'll check that for you. "
        '<tool>greet({"name": "test"})</tool>'
        " Let me know if you need anything else."
    )
    results = executor.parse_and_execute(text)
    assert len(results) == 1
    assert "Hello" in results[0]["result"]


def test_no_tool_call_returns_empty(executor):
    results = executor.parse_and_execute("Just a normal response.")
    assert len(results) == 0


def test_unregistered_tool(executor):
    results = executor.parse_and_execute('<tool>nonexistent()</tool>')
    assert len(results) == 1
    assert results[0]["error"] is not None


def test_blocked_tool(executor):
    """不在 allowlist 中的工具应被阻止。"""
    ex = ToolExecutor(ToolRegistry())
    results = ex.parse_and_execute('<tool>ping()</tool>')
    assert len(results) == 1
    assert "not allowed" in results[0]["error"]


def test_tool_error_doesnt_crash(executor):
    """工具执行失败不应中断整体流程。"""
    r = ToolExecutor(ToolRegistry())
    results = r.parse_and_execute('<tool>nonexistent()</tool>')
    assert len(results) == 1
    assert results[0]["error"] is not None


def test_execute_one(executor):
    result = executor._execute_one("add", {"a": 2, "b": 3})
    assert result["result"] == 5
    assert result["error"] is None
