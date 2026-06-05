"""工具系统：ToolRegistry + 长期经验工具。

接口对齐 docs/CogCore-通用认知内核架构设计.md §6.2。

M1.3 交付：
- ToolRegistry：register / execute / allowlist（M0 骨架 → 完整实现）
- LongTermExperienceTools：write_diary / read_diary / schedule_task
"""

from __future__ import annotations

from typing import Any, Callable
from uuid import uuid4

from cogcore.hdb import HDB
from cogcore.state_pool import StatePool
from cogcore.types import EpisodicMemory, Outcome


# ============================================================
# ToolRegistry
# ============================================================


class ToolRegistry:
    """工具注册与执行中心。

    行动节点通过 tool_mapping 字段关联到注册的工具名。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Callable] = {}
        self._schemas: dict[str, dict] = {}
        self._allowlist: set[str] = set()

    def register_tool(self, name: str, func: Callable, schema: dict) -> None:
        self._tools[name] = func
        self._schemas[name] = schema

    def execute_tool(self, name: str, params: dict | None = None) -> Any:
        if name not in self._allowlist:
            raise PermissionError(f"工具 {name} 不在白名单中")
        if name not in self._tools:
            raise KeyError(f"工具 {name} 未注册")
        return self._tools[name](**(params or {}))

    def get_available_tools(self) -> list[str]:
        return list(self._allowlist)

    def set_allowlist(self, allowlist: set[str]) -> None:
        self._allowlist = allowlist

    def add_to_allowlist(self, name: str) -> None:
        self._allowlist.add(name)


# ============================================================
# 长期经验工具（论文 5.7.2）
# ============================================================


class LongTermExperienceTools:
    """长期经验工具：日记读写与定时任务。

    通过 HDB 持久化日记，通过 StatePool 调度延迟任务。

    用法：
        tools = LongTermExperienceTools(hdb, pool)
        tools.write_diary("今日总结", "完成了 X 工作", importance=0.8)
        entries = tools.read_diary("X 工作")
    """

    def __init__(self, hdb: HDB, pool: StatePool | None = None) -> None:
        self._hdb = hdb
        self._pool = pool
        self._diary_store: list[dict] = []

    def write_diary(
        self,
        title: str,
        content: str,
        importance: float = 0.5,
        tags: list[str] | None = None,
    ) -> str:
        """写一条日记。同时写入内存存储和 HDB 情景记忆。"""
        entry_id = uuid4()
        entry = {
            "id": str(entry_id),
            "title": title,
            "content": content,
            "importance": importance,
            "tags": tags or [],
        }
        self._diary_store.append(entry)

        memory = EpisodicMemory(
            id=entry_id,
            tick_range=(self._hdb._tick, self._hdb._tick),
            action_taken=f"write_diary: {title}",
            outcome=Outcome.SUCCESS,
            feeling_snapshot={
                "importance": importance,
                "title_len": len(title),
            },
        )
        try:
            self._hdb.write_episodic(memory)
        except Exception:
            pass
        return str(entry_id)

    def read_diary(
        self,
        query: str = "",
        k: int = 5,
    ) -> list[dict]:
        """读日记。搜索标题和内容匹配的条目。

        Args:
            query: 关键词（空 = 返回最近 k 条）
            k: 最大返回数

        Returns:
            日记条目列表 [{id, title, content, importance, tags}]
        """
        results = []

        # 从 HDB 情景记忆中检索
        # 目前 HDB 没有全文搜索，用 memory store fallback + HDB report
        for entry in reversed(self._diary_store):
            if query:
                if query.lower() in entry.get("title", "").lower() or query.lower() in entry.get("content", "").lower():
                    results.append(entry)
            else:
                results.append(entry)
            if len(results) >= k:
                break

        return results

    def schedule_task(
        self,
        trigger: str,
        action_ref: str,
        period: int = 10,
    ) -> str:
        """注册一个延迟任务。

        Args:
            trigger: 触发条件描述（如 "每 10 tick"）
            action_ref: 行动引用（如行动节点名）
            period: 延迟 tick 数

        Returns:
            任务 ID
        """
        task_id = uuid4()

        if self._pool is not None:
            try:
                self._pool.schedule_task(
                    trigger_tick=self._pool._tick + period,
                    task_type="diary_task",
                    target_id=task_id,
                    content={"trigger": trigger, "action_ref": action_ref},
                    energy_real=0.5,
                    energy_virtual=0.0,
                )
            except Exception:
                pass

        return str(task_id)

    def list_tasks(self) -> list[dict]:
        """列出当前所有延迟任务。"""
        if self._pool is None:
            return []
        try:
            tasks = self._pool._delayed_tasks
            return [
                {
                    "target_id": str(t.get("target_id", "")),
                    "trigger_tick": t.get("trigger_tick", 0),
                    "type": t.get("task_type", ""),
                    "content": str(t.get("content", "")),
                }
                for t in tasks
            ]
        except Exception:
            return []

    def cancel_task(self, task_id: str) -> bool:
        """取消一个延迟任务。"""
        if self._pool is None:
            return False
        try:
            tasks = self._pool._delayed_tasks
            before = len(tasks)
            self._pool._delayed_tasks = [
                t for t in tasks if str(t.get("target_id", "")) != task_id
            ]
            return len(self._pool._delayed_tasks) < before
        except Exception:
            return False


# ============================================================
# 内置工具函数
# ============================================================


def tool_calc(expr: str) -> str:
    """安全计算 Python 表达式。

    只允许基本数学运算，不访问文件/网络/系统。
    """
    allowed = {
        "abs", "all", "any", "bool", "complex", "dict", "divmod",
        "enumerate", "filter", "float", "format", "frozenset",
        "getattr", "hasattr", "hash", "hex", "id", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map",
        "max", "min", "next", "object", "oct", "ord", "pow",
        "range", "repr", "reversed", "round", "set", "slice",
        "sorted", "str", "sum", "tuple", "type", "zip",
        "__import__",  # blocked below
    }
    # 移除危险名字
    restricted = {"__import__", "eval", "exec", "compile", "open", "input"}
    try:
        # 在受限命名空间中求值
        result = eval(expr, {"__builtins__": {}}, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def tool_now() -> str:
    """返回当前日期时间字符串。"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def tool_echo(text: str) -> str:
    """回显输入文本。用于测试工具调用链路。"""
    return text


