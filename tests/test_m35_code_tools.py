"""M3.5 代码感知工具测试 (L12.1 自检)。"""
from __future__ import annotations

import pytest

from cogcore.tools import ToolRegistry
from cogcore.tools_code import (
    count_lines,
    find_test_for_module,
    list_modules,
    list_tests,
    read_file,
    register_code_tools,
    search_code,
)


# ============================================================
# 直接函数调用
# ============================================================


def test_read_file_basic():
    result = read_file("src/cogcore/types.py", offset=0, limit=10)
    # 包含行号 + 头部行
    assert "1|" in result or "types.py" in result or "StimulusSource" in result


def test_read_file_offset_and_limit():
    result = read_file("src/cogcore/types.py", offset=10, limit=5)
    # 应该有 5 行
    lines = [l for l in result.split("\n") if l and not l.startswith("[")]
    assert len(lines) == 5


def test_read_file_not_found():
    result = read_file("nonexistent.py")
    assert "Error" in result
    assert "not found" in result


def test_search_code_finds_something():
    results = search_code("class.*BaseModel", path="src/cogcore", glob="types.py")
    assert isinstance(results, list)
    # types.py 里应该有 BaseModel 子类
    assert len(results) > 0
    assert all("path" in r and "line" in r and "text" in r for r in results)


def test_search_code_invalid_regex():
    results = search_code("[invalid", path="src/cogcore")
    assert len(results) == 1
    assert "error" in results[0]


def test_search_code_max_results():
    results = search_code(".*", path="src/cogcore", max_results=3)
    assert len(results) <= 3


def test_list_modules():
    results = list_modules()
    assert isinstance(results, list)
    assert len(results) > 5
    # 应该包含核心模块
    names = {r["name"] for r in results}
    assert "types" in names
    assert "state_pool" in names
    assert "graph" in names
    # 每个模块有 lines 字段
    assert all("lines" in r and r["lines"] > 0 for r in results)


def test_list_tests():
    results = list_tests()
    assert isinstance(results, list)
    assert len(results) > 0
    paths = {r["path"] for r in results}
    assert any("test_config" in p for p in paths)
    # 每个文件有 test_count
    assert all("test_count" in r for r in results)


def test_find_test_for_module():
    # 已知对应关系
    result = find_test_for_module("src/cogcore/types.py")
    assert result is None  # types 没有专属测试


def test_find_test_for_module_with_test():
    result = find_test_for_module("src/cogcore/config.py")
    assert result is not None
    assert "config" in result


def test_count_lines():
    n = count_lines("src/cogcore/types.py")
    assert n > 50  # types.py 至少 50 行


def test_count_lines_not_found():
    n = count_lines("nonexistent.py")
    assert n == -1


# ============================================================
# ToolRegistry 集成
# ============================================================


def test_register_code_tools():
    reg = ToolRegistry()
    n = register_code_tools(reg)
    assert n == 6
    available = reg.get_available_tools()
    for name in ["read_file", "search_code", "list_modules", "list_tests",
                 "find_test_for_module", "count_lines"]:
        assert name in available


def test_read_file_through_registry():
    reg = ToolRegistry()
    register_code_tools(reg)
    result = reg.execute_tool("read_file", {"path": "src/cogcore/types.py", "offset": 0, "limit": 3})
    assert "StimulusSource" in result or "types.py" in result or "|" in result
