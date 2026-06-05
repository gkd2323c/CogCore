"""ToolExecutor：解析 LLM 输出中的工具调用标记并执行。

支持两种格式：
1. XML 标记：<tool>name({"key": "value"})</tool>
2. OpenAI function_call 原生格式（由 SDK 返回）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from cogcore.tools import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """解析并执行 LLM 回复中的工具调用。

    用法：
        executor = ToolExecutor(registry)
        results = executor.parse_and_execute(llm_response)
        # [{"name": "search", "args": {...}, "result": "..."}, ...]
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def parse_and_execute(self, llm_response: str) -> list[dict]:
        """解析 LLM 回复，找到所有工具调用并执行。

        Args:
            llm_response: LLM 回复文本

        Returns:
            工具执行结果列表：[{name, args, result, error?}]
        """
        results = []

        # 方式 1: XML 标记 <tool>name(args)</tool>
        xml_calls = self._parse_xml_calls(llm_response)
        for name, args in xml_calls:
            result = self._execute_one(name, args)
            results.append(result)

        # 方式 2: 尝试解析 JSON 格式的 tool_calls 块
        if not xml_calls:
            json_calls = self._parse_json_calls(llm_response)
            for name, args in json_calls:
                result = self._execute_one(name, args)
                results.append(result)

        return results

    def _parse_xml_calls(self, text: str) -> list[tuple[str, dict]]:
        """解析 <tool>name({"key": "val"})</tool> 格式。"""
        calls = []
        pattern = re.compile(r"<tool>(.*?)</tool>", re.DOTALL)
        for match in pattern.finditer(text):
            content = match.group(1).strip()
            # 格式: name({"key": "value"}) 或 name
            paren = content.find("(")
            if paren > 0:
                name = content[:paren].strip()
                args_str = content[paren + 1 :]
                if args_str.endswith(")"):
                    args_str = args_str[:-1]
                try:
                    args = json.loads(args_str) if args_str.strip() else {}
                except json.JSONDecodeError:
                    args = {"input": args_str} if args_str.strip() else {}
            else:
                name = content
                args = {}
            calls.append((name, args))
        return calls

    def _parse_json_calls(self, text: str) -> list[tuple[str, dict]]:
        """解析 JSON 格式的工具调用块。"""
        calls = []
        # 查找 ```json ... ``` 或 ``` ... ``` 块
        pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
        for match in pattern.finditer(text):
            try:
                data = json.loads(match.group(1))
                if isinstance(data, dict) and "tool" in data:
                    calls.append((data["tool"], data.get("args", {})))
            except json.JSONDecodeError:
                pass
        return calls

    def _execute_one(self, name: str, args: dict) -> dict:
        """执行单个工具调用。"""
        try:
            result = self._registry.execute_tool(name, args)
            logger.info(f"Tool {name} executed: {str(result)[:100]}")
            return {
                "name": name,
                "args": args,
                "result": result,
                "error": None,
            }
        except PermissionError as e:
            logger.warning(f"Tool {name} blocked: {e}")
            return {
                "name": name,
                "args": args,
                "result": None,
                "error": f"Tool not allowed: {name}",
            }
        except KeyError:
            logger.warning(f"Tool {name} not registered")
            return {
                "name": name,
                "args": args,
                "result": None,
                "error": f"Tool not found: {name}",
            }
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            return {
                "name": name,
                "args": args,
                "result": None,
                "error": str(e),
            }