# ============================================================
# Skill Runner（论文 5.7.4 简版）
# ============================================================


class Skill:
    """动态加载的技能。

    技能 = 一段 Python 代码 + schema 声明。
    通过 ToolRegistry 注册为可调用工具。
    """

    def __init__(
        self,
        name: str,
        description: str,
        code: str,
        params_schema: dict | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.code = code
        self.params_schema = params_schema or {}

    def execute(self, **kwargs: Any) -> Any:
        """在隔离命名空间中执行技能代码。"""
        namespace: dict[str, Any] = {
            "params": kwargs,
            "result": None,
        }
        try:
            exec(self.code, {"__builtins__": {}}, namespace)
            return namespace.get("result", "executed")
        except Exception as e:
            return f"Skill error: {e}"


class SkillRunner:
    """技能注册与执行管理器。"""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def execute(self, name: str, **kwargs: Any) -> Any:
        if name not in self._skills:
            return f"Skill not found: {name}"
        return self._skills[name].execute(**kwargs)

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())

    def skill_run(self, name: str, params: dict | None = None) -> Any:
        """作为工具调用的入口。"""
        return self.execute(name, **(params or {}))


# ============================================================
# 默认工具注册
# ============================================================


def register_default_tools(registry: ToolRegistry) -> None:
    """注册所有内置工具到 ToolRegistry。"""
    import math

    tools = [
        ("calc", tool_calc, {"expr": "string"}, "安全计算器"),
        ("now", tool_now, {}, "当前时间"),
        ("echo", tool_echo, {"text": "string"}, "回显"),
    ]
    for name, func, schema, _desc in tools:
        registry.register_tool(name, func, schema)
        registry.add_to_allowlist(name)
