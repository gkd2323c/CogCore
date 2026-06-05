"""MCP 集成演示。

启动一个 mock MCP server (3 个工具), 把它注册到 ToolRegistry,
然后通过 CogCore Agent 调用。

工具:
- echo(text): 回显
- add(a, b): 加法
- reverse(text): 反转
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
os.environ["COGCORE_LLM_ENDPOINT"] = "https://api.deepseek.com/v1"
os.environ["COGCORE_LLM_API_KEY"] = "sk-30f3ba9b7c89444ab79145ce2700c34a"
os.environ["COGCORE_LLM_MODEL"] = "deepseek-chat"
os.environ["COGCORE_SERVICE_DATA_DIR"] = "cogcore_data_mcp_demo"

from cogcore.agent import CogCoreAgent
from cogcore.llm_bridge import LLMBridge
from cogcore.mcp_adapter import MCPAdapter, MCPServerConfig
from cogcore.service import CogCoreService
from cogcore.tools import ToolRegistry, register_default_tools, register_long_term_tools, LongTermExperienceTools


HERE = Path(__file__).parent
MOCK_SERVER = HERE.parent / "tests" / "mock_mcp_server.py"


def main() -> None:
    print("=== CogCore x MCP 集成演示 ===\n")

    # 1. 启动 MCP server
    print("1. 启动 mock MCP server...")
    adapter = MCPAdapter()
    adapter.add_server(MCPServerConfig(
        name="demo",
        command=sys.executable,
        args=[str(MOCK_SERVER)],
    ))
    results = adapter.connect_all()
    print(f"   连接结果: {results}")
    print(f"   Server names: {adapter.server_names()}\n")

    # 2. 注册到 ToolRegistry
    print("2. 注册 MCP 工具到 ToolRegistry...")
    svc = CogCoreService()
    svc.config.service.tick_interval = 0
    reg = ToolRegistry()
    register_default_tools(reg)
    lt = LongTermExperienceTools(svc._hdb, svc._pool, db_path=os.path.join(svc._data_dir, "diary.db"))
    register_long_term_tools(reg, lt)
    count = adapter.register_all(reg)
    print(f"   注册了 {count} 个 MCP 工具")
    print(f"   当前所有工具: {sorted(reg.get_available_tools())}\n")

    # 3. 直接调一次
    print("3. 直接调一次 MCP 工具（绕过 LLM）...")
    result = reg.execute_tool("mcp__demo__add", {"a": 17, "b": 25})
    print(f"   add(17, 25) = {result!r}\n")

    # 4. 通过 LLM Agent 调用
    print("4. 用 DeepSeek Agent 通过工具调用...")
    bridge = LLMBridge()
    agent = CogCoreAgent(service=svc, bridge=bridge, registry=reg)
    agent._service.config.service.tick_interval = 0

    msgs = [
        "用 reverse 工具反转 'Hello MCP'",
        "用 add 算 100 + 200",
    ]
    for msg in msgs:
        print(f"\n   [User] {msg}")
        resp = agent.process_message(msg)
        print(f"   [Agent] {resp.message[:200]}")
        if resp.tool_calls:
            print(f"          tool_calls: {resp.tool_calls}")

    # 5. 清理
    adapter.disconnect_all()
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
