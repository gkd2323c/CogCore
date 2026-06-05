"""CogCore Agent 交互式演示（M2.2）。

运行本地 CogCore 认知内核 + mock LLM（不依赖真实 Ollama）。

用法：
    cd C:\\Users\\gkd2323c\\Documents\\CogCore
    $env:PYTHONPATH = "src"
    python scripts/demo_agent.py [--real-llm]
"""

from __future__ import annotations

import argparse
import sys
from unittest.mock import MagicMock

from cogcore.agent import CogCoreAgent
from cogcore.config import get_config
from cogcore.llm_bridge import LLMBridge
from cogcore.service import CogCoreService
from cogcore.tools import ToolRegistry


def _utf8():
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _make_mock_llm():
    """构造一个简单的 mock LLM，处理工具调用。"""
    mock = MagicMock(spec=LLMBridge)
    cfg = get_config()

    def chat_side_effect(messages, **kwargs):
        last = messages[-1]["content"] if messages else ""
        last_lower = last.lower()

        # 简单模式匹配：模拟工具调用
        if "weather" in last_lower or "天气" in last_lower:
            return '<tool>query_weather({"city": "Beijing"})</tool>'
        if "add" in last_lower or "计算" in last_lower:
            return '<tool>calc({"expr": "1+1"})</tool>'
        if "tool" in last_lower and "returned" in last_lower:
            return f"收到工具结果: {last[:80]}"
        if "diary" in last_lower or "日记" in last_lower:
            return "已经为你记录了日记。"
        return (
            f"[CogCore Agent] 已收到你的消息。"
            f" (model={cfg.llm.model})"
        )

    mock.chat = MagicMock(side_effect=chat_side_effect)
    mock.build_context_packet = MagicMock(
        return_value="=== COGCORE CONTEXT ===\n[CURRENT INPUT]\n...\n[ENERGY STATE]\n..."
    )
    return mock


def main():
    _utf8()
    parser = argparse.ArgumentParser(description="CogCore Agent 演示")
    parser.add_argument("--real-llm", action="store_true", help="使用真实 Ollama LLM")
    args = parser.parse_args()

    # 工具注册
    registry = ToolRegistry()
    registry.register_tool("ping", lambda: "pong", {})
    registry.register_tool("calc", lambda expr: eval(expr), {"expr": "string"})
    registry.add_to_allowlist("ping")
    registry.add_to_allowlist("calc")

    # Service
    service = CogCoreService()
    service.config.service.tick_interval = 0

    # LLM
    if args.real_llm:
        bridge = LLMBridge()
        print(f"Using real LLM: {bridge.model}")
    else:
        bridge = _make_mock_llm()
        print("Using mock LLM (pass --real-llm for real Ollama)")

    # Agent
    agent = CogCoreAgent(service=service, bridge=bridge, registry=registry)

    print(f"\n{'='*50}")
    print(f"CogCore Agent Demo (M2.2)")
    print(f"{'='*50}")
    print(f"Available tools: ping, calc")
    print(f"Type 'exit' to quit.\n")

    while True:
        try:
            text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text.lower() in ("exit", "quit"):
            break

        resp = agent.process_message(text)
        status = agent._service.get_status()

        print(f"Agent: {resp.message}")
        if resp.tool_calls > 0:
            print(f"       (tools called: {resp.tool_calls})")
        print(f"       [tick={resp.tick_count}, "
              f"pool={status['pool']['active']}a "
              f"pressure={status['pool']['pressure']:.2f}]")
        print()

    print("Bye.")


if __name__ == "__main__":
    main()
