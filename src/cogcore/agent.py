"""CogCoreAgent：5 步消息流实现的端到端 Agent（M2.2）。

对齐论文 §6.1.2 的 5 步消息处理顺序：
1. should_wake → 判断是否值得进入主链
2. CogCore tick(s) → 生成认知状态
3. build_context_packet → 翻译为 LLM prompt
4. LLM → tool_executor → 结果回写 CogCore
5. 最终回复
"""

from __future__ import annotations

import logging
from typing import Any

from cogcore.graph import invoke_cogcore
from cogcore.llm_bridge import LLMBridge
from cogcore.modes import AgentMode, WakeController
from cogcore.service import CogCoreService
from cogcore.tool_executor import ToolExecutor
from cogcore.tools import ToolRegistry

logger = logging.getLogger(__name__)


class AgentResponse:
    """Agent 回复。"""

    def __init__(
        self,
        message: str,
        tick_count: int = 0,
        tool_calls: int = 0,
        stages: int = 0,
    ) -> None:
        self.message = message
        self.tick_count = tick_count
        self.tool_calls = tool_calls
        self.stages = stages

    def __repr__(self) -> str:
        return (
            f"AgentResponse(msg={self.message[:50]!r}, "
            f"ticks={self.tick_count}, tools={self.tool_calls})"
        )


class CogCoreAgent:
    """CogCore 驱动的端到端 Agent。

    用法：
        agent = CogCoreAgent()
        response = agent.process_message("北京明天天气")
        print(response.message)
    """

    def __init__(
        self,
        service: CogCoreService | None = None,
        bridge: LLMBridge | None = None,
        registry: ToolRegistry | None = None,
    ) -> None:
        self._service = service or CogCoreService()
        self._bridge = bridge or LLMBridge()
        self._registry = registry or ToolRegistry()
        self._executor = ToolExecutor(self._registry)
        self._wake = WakeController(mode=AgentMode.FULL_SILENT)

    # ============================================================
    # 5 步消息流
    # ============================================================

    def process_message(
        self,
        message: str,
        thread_id: str = "default",
        system_prompt: str | None = None,
        max_tool_turns: int = 3,
    ) -> AgentResponse:
        """处理一条用户消息，返回 Agent 回复。

        内部执行 5 步流：
        1. should_wake — 检查是否有外源输入
        2. CogCore tick — 执行认知闭环
        3. build_context_packet — 翻译为 LLM prompt
        4. LLM + tool_executor — 调用 LLM，执行工具
        5. 最终回复 — 收集结果并返回
        """
        # ── Step 1: Should wake ──
        decision = self._wake.should_wake(
            event={"raw_input": message, "has_external_input": True}
        )
        if not decision:
            return AgentResponse(
                message="", tick_count=self._service._tick_count
            )

        total_tool_calls = 0

        # ── Step 2: CogCore tick ──
        state = self._service.tick(raw_input=message)
        stages_count = len(state.get("stages_log", []))

        # ── Step 3: Build context packet ──
        packet = self._bridge.build_context_packet(state, max_tokens=2000)

        # ── Step 4: LLM + tool_executor loop ──
        messages = [
            {
                "role": "system",
                "content": system_prompt
                or (
                    "You are an AI assistant powered by CogCore cognitive state. "
                    "Use the provided cognitive context to respond naturally. "
                    "If you need to use a tool, write: "
                    "<tool>tool_name({\"key\": \"value\"})</tool>"
                ),
            },
            {"role": "user", "content": packet},
        ]

        final_response = ""
        for turn in range(max_tool_turns):
            llm_response = self._bridge.chat(messages)
            if llm_response.startswith("[LLM Error"):
                final_response = llm_response
                break

            # 解析并执行工具调用
            tool_results = self._executor.parse_and_execute(llm_response)

            if not tool_results:
                # 没有工具调用 = 最终回复
                final_response = llm_response
                break

            # 有工具调用：把结果注入 CogCore 并继续
            total_tool_calls += len(tool_results)
            for tr in tool_results:
                result_text = (
                    f"Tool {tr['name']} returned: {tr['result']}"
                    if tr["error"] is None
                    else f"Tool {tr['name']} error: {tr['error']}"
                )
                # 注入回 CogCore
                self._service.tick(raw_input=result_text)

                # 同时注入 LLM 上下文
                messages.append({"role": "assistant", "content": llm_response})
                messages.append(
                    {
                        "role": "user",
                        "content": f"[Tool Result] {result_text}",
                    }
                )

        # ── Step 5: Return ──
        return AgentResponse(
            message=final_response or "(no response)",
            tick_count=self._service._tick_count,
            tool_calls=total_tool_calls,
            stages=stages_count,
        )
