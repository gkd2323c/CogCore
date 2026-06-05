"""工具链接口：与外部工具的注册与执行。

接口与 docs/CogCore-通用认知内核架构设计.md §6.2 完全对齐。
长期经验工具（write_diary / read_diary / schedule_task / skill_run）见 §6.2.1。
"""

from __future__ import annotations

from typing import Any, Callable


class ToolRegistry:
    """行动节点通过 tool_mapping 字段关联到具体工具。"""

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._allowlist: set[str] = set()

    def register_tool(
        self, name: str, func: Callable, schema: dict
    ) -> None:
        self._tools[name] = func
        self._schemas[name] = schema

    def execute_tool(self, name: str, params: dict) -> Any:
        if name not in self._allowlist:
            raise PermissionError(f"工具 {name} 不在白名单中")
        if name not in self._tools:
            raise KeyError(f"工具 {name} 未注册")
        return self._tools[name](**params)

    def get_available_tools(self) -> list[str]:
        return list(self._allowlist)

    def set_allowlist(self, allowlist: set[str]) -> None:
        self._allowlist = allowlist


class LongTermExperienceTools:
    """长期经验工具（论文 5.7.2）。"""

    def write_diary(self, title: str, content: str, importance: float) -> int:
        raise NotImplementedError("M1.4 待实现：写日记")

    def read_diary(self, query: str, k: int = 5) -> list[dict]:
        raise NotImplementedError("M1.4 待实现：读日记")

    def schedule_task(self, trigger: str, action_ref: str, period: int) -> int:
        raise NotImplementedError("M1.4 待实现：建定时任务")

    def list_tasks(self) -> list[dict]:
        raise NotImplementedError("M1.4 待实现：查任务")

    def cancel_task(self, task_id: int) -> None:
        raise NotImplementedError("M1.4 待实现：删任务")
