"""M3.5 代码感知工具 (L12.1 自检)。

让 Agent 读自己源码、找模块、定位测试。

工具：
- read_file(path, offset, limit): 读源码片段
- search_code(pattern, path, glob): 按 regex 找代码
- list_modules(): 列出 src/cogcore/ 下所有模块
- list_tests(): 列出所有测试文件
- find_test_for_module(module_path): 根据 module 推断测试文件
- count_lines(path): 文件行数

设计：
- 用 pathlib 读文件
- 用 re 做 regex 搜索
- 所有路径都相对于 project root
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    """项目根目录（这个文件所在目录的 parent）。"""
    return Path(__file__).resolve().parent.parent.parent


def _resolve(path: str) -> Path:
    """把相对路径解析到项目根。"""
    p = Path(path)
    if p.is_absolute():
        return p
    return _project_root() / p


def read_file(path: str, offset: int = 0, limit: int = 200) -> str:
    """读源码片段。

    Args:
        path: 相对项目根的路径
        offset: 起始行（0-indexed）
        limit: 最多读多少行

    Returns:
        带行号的源码字符串, 或错误信息
    """
    try:
        p = _resolve(path)
        if not p.exists():
            return f"Error: file not found: {path}"
        if not p.is_file():
            return f"Error: not a file: {path}"
        with p.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        end = min(offset + limit, total)
        if offset >= total:
            return f"Error: offset {offset} >= total lines {total}"
        # 行号格式: 0001|+5
        out_lines: list[str] = []
        for i in range(offset, end):
            out_lines.append(f"{i+1:4d}| {lines[i].rstrip()}")
        return "\n".join(out_lines) + f"\n[{offset+1}-{end} of {total} lines]"
    except Exception as e:
        return f"Error: {e}"


def search_code(
    pattern: str,
    path: str = "src/cogcore",
    glob: str = "*.py",
    max_results: int = 50,
) -> list[dict[str, Any]]:
    """按 regex 找代码。

    Args:
        pattern: regex 字符串
        path: 搜索根目录
        glob: 文件 glob 模式
        max_results: 最多返回条数

    Returns:
        [{path, line, text}, ...]
    """
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return [{"error": f"invalid regex: {e}"}]
    root = _resolve(path)
    if not root.exists():
        return [{"error": f"path not found: {path}"}]
    results: list[dict[str, Any]] = []
    for f in root.rglob(glob):
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                relpath = str(f.relative_to(_project_root()))
                results.append({
                    "path": relpath,
                    "line": i,
                    "text": line.rstrip()[:200],
                })
                if len(results) >= max_results:
                    return results
    return results


def list_modules(path: str = "src/cogcore") -> list[dict[str, Any]]:
    """列出指定路径下所有 Python 模块 + 行数。"""
    root = _resolve(path)
    if not root.exists():
        return [{"error": f"path not found: {path}"}]
    results: list[dict[str, Any]] = []
    for f in sorted(root.rglob("*.py")):
        if f.name == "__init__.py":
            continue
        try:
            n = sum(1 for _ in f.open("r", encoding="utf-8"))
        except (UnicodeDecodeError, OSError):
            n = 0
        results.append({
            "path": str(f.relative_to(_project_root())),
            "name": f.stem,
            "lines": n,
        })
    return results


def list_tests(path: str = "tests") -> list[dict[str, Any]]:
    """列出所有测试文件。"""
    root = _resolve(path)
    if not root.exists():
        return [{"error": f"path not found: {path}"}]
    results: list[dict[str, Any]] = []
    for f in sorted(root.rglob("test_*.py")):
        if not f.is_file():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            content = ""
        # 数 test_ 函数
        n_tests = len(re.findall(r"^def test_", content, re.MULTILINE))
        results.append({
            "path": str(f.relative_to(_project_root())),
            "test_count": n_tests,
        })
    return results


def find_test_for_module(module_path: str) -> str | None:
    """根据 module 路径推断对应测试文件。

    启发式：src/cogcore/xxx.py -> tests/test_xxx.py
    """
    p = Path(module_path)
    name = p.stem
    candidates = [
        _resolve(f"tests/test_{name}.py"),
        _resolve(f"tests/test_{name.replace('_test', '')}.py"),
    ]
    for c in candidates:
        if c.exists():
            return str(c.relative_to(_project_root()))
    return None


def count_lines(path: str) -> int:
    """数文件行数。"""
    p = _resolve(path)
    if not p.exists() or not p.is_file():
        return -1
    try:
        return sum(1 for _ in p.open("r", encoding="utf-8"))
    except (UnicodeDecodeError, OSError):
        return -1


# ============================================================
# 注册到 ToolRegistry
# ============================================================


def register_code_tools(registry: Any) -> int:
    """把代码感知工具注册到 ToolRegistry。"""
    from cogcore.tools import ToolRegistry

    if not isinstance(registry, ToolRegistry):
        return 0

    tools: list[tuple[str, Any, dict[str, str], str]] = [
        ("read_file", read_file, {"path": "string", "offset": "int", "limit": "int"}, "读源码片段（带行号）"),
        ("search_code", search_code, {"pattern": "string", "path": "string", "glob": "string"}, "按 regex 找代码"),
        ("list_modules", list_modules, {"path": "string"}, "列出所有模块 + 行数"),
        ("list_tests", list_tests, {"path": "string"}, "列出所有测试文件"),
        ("find_test_for_module", find_test_for_module, {"module_path": "string"}, "根据模块找测试文件"),
        ("count_lines", count_lines, {"path": "string"}, "数文件行数"),
    ]
    for name, func, schema, _desc in tools:
        registry.register_tool(name, func, schema)
        registry.add_to_allowlist(name)
    return len(tools)
