"""CogCoreAgent 测试（M2.2）。mock LLM 和工具，不依赖真实 LLM。"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cogcore.agent import CogCoreAgent
from cogcore.config import load_config
from cogcore.llm_bridge import LLMBridge
from cogcore.service import CogCoreService
from cogcore.tools import ToolRegistry


@pytest.fixture
def mock_bridge():
    """返回固定回复的 mock LLMBridge。"""
    mock = MagicMock(spec=LLMBridge)

    def chat_side_effect(messages, **kwargs):
        return "This is a mock response from LLM."

    mock.chat = MagicMock(side_effect=chat_side_effect)
    mock.build_context_packet = MagicMock(return_value="Mocked context packet")
    return mock


@pytest.fixture
def agent(mock_bridge):
    svc = CogCoreService()
    svc.config.service.tick_interval = 0
    reg = ToolRegistry()
    reg.register_tool("ping", lambda: "pong", {})
    reg.add_to_allowlist("ping")
    return CogCoreAgent(service=svc, bridge=mock_bridge, registry=reg)


def test_agent_created(agent):
    assert agent is not None


def test_process_message_returns_response(agent):
    resp = agent.process_message("hello")
    assert resp is not None
    assert isinstance(resp.message, str)


def test_process_message_increases_tick(agent):
    before = agent._service._tick_count
    agent.process_message("test")
    after = agent._service._tick_count
    assert after > before


def test_process_message_with_tool_call(agent, mock_bridge):
    """Agent 应处理 LLM 返回工具调用标记的情况。"""
    mock_bridge.chat = MagicMock(
        side_effect=[
            # First LLM call: returns tool call
            '<tool>ping()</tool>',
            # Second LLM call: returns final response
            "Tool executed. The result was pong.",
        ]
    )
    resp = agent.process_message("use tool")
    assert "pong" in resp.message or "Tool" in resp.message
    assert resp.tool_calls >= 1


def test_process_message_tool_loop_max_turns(agent, mock_bridge):
    """工具循环不应超过 max_tool_turns。"""
    mock_bridge.chat = MagicMock(return_value='<tool>ping()</tool>')
    resp = agent.process_message("loop test", max_tool_turns=2)
    # 即使一直在返回工具调用，也只应该执行 max_tool_turns 次
    assert resp.tool_calls <= 2


def test_process_message_empty_message(agent):
    resp = agent.process_message("")
    assert resp is not None


def test_process_message_preserves_cogcore_state(agent):
    """处理后 CogCore 状态应被更新。"""
    resp = agent.process_message("status check")
    status = agent._service.get_status()
    assert status["tick_count"] > 0
    assert status["pool"]["active"] >= 0


def test_agent_response_repr(agent):
    from cogcore.agent import AgentResponse
    r = AgentResponse(message="hello", tick_count=5, tool_calls=2, stages=10)
    assert "hello" in repr(r)
